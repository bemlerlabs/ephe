"""
◑ Ephe – Swarm Engine V2
core/swarm_v2.py

Autonomous swarm system with:
  - manager agent (Gemma4 12B) decides via function calling about spawning
  - SwarmAgent: autonomous worker with its own Ollama client + tool access
  - SwarmOrchestrator: drives lifecycle, SSE events, synthesis

Architecture:

    ┌──────────────┐
    │  MANAGER     │  Gemma4 12B + the spawn_swarm tool
    └──────┬───────┘
           │ spawn_swarm({count, role, subtasks})
    ┌──────▼─────────────────────────────────┐
    │  asyncio.create_task() × N             │  ← PARALLEL, bounded by
    │  SwarmAgent1  SwarmAgent2  Agent3 ...  │    swarm_max_parallel (semaphore):
    │  (own client, own prompt)              │    excess agents queue per wave
    │  → terminate_self() when done          │
    └──────┬─────────────────────────────────┘
           │ N results via SharedState
    ┌──────▼───────┐
    │  SYNTHESIZER │  pulls everything together
    └──────────────┘

Design:
  - pure async Python, no threading
  - on_event callback for the SSE bridge (server integration)
  - SwarmAgent has tool calling via chat_with_tools (configurable whitelist)
  - self-termination: the agent calls terminate_self → the task ends itself
  - fail-safe: agent exceptions are caught, the others keep running

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import asyncio
import json
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import ollama  # noqa: F401 — test seam: tests patch core.swarm_v2.ollama

from core.chat import OllamaModelNotFoundError, OllamaNotReachableError
from core.swarm_state import (
    AgentStatus,
    SwarmPhase,
    SwarmStateStore,
    swarm_state_store,
)

# S1: result envelope (G1, G2, G10)
# Only the slim, validated package leaves a child towards the synthesis.
# Intermediate results stay in the child context (Clean-Summary-Discipline).
ENVELOPE_SUMMARY_CAP = 2000


@dataclass
class SwarmEnvelope:
    """Slim, validated return block of one swarm agent."""

    agent_id: str
    status: str = "ok"                 # ok|budget_exceeded|step_limit|timeout|error
    summary: str = ""                  # capped to ENVELOPE_SUMMARY_CAP
    facts: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    trace_id: str = ""
    run_id: str = ""
    task_spec_hash: str = ""

    def as_text(self) -> str:
        """Merge-ready text form: summary + facts, no raw dumps."""
        parts = [self.summary] if self.summary else []
        if self.facts:
            parts.append("Fakten: " + "; ".join(self.facts))
        if self.status != "ok":
            parts.append(f"[status={self.status}]")
        return "\n".join(p for p in parts if p)


def _make_envelope(agent_id: str, text: str, *, status: str = "ok",
                   trace_id: str = "", run_id: str = "",
                   task_spec_hash: str = "",
                   tokens_in: int = 0, tokens_out: int = 0) -> SwarmEnvelope:
    """Raw text → validated envelope (cap + required-field check).

    The token counters are what the engine reported for this agent's calls and
    stay zero when it reported no usage — a figure the surface can hide, never
    one it can guess.
    """
    body = (text or "").strip()
    capped = len(body) > ENVELOPE_SUMMARY_CAP
    summary = body[:ENVELOPE_SUMMARY_CAP]
    facts = [ln for ln in body.splitlines() if ln.strip()][:20]
    st = status if status != "ok" else ("budget_exceeded" if capped else "ok")
    return SwarmEnvelope(
        agent_id=agent_id, status=st, summary=summary, facts=facts,
        tokens_in=tokens_in, tokens_out=tokens_out,
        trace_id=trace_id, run_id=run_id, task_spec_hash=task_spec_hash,
    )


def _coerce_result(
    result: object, *, agent_id: str, run_id: str, trace_id: str
) -> SwarmEnvelope | str | None:
    """Anything a child task left behind → a value the merge step can read.

    An envelope, a raw string (mock/legacy seam) and ``None`` pass through;
    every ``BaseException`` becomes an error envelope. ``asyncio.CancelledError``
    is a ``BaseException``, so the old ``isinstance(result, Exception)`` guard let
    it through and the merge then read ``.status`` off a cancelled task, losing
    the whole wave's answer. An unexpected object is an error as well.
    """
    if result is None or isinstance(result, (SwarmEnvelope, str)):
        return result
    if isinstance(result, BaseException):
        logger.error("Agent %s crashed: %r", agent_id, result)
    else:
        logger.error("Agent %s returned an unexpected %s: %r",
                     agent_id, type(result).__name__, result)
    return _make_envelope(
        agent_id, f"[agent error: {result!r}]", status="error",
        trace_id=trace_id, run_id=run_id,
    )


def _task_spec_hash(subtask: str) -> str:
    """Stable short hash of the subtask (idempotency / replay anchor)."""
    return hashlib.sha256(subtask.encode("utf-8")).hexdigest()[:12]

logger = logging.getLogger(__name__)


# Wave observability: counters + events for a running wave. The semaphore bounds
# a wave; these counters say what the bound is doing right now (how much queues,
# how much runs, how the finished agents ended). The on_event bridge carries them
# as `swarm_wave` events so a live surface can render wave progress.

_WAVE_STATUS_BUCKETS = frozenset(
    {"ok", "budget_exceeded", "step_limit", "timeout", "error"}
)


def _wave_status(value: object) -> str:
    """Normalises an envelope status onto a counter bucket (unknown → error)."""
    if isinstance(value, SwarmEnvelope):
        value = value.status
    text = str(value) if value is not None else ""
    if text in _WAVE_STATUS_BUCKETS:
        return text
    return "ok" if text == "" else "error"


@dataclass
class WaveCounters:
    """Live counters of one running wave (agents queued / active / finished)."""

    total: int
    cap: int
    active: int = 0
    started: int = 0
    finished: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    #: Gated tool calls this wave's agents asked for and the gate refused (N24 R1):
    #: the call is skipped, never run, and the refusal is counted here.
    skipped_for_approval: int = 0

    @property
    def queued(self) -> int:
        """Agents still waiting for a slot (total minus those that started)."""
        return max(0, self.total - self.started)

    def record_start(self) -> None:
        """One agent entered a slot: it is active and counted as started."""
        self.active += 1
        self.started += 1

    def record_finish(self, status: object) -> str:
        """One agent left its slot: bucket its terminal status, returns the bucket."""
        bucket = _wave_status(status)
        self.active = max(0, self.active - 1)
        self.finished += 1
        self.by_status[bucket] = self.by_status.get(bucket, 0) + 1
        return bucket

    def record_gate_skip(self) -> None:
        """Count a tool call the approval gate refused."""
        self.skipped_for_approval += 1

    def snapshot(self) -> dict:
        """Flat, JSON-able view of the counters (safe to put on the wire)."""
        return {
            "total": self.total,
            "cap": self.cap,
            "queued": self.queued,
            "active": self.active,
            "started": self.started,
            "finished": self.finished,
            "by_status": dict(self.by_status),
            # The gate's figure for this wave: N tools skipped for approval.
            "skipped_for_approval": self.skipped_for_approval,
        }


# Constants

# Hard cap of the spawn COUNT per wave. The runtime parallelism of a wave is a
# separate lever: the generation option `swarm_max_parallel`
# (core/engine_config.py: env EPHE_SWARM_MAX_PARALLEL > engine.json > default 8).
MAX_SWARM_AGENTS = 8
DEFAULT_TOOL_WHITELIST = [
    "web_search", "browser_go", "browser_screenshot", "browser_click",
    "browser_type", "browser_press", "read_file", "list_directory",
    "file_search", "load_workspace", "get_datetime", "analyze_image",
]
AGENT_TIMEOUT = 120.0  # Max seconds per agent


def resolve_swarm_max_parallel() -> int:
    """Active concurrency cap of one swarm wave (env > engine.json > default).

    Reads the generation option `swarm_max_parallel` at pipeline start, so a
    changed cap applies to the next swarm run without a restart. A damaged
    config can never take the swarm down — the fallback is MAX_SWARM_AGENTS.
    """
    from core.engine_config import read_generation_values

    try:
        cap = int(read_generation_values()["swarm_max_parallel"])
    except Exception:
        return MAX_SWARM_AGENTS
    # Ceiling = the spawn-count cap: a wave never runs more agents at once than
    # it spawned, so a misconfigured wide cap is trimmed instead of sizing the
    # semaphore to a number the wave can never reach.
    return min(MAX_SWARM_AGENTS, max(1, cap))

# Prompts

MANAGER_SYSTEM = """\
You are the manager agent of Ephe. Your job is to analyse complex tasks
and, when needed, spawn a swarm of specialist agents.

