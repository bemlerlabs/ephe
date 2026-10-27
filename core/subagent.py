"""Single sub-agent runner for native chat-agent delegation.

The main chat agent decides autonomously when a task benefits from a helper —
no slash command needed. ``spawn_agent`` (see core/tools/subagent_tool.py)
runs one ``Subagent``: an isolated LLM loop with a READ-ONLY tool whitelist,
following the configured engine (never a hardcoded provider).

Naming: this is deliberately NOT the swarm pipeline (core/swarm_v2.py, the
``/swarm`` manager→spawn→synthesize flow). One helper, one task, one report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from core import subagent_history
from core.steering import SteeringChannel, take_up

logger = logging.getLogger(__name__)

#: Read-only tools a subagent may use. Host mutations are out of scope for
#: helper agents — the main agent keeps approval-gated write tools itself.
SUBAGENT_TOOL_WHITELIST: list[str] = [
    "web_search", "fetch_url", "read_file", "list_directory",
    "file_search", "load_workspace", "get_datetime", "analyze_image",
    "query_source_notebook",
]

#: Per-agent LLM budget. One helper should never stall a turn for minutes.
SUBAGENT_TIMEOUT = 180.0
SUBAGENT_MAX_ITERATIONS = 8


@dataclass
class SubagentResult:
    agent_id: str
    role: str
    task: str
    report: str
    status: str = "ok"  # ok | timeout | error
    tool_calls: list[dict] = field(default_factory=list)


class Subagent:
    """One delegated helper: own context, own tools, one report back."""

    def __init__(
        self,
        *,
        agent_id: str,
        role: str,
        task: str,
        model: str | None = None,
        context: str = "",
        on_event: Callable[[dict], None] | None = None,
        allowed_tools: list[str] | None = None,
        timeout: float | None = None,
        instructions: str = "",
        max_iterations: int | None = None,
        chat_session_id: str = "",
        parent_session: str = "",
        steering: SteeringChannel | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.task = task
        self.context = context
        # Agent Center: the profile's own instructions and step budget. Empty
        # and None keep the stock helper exactly as it was.
        self.instructions = instructions or ""
        self.max_iterations = max(1, min(24, int(max_iterations))) if max_iterations else None
        # The parent turn's channel, handed down by spawn_agent: holding its focus
        # while this helper runs is what lets a direction change reach the work the
        # user is watching instead of waiting for the parent's next round.
        self.steering = steering
        # Visibility wave: the run carries its own chat session and knows its
        # parent task. Both travel in the events and in the ledger so the surface
        # can build the chat live AND find it again after a restart — the same id
        # on both paths.
        self.chat_session_id = chat_session_id or subagent_history.chat_session_id_for(agent_id)
        self.parent_session = parent_session or ""
        # R36-S: model follows the ACTIVE engine when not pinned explicitly.
        if model:
            self.model = model
        else:
            from core.model_provider import get_active_provider

            self.model = get_active_provider().model
        # E5: agent profiles may narrow the tool set and the runtime budget.
        # None = stock behaviour (SUBAGENT_TOOL_WHITELIST / SUBAGENT_TIMEOUT).
        self.allowed_tools = allowed_tools
        self.timeout = timeout
        # Bridge may raise nothing — swallow per-event so a UI hiccup can
        # never kill the helper mid-run.
        self.on_event = on_event
        self.tool_calls: list[dict] = []

    def _emit(self, event: dict) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:
            logger.exception("subagent event bridge failed")

    def _system_prompt(self) -> str:
        role_line = f"You act as: {self.role}." if self.role else ""
        ctx = f"\nShared context from the main conversation:\n{self.context}" if self.context else ""
        own = f"\n\nAgent instructions:\n{self.instructions}" if self.instructions else ""
        return (
            "You are a focused subagent spawned by the main assistant to handle ONE "
            "delegated task. Work autonomously: use your read-only tools when they help, "
            "then produce a compact, factual final report (no preamble, no apologies). "
            f"{role_line}{ctx}{own}"
        )

    async def run(self) -> SubagentResult:
        from core.model_provider import build_provider_client
        from core.tools import execute_tool

        self._emit({
            "type": "subagent_started",
            "agent_id": self.agent_id,
            "role": self.role,
            "task": self.task,
            "model": self.model,
            "description": self.context,
            "chat_session_id": self.chat_session_id,
            "parent_session": self.parent_session,
        })
        subagent_history.begin(
            self.agent_id,
            role=self.role,
            task=self.task,
            description=self.context,
            model=self.model,
            chat_session_id=self.chat_session_id,
            parent_session=self.parent_session,
        )
        t_turn = time.perf_counter()

        tools = await _whitelisted_schemas()
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": self.task},
        ]
        client = build_provider_client()
        report = ""
        status = "ok"
        cancelled = False

        # Held for the whole run: see the constructor. A helper that dies still
        # releases it, or the parent turn would take no steer for the rest of it.
        if self.steering is not None:
            self.steering.enter_focus(self.agent_id)
        try:
            effective_timeout = float(self.timeout) if self.timeout else SUBAGENT_TIMEOUT
            effective_whitelist = set(self.allowed_tools) if self.allowed_tools else set(SUBAGENT_TOOL_WHITELIST)
            for _iteration in range(self.max_iterations or SUBAGENT_MAX_ITERATIONS):
                # The helper's own round boundary: the previous iteration's tool
                # results are in `messages`, so a direction change lands where the
                # parent turn's does — between rounds, never mid-call.
                taken = take_up(
                    messages,
                    boundary=_iteration + 1,
                    consumer=self.agent_id,
                    channel=self.steering,
                )
                if any(steer.stop for steer in taken):
                    status = "stopped"
                    report = "[subagent stopped on request before its next step]"
                    break
                response = await asyncio.wait_for(
                    client.chat(model=self.model, messages=messages, tools=tools, stream=False),
                    timeout=effective_timeout,
                )
                msg = getattr(response, "message", None)
                tool_calls = getattr(msg, "tool_calls", None) if msg is not None else None
                if not tool_calls:
                    report = str((msg.content if msg is not None else "") or "").strip()
                    break

                messages.append(msg)
                for call in tool_calls:
                    name = call.function.name
                    args = call.function.arguments or {}
                    args_preview = json.dumps(args, default=str)[:160]
                    self.tool_calls.append({"tool": name, "args_preview": args_preview[:120]})
                    t_tool = time.perf_counter()

                    # N24: the helper's call takes the same gate the main turn
                    # takes, and the answer carries its own record — exempt,
                    # approved or denied — so no helper call is a silent one.
                    from core.tools.chat_gate import gate_delegated_tool

                    if name not in effective_whitelist:
                        allowed = False
                        denial = f"[Tool '{name}' is not available to this subagent profile.]"
                        gate_note = (
                            f"[gate] subagent {self.agent_id}: {name} is outside this "
                            f"helper's whitelist."
                        )
                    else:
                        allowed, denial, gate_note = await gate_delegated_tool(
                            name, args, who=f"subagent {self.agent_id}"
                        )
                    self._emit({
                        "type": "subagent_tool",
                        "agent_id": self.agent_id,
                        "chat_session_id": self.chat_session_id,
                        "tool": name,
                        "args_preview": args_preview,
                        "gate": gate_note,
                    })
                    if not allowed:
                        messages.append({"role": "tool", "content": denial})
                        subagent_history.tool_call(
                            self.agent_id, name, args_preview, 0, gate=gate_note
                        )
                        continue
                    try:
                        result = await execute_tool(name, args)
                    except Exception as exc:  # noqa: BLE001 — tool errors feed back to the model
                        result = f"[tool-error: {exc}]"
                    messages.append({"role": "tool", "content": str(result)[:8000]})
                    subagent_history.tool_call(
                        self.agent_id, name, args_preview,
                        int((time.perf_counter() - t_tool) * 1000),
                        gate=gate_note,
                    )
            else:
                status = "step_limit"
                report = report or "[subagent reached its step limit without a final report]"
        except asyncio.CancelledError:
            # A stopped parent turn cancels its helpers. Without a record here the
            # entry stays "running" in the live registry for the rest of the
            # process, and the fleet paints a dead run as busy.
            cancelled = True
            status = "interrupted"
            report = "[subagent was cancelled before it finished]"
        except asyncio.TimeoutError:
            status = "timeout"
            report = f"[subagent timeout after {effective_timeout:.0f}s]"
        except Exception as exc:  # noqa: BLE001 — report engine failures as the result
            status = "error"
            report = f"[subagent error: {exc}]"
            logger.exception("subagent %s failed", self.agent_id)
        finally:
            if self.steering is not None:
                self.steering.leave_focus(self.agent_id)

        # P4-D: persistent completion record (timings + transcript) for
        # GET /api/subagents/<id>. Written before the done event so the frontend
        # poll sees the final record as soon as the activity closes.
        subagent_history.finish(
            self.agent_id,
            status=status,
            report=report or "[no report]",
            duration_ms=int((time.perf_counter() - t_turn) * 1000),
            transcript=_transcript(messages),
        )
        self._emit({
            "type": "subagent_done",
            "agent_id": self.agent_id,
            "chat_session_id": self.chat_session_id,
            "parent_session": self.parent_session,
            "status": status,
            "summary": report[:600],
            # The helper chat carries the full report length (same cap as the
            # ledger record); `summary` stays the short form of the activity.
            "report": report[: subagent_history.MAX_REPORT_CHARS],
        })
        if cancelled:
            raise asyncio.CancelledError()
        return SubagentResult(
            agent_id=self.agent_id, role=self.role, task=self.task,
            report=report or "[no report]", status=status, tool_calls=self.tool_calls,
        )


async def _whitelisted_schemas() -> list[dict]:
    """Schemas for the whitelist only — the model never sees more."""
    from core.tools.registry import get_tool_schemas

    wanted = set(SUBAGENT_TOOL_WHITELIST)
    return [s for s in get_tool_schemas() if s.get("function", {}).get("name") in wanted]


def _transcript(messages: list) -> list[dict]:
    """P4-D: compact role/text pairs for the detail tab (system stripped,
    pydantic-message objects tolerated)."""
    from core.subagent_history import MAX_TRANSCRIPT_CHARS

    out: list[dict] = []
    for m in messages[1:]:  # the system prompt is already in the record as task/model
        if isinstance(m, dict):
            role, content = m.get("role", ""), m.get("content", "")
        else:
            # provider objects (assistant without a role field) → 'assistant'
            role, content = getattr(m, "role", "") or "assistant", getattr(m, "content", "") or ""
        out.append({"role": str(role), "text": str(content)[:MAX_TRANSCRIPT_CHARS]})
    return out
