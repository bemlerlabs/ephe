"""
◑ Ephe – Swarm Engine

Multi-agent pipeline that distributes a task across specialized LLM agents:

    /swarm <task>

    ┌──────────────┐
    │   PLANER     │  the chosen tag: breaks the task into subtasks
    └──────┬───────┘
           │ N subtasks
    ┌──────▼─────────────────────────────┐
    │          asyncio.gather()           │   ← PARALLEL
    │  Agent1    Agent2    Agent3 ...     │
    └──────┬─────────────────────────────┘
           │ N partial results
    ┌──────▼───────┐
    │  SYNTHESIZER │  merges everything into one coherent answer
    └──────────────┘

Design rules (same as chat.py):
- Pure async Python, no Textual imports
- on_progress callback for streaming UI updates
- Raises OllamaNotReachableError / OllamaModelNotFoundError as needed

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable

import ollama

from core.chat import OllamaNotReachableError

# Max parallel specialist agents – optimized for 12B (~4B active params, ~3GB each)
MAX_SPECIALISTS = 3


# Prompts

PLANNER_SYSTEM = """\
You are a task planner. Given a task, break it into 2-4 clear, independent subtasks.
Return ONLY a JSON array of strings. No explanation, no markdown, just JSON.
Example: ["Design the data model", "Write the API endpoints", "Add error handling"]
"""

SPECIALIST_SYSTEM = """\
You are a specialist agent. Complete the given subtask concisely and precisely.
Focus only on your assigned subtask. Be direct and practical.
"""

SYNTHESIZER_SYSTEM = """\
You are a synthesis agent. Combine multiple specialist outputs into one coherent,
well-structured response. Avoid duplication. Be clear and actionable.
"""


# Helpers

def _make_client() -> ollama.AsyncClient:
    return ollama.AsyncClient()


def _wrap_exc(exc: Exception) -> Exception:
    """Convert low-level connection errors to our custom exceptions."""
    msg = str(exc).lower()
    if any(k in msg for k in ("connection", "refused", "socket", "connect")):
        return OllamaNotReachableError()
    if "not found" in msg or "does not exist" in msg:
        return exc  # let caller extract model name
    return exc


async def _call_model(
    system: str,
    user: str,
    model: str,
    use_tools: bool = False,
) -> str:
    """Single non-streaming model call. Returns the response text.

    Args:
        system:    System prompt
        user:      User message
        model:     Ollama model name
        use_tools: If True, passes tool schemas and executes tool calls.
    """
    from core.tools import get_tool_schemas, execute_tool

    client = _make_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: dict = {"model": model, "messages": messages, "stream": False}
    if use_tools:
        # Wave 3 only covered the main path: a specialist got the full
        # landscape (66 tools, ~4 400 tokens more than needed). The same
        # core + the discovery meta-tools reach the rare generators
        # on demand — here too.
        from core.tools.discovery import CORE_TOOLS

        kwargs["tools"] = [
            tool
            for tool in get_tool_schemas()
            if tool.get("function", {}).get("name") in CORE_TOOLS
        ]

    try:
        response = await asyncio.wait_for(
            client.chat(**kwargs),
            timeout=60.0,
        )

        # If LLM returned tool calls, execute them and feed results back
        tool_calls = getattr(response.message, "tool_calls", None)
        if use_tools and tool_calls:
            messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
            for tc in tool_calls:
                fn_name = tc.function.name
                fn_args = tc.function.arguments or {}
                # Security: swarm agents (autonomous, no interactive
                # approval gate) may not execute shell commands —
                # consistent with core/swarm_v2.py.
                if fn_name == "run_shell":
                    result = "[swarm agents may not execute shell commands.]"
                else:
                    # N24: the same gate the main turn passes, and its answer is
                    # the record — a swarm agent's mutating call is never silent.
                    from core.tools.chat_gate import gate_delegated_tool

                    allowed, denial, _gate_note = await gate_delegated_tool(
                        fn_name, fn_args, who="swarm agent"
                    )
                    if not allowed:
                        result = denial
                    else:
                        try:
                            result = await execute_tool(fn_name, fn_args)
                        except Exception as e:
                            result = f"[tool-error: {e}]"
                messages.append({"role": "tool", "content": str(result)})

            # Second call to synthesize tool results
            followup = await asyncio.wait_for(
                client.chat(model=model, messages=messages, stream=False),
                timeout=45.0,
            )
            return str(followup.message.content or "").strip()

        return str(response.message.content or "").strip()
    except Exception as exc:
        raise _wrap_exc(exc) from exc


# Core pipeline

async def _plan(task: str, model: str) -> list[str]:
    """
    Step 1: Planner – break the task into subtasks.
    Returns a list of subtask strings (2–4 items).
    Falls back to [task] if parsing fails (fail-safe).
    """
    raw = await _call_model(PLANNER_SYSTEM, task, model)

    # Try to extract JSON array
    try:
        # Handle model wrapping JSON in markdown code block
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            subtasks = json.loads(match.group())
            if isinstance(subtasks, list) and len(subtasks) > 0:
                return [str(s) for s in subtasks[:MAX_SPECIALISTS]]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: treat whole response as single task
    return [task]


async def _run_specialist(
    subtask: str,
    original_task: str,
    model: str,
    index: int,
    on_progress: Callable[[str], None] | None,
) -> str:
    """
    Step 2: Specialist – handle one subtask.
    Calls on_progress with live status text.
    """
    if on_progress:
        on_progress(f"  [{index+1}] {subtask[:60]}…")

    context = f"Main task: {original_task}\n\nYour subtask: {subtask}"
    result = await _call_model(SPECIALIST_SYSTEM, context, model, use_tools=True)

    if on_progress:
        on_progress(f"  [{index+1}] ✓ done")

    return result


async def _synthesize(
    task: str,
    subtasks: list[str],
    results: list[str],
    model: str,
) -> str:
    """
    Step 3: Synthesizer – combine specialist outputs into final response.
    """
    parts = [f"Original task: {task}\n"]
    for i, (subtask, result) in enumerate(zip(subtasks, results), 1):
        parts.append(f"Subtask {i}: {subtask}\nResult:\n{result}")

    combined = "\n\n---\n\n".join(parts)
    return await _call_model(SYNTHESIZER_SYSTEM, combined, model)


# Public API

async def run_swarm(
    *,
    task: str,
    model: str,
    on_progress: Callable[[str], None] | None = None,
) -> SwarmResult:
    """
    Run the full 3-stage swarm pipeline.

    Args:
        task:        The user's task / question
        model:       Ollama model to use for all agents
        on_progress: Called with status strings throughout execution

    Returns:
        SwarmResult with subtasks, partial results, and final synthesis
    """
    if on_progress:
        on_progress("🌲 Swarm started — the planner is analysing the task…")

    # Stage 1: Plan
    subtasks = await _plan(task, model)

    if on_progress:
        on_progress(
            f"📋 {len(subtasks)} subtasks detected:\n"
            + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(subtasks))
        )
        on_progress(f"\n⚡ {len(subtasks)} agents start in parallel…")

    # Stage 2: Run specialists in parallel
    specialist_coros = [
        _run_specialist(subtask, task, model, i, on_progress)
        for i, subtask in enumerate(subtasks)
    ]
    partial_results: list[str] = list(await asyncio.gather(*specialist_coros))

    if on_progress:
        on_progress("\n🔗 Synthesizer is merging the results…")

    # Stage 3: Synthesize
    final = await _synthesize(task, subtasks, partial_results, model)

    return SwarmResult(
        task=task,
        subtasks=subtasks,
        partial_results=partial_results,
        final=final,
    )


class SwarmResult:
    """Holds the complete output of a swarm run."""

    def __init__(
        self,
        task: str,
        subtasks: list[str],
        partial_results: list[str],
        final: str,
    ) -> None:
        self.task = task
        self.subtasks = subtasks
        self.partial_results = partial_results
        self.final = final

    def __repr__(self) -> str:
        return (
            f"SwarmResult(subtasks={len(self.subtasks)}, "
            f"final_len={len(self.final)})"
        )