ANALYSIS STRATEGY:
1. Read the task carefully
2. Decide: can I solve this alone, or do I need parallel helpers?
3. If parallel helpers are needed: use the spawn_swarm tool

RULES FOR SPAWN DECISIONS:
- Spawn ONLY if the task clearly splits into independent subtasks
- Spawn 2-6 agents (no more, no less)
- Each agent needs a CLEAR, SELF-CONTAINED subtask
- Roles: researcher, writer, analyzer, summarizer, coder, reviewer

If you do NOT need spawn_swarm, solve the task directly yourself.\
"""

SPECIALIST_SYSTEM_TEMPLATE = """\
You are a specialist swarm agent with the role: {role}

Your ONE task: {subtask}

Context of the overall task: {main_task}

RULES:
- Focus ONLY on your subtask
- Be precise and thorough
- Use available tools when needed (web_search, browser_go, read_file, etc.)
- When you are done, call terminate_self()
- Your result will be merged by a synthesizer with the results of the other agents\
"""

SYNTHESIZER_SYSTEM = """\
You are the synthesis agent. Combine the results of several specialist agents
into one coherent, well-structured overall answer.

RULES:
- Avoid duplicates
- Structure with markdown (headings, lists, code blocks)
- Be clear and action-oriented
- Do NOT mention that the answer comes from different agents
- Phrase it as a single, well-considered answer\
"""


# Swarm Tool Schemas

def get_spawn_swarm_schema() -> dict:
    """Tool schema for spawn_swarm (manager agent only)."""
    return {
        "type": "function",
        "function": {
            "name": "spawn_swarm",
            "description": (
                "Spawns a swarm of specialist agents for parallel task processing. Use this tool when a task can be split into independent subtasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of agents to spawn (2-8)",
                    },
                    "role": {
                        "type": "string",
                        "description": (
                            "Role for all agents. One of: researcher, writer, analyzer, summarizer, coder, reviewer"
                        ),
                    },
                    "subtasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of subtasks — one per agent",
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["general", "explore", "judge"],
                        "description": (
                            "Mode: general = balanced default (5 iterations), "
                            "explore = breadth-first multi-probe search (8), "
                            "judge = visual acceptance against given notes (3)."
                        ),
                    },
                },
                "required": ["count", "role", "subtasks"],
            },
        },
    }


# J2: mode configuration (point 5 — agent types as orchestrator modes)

_MODE_CONFIGS: dict[str, dict] = {
    "general": {
        "max_iterations": 5,
        "note": "",
    },
    "explore": {
        "max_iterations": 8,
        "note": (
            "Breadth-first: run several independent probes, return short "
            "excerpts + file paths, no long transcriptions."
        ),
    },
    "judge": {
        "max_iterations": 3,
        "note": (
            "Visual acceptance: read the given PNG paths, emit one verdict "
            "line per page (pass/fail + evidence)."
        ),
    },
}


def _mode_config(task_type: str = "general") -> dict:
    """Budget + prompt addition for a swarm mode (unknown → general)."""
    return _MODE_CONFIGS.get(task_type, _MODE_CONFIGS["general"])


# J2: agent continuation (point 6 — SendMessage equivalent)
# Module-global history reservoir, FIFO cap like R23; every history carries the
# model of the origin session for naive continuation without re-classification.

_AGENT_SESSIONS: dict[str, dict] = {}
_MAX_AGENT_SESSIONS = 50


def _store_agent_history(agent_id: str, history: list[dict], model: str = "") -> None:
    """Stores (or updates) the conversation history of one agent."""
    entry = _AGENT_SESSIONS.get(agent_id) or {"history": [], "model": ""}
    entry["history"] = list(history)[-20:]
    if model:
        entry["model"] = model
    _AGENT_SESSIONS[agent_id] = entry
    while len(_AGENT_SESSIONS) > _MAX_AGENT_SESSIONS:
        _AGENT_SESSIONS.pop(next(iter(_AGENT_SESSIONS)), None)


def _get_agent_history(agent_id: str) -> list[dict]:
    """Reads the stored history (empty list for an unknown id)."""
    entry = _AGENT_SESSIONS.get(agent_id)
    return list(entry["history"]) if entry else []


def get_agent_message_schema() -> dict:
    """Tool schema for agent_message (continuation of a swarm agent)."""
    return {
        "type": "function",
        "function": {
            "name": "agent_message",
            "description": (
                "Continues a finished swarm agent with a new message. The agent's stored conversation history is reused as context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "The agent's id (as reported by the swarm run).",
                    },
                    "message": {
                        "type": "string",
                        "description": "The follow-up message for the agent.",
                    },
                },
                "required": ["agent_id", "message"],
            },
        },
    }


async def agent_message(agent_id: str, message: str) -> str:
    """One-shot continuation of an agent against its stored history."""
    entry = _AGENT_SESSIONS.get(agent_id)
    if entry is None or not entry.get("history"):
        return (
            f"[No stored history for agent '{agent_id}' — "
            "it never ran or was purged. Start a fresh swarm run instead.]"
        )

    model = entry.get("model") or ""
    if not model:
        from core.model_provider import get_active_provider

        model = get_active_provider().model

    messages: list[dict] = list(entry["history"]) + [
        {"role": "user", "content": message}
    ]
    # R36-S: the active engine instead of a hardcoded Ollama (agent_message continuation).
    from core.model_provider import build_provider_client

    client = build_provider_client()
    try:
        response = await asyncio.wait_for(
            client.chat(model=model, messages=messages, stream=False),
            timeout=AGENT_TIMEOUT,
        )
        text = str(getattr(response.message, "content", "") or "").strip()
    except asyncio.TimeoutError:
        return f"[Agent {agent_id} timeout after {AGENT_TIMEOUT}s]"
    except Exception as exc:
        return f"[Agent {agent_id} error: {exc}]"

    messages.append({"role": "assistant", "content": text})
    _store_agent_history(agent_id, messages, model)
    return text or "(no output)"


def get_terminate_self_schema() -> dict:
    """Tool schema for terminate_self (for swarm agents)."""
    return {
        "type": "function",
        "function": {
            "name": "terminate_self",
            "description": (
                "Terminate this swarm agent. Call this when your subtask is fully done. Your result will be stored."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }


# Exceptions

class SwarmAgentTerminated(Exception):
    """Signals that an agent has ended itself via terminate_self."""
    pass


# SwarmAgent

class SwarmAgent:
    """
    An autonomous swarm worker with its own LLM context and tool access.

    Lifecycle:
        1. __init__: the agent gets configured (role, subtask, tools)
        2. run(): the agent works autonomously with chat + tool-calling
        3. terminate_self or a natural end → result in the SharedState
    """

    def __init__(
        self,
        *,
        agent_id: str,
        role: str,
        subtask: str,
        main_task: str,
        model: str,
        state_store: SwarmStateStore,
        swarm_id: str,
        tool_whitelist: list[str] | None = None,
        task_type: str = "general",
        active_skills: list[str] | None = None,
        trace_id: str = "",
        run_id: str = "",
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.subtask = subtask
        self.main_task = main_task
        self.model = model
        self.state = state_store
        self.swarm_id = swarm_id
        self.tool_whitelist = tool_whitelist or DEFAULT_TOOL_WHITELIST
        self.task_type = task_type
        self.active_skills = active_skills or []
        self.trace_id = trace_id
        self.run_id = run_id
        self.task_spec_hash = _task_spec_hash(subtask)
        self._terminated = False
        # R36-S: optional SSE bridge channel — emits swarm_agent_started/
        # tool/chunk/done, so the UI can render one clickable live transcript
        # per agent (reference parity with leading agent frameworks).
        # None = silent (CLI/mock paths).
        self.on_event = on_event
        # N24 R1: the wave's counters, attached by the orchestrator while the
        # agent runs, so a gate refusal counts as a tool skipped for approval.
        self.wave: WaveCounters | None = None

    def _emit(self, event: dict) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:  # the bridge must never tear the agent down
            logger.exception("swarm agent event bridge failed")

    async def run(self) -> SwarmEnvelope:
        """
        Main loop: LLM call with tool calling.
        Returns a validated SwarmEnvelope (S1).
        """
        await self.state.update_agent_status(
            self.agent_id, AgentStatus.RUNNING, f"Starte: {self.subtask[:60]}…"
        )

        # Agent isolation, Ephe norm: every sub-agent = its own mini computer (its own cell).
        # Cell key = agent_id (not session_id), so worker namespaces stay isolated.
        from core.ephemeral_cell import create_cell as _cc, KIND_KERNEL as _kk
        _cc(self.agent_id, kind=_kk)

        mode = _mode_config(self.task_type)
        system_prompt = SPECIALIST_SYSTEM_TEMPLATE.format(
            role=self.role,
            subtask=self.subtask,
            main_task=self.main_task,
        )
        if mode.get("note"):
            system_prompt += f"\nMODE ({self.task_type}): {mode['note']}"
        # S2: skill hand-off — paths only, not inline (Fowler Narrow-Fix)
        if self.active_skills:
            system_prompt += "\nAKTIVE SKILLS (Pfade): " + ", ".join(self.active_skills)

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.subtask},
        ]

        # Tools: filtered schemas + terminate_self
        tools = self._get_tools()

        # R36-S: the active engine instead of a hardcoded Ollama — the swarm paths
        # follow the configured engine (before: non-Ollama setups died
        # with 'pull it at ollama.com/download').
        from core.model_provider import build_provider_client

        client = build_provider_client()
        result_text = ""
        max_iterations = mode["max_iterations"]
        # What the engine reported across this agent's calls; 0 = it reported none.
        tokens_in = 0
        tokens_out = 0

        try:
            for iteration in range(max_iterations):
                if self._terminated:
                    break

                response = await asyncio.wait_for(
                    client.chat(
                        model=self.model,
                        messages=messages,
                        tools=tools,
                        stream=False,
                    ),
                    timeout=AGENT_TIMEOUT,
                )

                usage = getattr(response, "usage", None)
                if usage is not None:
                    tokens_in += int(getattr(usage, "prompt_tokens", 0) or 0)
                    tokens_out += int(getattr(usage, "completion_tokens", 0) or 0)

                # Process the tool calls
                if (
                    hasattr(response, "message")
                    and hasattr(response.message, "tool_calls")
                    and response.message.tool_calls
                ):
                    messages.append(response.message)

                    for tool_call in response.message.tool_calls:
                        name = tool_call.function.name
                        args = tool_call.function.arguments or {}

                        # terminate_self → the agent ends itself
                        if name == "terminate_self":
                            self._terminated = True
                            await self.state.add_tool_used(self.agent_id, name)
                            messages.append({
                                "role": "tool",
                                "content": "Agent terminated successfully.",
                            })
                            break

                        # block run_shell (security)
                        if name == "run_shell":
                            messages.append({
                                "role": "tool",
                                "content": "[swarm agents may not execute shell commands.]",
                            })
                            continue

                        # check the tool whitelist
                        if name not in self.tool_whitelist:
                            messages.append({
                                "role": "tool",
                                "content": f"[Tool '{name}' is not in this agent's whitelist.]",
                            })
                            continue

                        # N24: a swarm agent's call takes the approval gate the
                        # main turn takes, and the answer is kept as a record
                        # (exempt / approved / denied) — never a silent write.
                        from core.tools.chat_gate import gate_delegated_tool

                        allowed, denial, _gate_note = await gate_delegated_tool(
                            name, args, who=f"swarm agent {self.agent_id}"
                        )
                        if not allowed:
                            # N24 R1: the gate refusal becomes a skipped-for-approval
                            # count on the wave.
                            if self.wave is not None:
                                self.wave.record_gate_skip()
                            messages.append({"role": "tool", "content": denial})
                            continue

                        # run the tool
                        await self.state.update_agent_status(
                            self.agent_id,
                            AgentStatus.RUNNING,
                            f"{name}({json.dumps(args, ensure_ascii=False)[:50]})",
                        )
                        await self.state.add_tool_used(self.agent_id, name)

                        # No shell-approval branch here (N24 R2): run_shell is refused
                        # above, before the whitelist and the gate, and the one site
                        # that raises ShellConfirmationRequired is the chat-layer
                        # run_shell — never this path — so such a handler would be dead
                        # code, and it used to swallow the signal into an unaudited
                        # string. Any real error keeps its audited [tool-error] line.
                        from core.tools import execute_tool
                        try:
                            tool_result = await execute_tool(name, args)
                        except Exception as exc:
                            tool_result = f"[tool-error: {exc}]"

                        messages.append({
                            "role": "tool",
                            "content": tool_result,
                        })

                    if self._terminated:
                        # extract the result from the messages so far
                        result_text = self._extract_result(messages)
                        break

                    continue  # next iteration after the tool calls

                # no tool calls → the final answer
                if hasattr(response, "message") and response.message.content:
                    result_text = str(response.message.content).strip()
                break  # done

        except asyncio.TimeoutError:
            result_text = f"[Agent {self.agent_id} Timeout after {AGENT_TIMEOUT}s]"
            await self.state.set_agent_error(self.agent_id, "Timeout")
            _store_agent_history(
                self.agent_id, self._serialize_messages(messages), self.model
            )
            return _make_envelope(self.agent_id, result_text, status="timeout",
                                  trace_id=self.trace_id, run_id=self.run_id,
                                  task_spec_hash=self.task_spec_hash,
                                  tokens_in=tokens_in, tokens_out=tokens_out)
        except Exception as exc:
            result_text = f"[Agent {self.agent_id} Error: {exc}]"
            await self.state.set_agent_error(self.agent_id, str(exc))
            _store_agent_history(
                self.agent_id, self._serialize_messages(messages), self.model
            )
            return _make_envelope(self.agent_id, result_text, status="error",
                                  trace_id=self.trace_id, run_id=self.run_id,
                                  task_spec_hash=self.task_spec_hash,
                                  tokens_in=tokens_in, tokens_out=tokens_out)

        # store result + history (the basis for the agent_message continuation)
        _store_agent_history(
            self.agent_id, self._serialize_messages(messages), self.model
        )
        await self.state.set_agent_result(self.agent_id, result_text)
        if not self._terminated:
            await self.state.update_agent_status(
                self.agent_id, AgentStatus.DONE, "Aufgabe erledigt"
            )
        else:
            await self.state.terminate_agent(self.agent_id)

        # S4: step_limit status when max_iterations is reached without terminate
        step_status = "step_limit" if (iteration + 1 >= max_iterations and not self._terminated) else "ok"
        return _make_envelope(self.agent_id, result_text, status=step_status,
                              trace_id=self.trace_id, run_id=self.run_id,
                              task_spec_hash=self.task_spec_hash,
                              tokens_in=tokens_in, tokens_out=tokens_out)

    def _get_tools(self) -> list[dict]:
        """Builds the tool schemas for this agent (filtered + terminate_self)."""
        from core.tools import get_tool_schemas

        all_tools = get_tool_schemas()
        filtered = [
            t for t in all_tools
            if t.get("function", {}).get("name") in self.tool_whitelist
        ]
        filtered.append(get_terminate_self_schema())
        return filtered

    def _serialize_messages(self, messages: list) -> list[dict]:
        """Messages (dicts + Pydantic response objects) → JSON-able dicts."""
        out: list[dict] = []
        for msg in messages:
            if isinstance(msg, dict):
                out.append(msg)
            else:
                out.append({
                    "role": str(getattr(msg, "role", "assistant") or "assistant"),
                    "content": str(getattr(msg, "content", "") or ""),
                })
        return out

    def _extract_result(self, messages: list[dict]) -> str:
        """Extracts the last meaningful result from the message history."""
        # find the last assistant message with content
        for msg in reversed(messages):
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            content = ""
            if isinstance(msg, dict):
                content = msg.get("content", "")
            elif hasattr(msg, "content"):
                content = str(msg.content or "")
            if role == "assistant" and content and "terminate" not in content.lower():
                return content
        return f"[Agent {self.agent_id}: task completed via terminate_self]"


# SwarmOrchestrator

class SwarmOrchestrator:
    """
    Drives the whole swarm lifecycle.

    1. The manager agent analyses the task
    2. The manager spawns via the spawn_swarm tool
    3. N SwarmAgents run in parallel
    4. The synthesizer pulls the results together

    Usage:
        orchestrator = SwarmOrchestrator(
            task="Analyse 3 AI trends",
            model=chosen_model("the swarm run"),
            on_event=emit,
        )
        result = await orchestrator.run()
    """

    def __init__(
        self,
        *,
        task: str,
        model: str,
        on_event: Callable[[dict], None] | None = None,
        state_store: SwarmStateStore | None = None,
        tool_whitelist: list[str] | None = None,
        active_skills: list[str] | None = None,
    ) -> None:
        self.task = task
        self.model = model
        self.on_event = on_event or (lambda e: None)
        self.state = state_store or swarm_state_store
        # The merge call's own usage, when its engine reported one.
        self._synth_tokens: dict[str, int] | None = None
        self.tool_whitelist = tool_whitelist or DEFAULT_TOOL_WHITELIST
        self.active_skills = active_skills or []
        self.swarm_id = ""
        self._spawn_result: dict | None = None
        # Live wave counters + event emission (filled once the wave starts).
        self.wave: WaveCounters | None = None

    def _emit_wave(self, transition: str, agent_id: str) -> None:
        """Pushes one counter snapshot on the event bridge for a wave transition."""
        if self.wave is None:
            return
        event = {
            "type": "swarm_wave",
            "swarm_id": self.swarm_id,
            "transition": transition,
            "agent_id": agent_id,
        }
        event.update(self.wave.snapshot())
        self.on_event(event)

    def _wave_enter(self, agent: SwarmAgent) -> None:
        """An agent took a slot: mark it active/started and emit the snapshot."""
        if self.wave is None:
            return
        self.wave.record_start()
        self._emit_wave("started", agent.agent_id)

    def _wave_exit(self, agent: SwarmAgent, status: object) -> None:
        """An agent freed its slot: bucket its status and emit the snapshot."""
        if self.wave is None:
            return
        self.wave.record_finish(status)
        self._emit_wave("finished", agent.agent_id)

    def wave_snapshot(self) -> dict:
        """Counter snapshot of the current wave (empty dict before it starts)."""
        return self.wave.snapshot() if self.wave is not None else {}

    async def run(self) -> SwarmV2Result:
        """
        Runs the whole swarm pipeline.

        Returns:
            SwarmV2Result with all agent results and the final synthesis.
        """
        # create the session
        self.swarm_id = self.state.create_session(self.task)
        self.state.subscribe(self.on_event)

        try:
            return await self._execute_pipeline()
        finally:
            self.state.unsubscribe(self.on_event)

    async def _execute_pipeline(self) -> SwarmV2Result:
        """Internal pipeline: manager → spawn → execute → synthesize."""

        # Phase 1: the manager analyses and spawns
        await self.state.update_session_phase(self.swarm_id, SwarmPhase.PLANNING)

        spawn_params = await self._run_manager()

        if not spawn_params:
            # the manager answered directly (no spawn needed)
            await self.state.update_session_phase(self.swarm_id, SwarmPhase.DONE)
            return SwarmV2Result(
                swarm_id=self.swarm_id,
                task=self.task,
                subtasks=[],
                agent_results=[],
                final=self._spawn_result.get("direct_answer", "") if self._spawn_result else "",
            )

        # Phase 2: spawn the agents
        await self.state.update_session_phase(self.swarm_id, SwarmPhase.SPAWNING)

        count = min(spawn_params.get("count", 2), MAX_SWARM_AGENTS)
        role = spawn_params.get("role", "researcher")
        subtasks = spawn_params.get("subtasks", [self.task])
        task_type = spawn_params.get("task_type") or "general"

        # align the subtasks with the count
        while len(subtasks) < count:
            subtasks.append(self.task)
        subtasks = subtasks[:count]

        # S3: trace linking — one trace_id per swarm, one run_id per child
        trace_id = self.swarm_id
        # S2: skill hand-off from spawn_params (the manager declares one per subtask)
        skills_per_subtask = spawn_params.get("skills") or []

        agents: list[SwarmAgent] = []
        for i, subtask in enumerate(subtasks):
            agent_id = self.state.register_agent(self.swarm_id, role, subtask)
            sub_skills = skills_per_subtask[i] if i < len(skills_per_subtask) else self.active_skills
            agent = SwarmAgent(
                agent_id=agent_id,
                role=role,
                subtask=subtask,
                main_task=self.task,
                model=self.model,
                state_store=self.state,
                swarm_id=self.swarm_id,
                tool_whitelist=self.tool_whitelist,
                task_type=task_type,
                active_skills=sub_skills,
                trace_id=trace_id,
                run_id=f"{self.swarm_id}:{i}",
                # The bridge the orchestrator received: without it every card in
                # the deck stayed at its first frame (no started/done pair ever
                # reached the stream, and the roster size was unknown).
                on_event=self.on_event,
            )
            agents.append(agent)

        # The roster the deck draws: one row per agent with the model that runs
        # it and the hash of its task, before the first agent starts.
        self.on_event({
            "type": "swarm_created",
            "swarm_id": self.swarm_id,
            "model": self.model,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "role": a.role,
                    "model": a.model,
                    "task_spec_hash": a.task_spec_hash,
                }
                for a in agents
            ],
        })

        # Phase 3: parallel execution — bounded by swarm_max_parallel (generation
        # option, default 8; the spawn COUNT is already capped in phase 2). A wave
        # starts at most `cap` agents together; the rest queue on the semaphore
        # and follow as slots free up — no agent is dropped or reordered.
        await self.state.update_session_phase(self.swarm_id, SwarmPhase.EXECUTING)

        parallel_cap = resolve_swarm_max_parallel()
        agent_slots = asyncio.Semaphore(parallel_cap)
        self.wave = WaveCounters(total=len(agents), cap=parallel_cap)
        self._emit_wave("start", "")

        async def _run_bounded(agent: SwarmAgent) -> SwarmEnvelope:
            async with agent_slots:
                # The agent counts its gate skips on this wave's counters (N24 R1).
                agent.wave = self.wave
                self._wave_enter(agent)
                # The card opens when the slot is taken (not when the agent was
                # queued): role, model and task hash travel with it.
                self.on_event({
                    "type": "swarm_agent_started",
                    "swarm_id": self.swarm_id,
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "model": agent.model,
                    "task_spec_hash": agent.task_spec_hash,
                    "subtask": agent.subtask,
                })
                status: object = "error"
                try:
                    envelope = await agent.run()
                    status = envelope
                    return envelope
                finally:
                    # The deck's card closes on this frame; without it every
                    # agent stayed "running" until the turn ended.
                    ok = isinstance(status, SwarmEnvelope)
                    self.on_event({
                        "type": "swarm_agent_done",
                        "swarm_id": self.swarm_id,
                        "agent_id": agent.agent_id,
                        "status": "done" if ok else "error",
                        "summary": status.summary[:280] if ok else "",
                        # 0/0 = the engine reported no usage; the card then shows none.
                        "tokens_in": status.tokens_in if ok else 0,
                        "tokens_out": status.tokens_out if ok else 0,
                    })
                    self._wave_exit(agent, status)

        agent_tasks = [asyncio.create_task(_run_bounded(agent)) for agent in agents]
        envelopes: list[SwarmEnvelope | str | None] = []

        # Wait for the whole wave. A cancelled orchestrator (client gone, wave
        # aborted) must not leave its children running or the session stuck in
        # EXECUTING: cancel every child, wait for each to unwind (so its
        # _wave_exit ran), stamp the phase ERROR, then let the CancelledError
        # continue.
        try:
            done_results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for agent_task in agent_tasks:
                agent_task.cancel()
            await asyncio.gather(*agent_tasks, return_exceptions=True)
            await self.state.update_session_phase(self.swarm_id, SwarmPhase.ERROR)
            raise

        for i, result in enumerate(done_results):
            envelopes.append(_coerce_result(
                result,
                agent_id=agents[i].agent_id,
                run_id=f"{self.swarm_id}:{i}",
                trace_id=trace_id,
            ))

        # S4: merge from envelopes — missing/faulty children as explicit gaps
        results: list[str] = []
        for i, env in enumerate(envelopes):
            if env is None:
                results.append(f"[Quelle {i+1} nicht verfuegbar: kein Ergebnis]")
            elif isinstance(env, str):          # defensive: mock/legacy form
                results.append(env)
            elif env.status != "ok":
                results.append(f"{env.as_text()}\n[Gap: status={env.status}]")
            else:
                results.append(env.as_text())

        # Phase 4: synthesis
        await self.state.update_session_phase(self.swarm_id, SwarmPhase.SYNTHESIZING)

        self._synth_tokens = None
        final = await self._synthesize(subtasks, results)
        # What the orchestrator actually carried: the agents' own context next to
        # the brief the merge step read. Both numbers are engine-reported; the
        # difference is arithmetic, not an estimate.
        usage = self._synth_tokens or {}
        tokens = {
            "agent_in": sum(
                env.tokens_in for env in envelopes if isinstance(env, SwarmEnvelope)
            ),
            "agent_out": sum(
                env.tokens_out for env in envelopes if isinstance(env, SwarmEnvelope)
            ),
            "merge_in": int(usage.get("in", 0)),
            "merge_out": int(usage.get("out", 0)),
        }

        await self.state.set_session_result(self.swarm_id, final)
        await self.state.update_session_phase(self.swarm_id, SwarmPhase.DONE)

        # swarm_done event
        self.on_event({
            "type": "swarm_done",
            "swarm_id": self.swarm_id,
            "agent_count": len(agents),
            "final": final,
            "counters": self.wave_snapshot(),
            "tokens": tokens,
        })

        return SwarmV2Result(
            swarm_id=self.swarm_id,
            task=self.task,
            subtasks=subtasks,
            agent_results=results,
            final=final,
            envelopes=envelopes,
            counters=self.wave_snapshot(),
            tokens=tokens,
        )

    async def _run_manager(self) -> dict | None:
        """
        Manager agent: analyses the task and decides about spawning.

        Returns:
            dict with spawn_params when spawning is needed, None when the manager answers
            directly.
        """
        # R36-S: the active engine instead of a hardcoded Ollama — the swarm paths
        # follow the configured engine (before: non-Ollama setups died
        # with 'pull it at ollama.com/download').
        from core.model_provider import build_provider_client

        client = build_provider_client()
        tools = [get_spawn_swarm_schema()]

        messages = [
            {"role": "system", "content": MANAGER_SYSTEM},
            {"role": "user", "content": self.task},
        ]

        try:
            response = await asyncio.wait_for(
                client.chat(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    stream=False,
                ),
                timeout=60.0,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("connection", "refused", "socket")):
                raise OllamaNotReachableError() from exc
            if "not found" in msg:
                raise OllamaModelNotFoundError(self.model) from exc
            raise

        # check for a tool call
        if (
            hasattr(response, "message")
            and hasattr(response.message, "tool_calls")
            and response.message.tool_calls
        ):
            for tool_call in response.message.tool_calls:
                if tool_call.function.name == "spawn_swarm":
                    params = tool_call.function.arguments or {}
                    logger.info(f"◑ Manager spawnt Swarm: {params}")
                    return params

        # no tool call → the manager answered directly
        direct = ""
        if hasattr(response, "message") and response.message.content:
            direct = str(response.message.content).strip()

        self._spawn_result = {"direct_answer": direct}
        return None

    async def _synthesize(self, subtasks: list[str], results: list[str]) -> str:
        """Synthesizer agent: combines the agent results into one answer."""
        parts = [f"Originalaufgabe: {self.task}\n"]
        for i, (subtask, result) in enumerate(zip(subtasks, results), 1):
            parts.append(f"Teilaufgabe {i}: {subtask}\nErgebnis:\n{result}")

        combined = "\n\n---\n\n".join(parts)

        # R36-S: the active engine instead of a hardcoded Ollama — the swarm paths
        # follow the configured engine (before: non-Ollama setups died
        # with 'pull it at ollama.com/download').
        from core.model_provider import build_provider_client

        client = build_provider_client()
        try:
            response = await asyncio.wait_for(
                client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYNTHESIZER_SYSTEM},
                        {"role": "user", "content": combined},
                    ],
                    stream=False,
                ),
                timeout=90.0,
            )
            # two shapes arrive: Pydantic object (Ollama ≥ 0.4) or dict
            if isinstance(response, dict):
                content = response.get("message", {}).get("content", "")
                usage = response.get("usage") or {}
                self._synth_tokens = {
                    "in": int(usage.get("prompt_tokens") or 0),
                    "out": int(usage.get("completion_tokens") or 0),
                }
            else:
                content = getattr(getattr(response, "message", None), "content", "") or ""
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self._synth_tokens = {
                        "in": int(getattr(usage, "prompt_tokens", 0) or 0),
                        "out": int(getattr(usage, "completion_tokens", 0) or 0),
                    }
            return str(content).strip()
        except Exception as exc:
            logger.error(f"◑ Synthesizer error: {exc}")
            # fallback: simply join the results
            return "\n\n---\n\n".join(
                f"## Teilaufgabe {i+1}\n{r}" for i, r in enumerate(results)
            )


# Result

@dataclass
class SwarmV2Result:
    """What one swarm run left behind: the split, the agent texts, the final answer."""
    swarm_id: str
    task: str
    subtasks: list[str]
    agent_results: list[str]
    final: str
    envelopes: list[SwarmEnvelope | str | None] = field(default_factory=list)
    counters: dict = field(default_factory=dict)
    tokens: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"SwarmV2Result(swarm_id={self.swarm_id!r}, "
            f"agents={len(self.subtasks)}, "
            f"final_len={len(self.final)})"
        )


# Public API

async def run_swarm_v2(
    *,
    task: str,
    model: str,
    on_event: Callable[[dict], None] | None = None,
    state_store: SwarmStateStore | None = None,
    tool_whitelist: list[str] | None = None,
    active_skills: list[str] | None = None,
) -> SwarmV2Result:
    """
    Convenience function: creates and runs a SwarmOrchestrator.

    Args:
        task:           the task
        model:          Ollama model
        on_event:       SSE bridge callback
        state_store:    optional: your own state store (for tests)
        tool_whitelist: optional: tools for the agents (default: all read-safe tools)

    Returns:
        SwarmV2Result
    """
    orchestrator = SwarmOrchestrator(
        task=task,
        model=model,
        on_event=on_event,
        state_store=state_store,
        tool_whitelist=tool_whitelist,
        active_skills=active_skills,
    )
    return await orchestrator.run()
