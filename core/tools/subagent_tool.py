"""``spawn_agent`` — native sub-agent delegation for the chat agent.

Leading agent frameworks all converge on the same primitive: the MAIN agent
decides autonomously to delegate a task to a helper (no slash command). One
call = one helper, one report. The helper follows the ACTIVE engine and
streams ``subagent_started/tool/done`` events into the chat, where the UI
renders a clickable SubAgent card with a live transcript (AgentPanel tab).
"""

from __future__ import annotations

import contextvars
import itertools
import time
import uuid
from collections.abc import Callable
from typing import Any

#: Stream bridge. server/routes/chat.py sets this per SSE request; core stays
#: transport-agnostic. Unset (CLI, tests) → events are simply dropped.
subagent_emit_var: contextvars.ContextVar[Callable[[dict], None] | None] = contextvars.ContextVar(
    "ephe_subagent_emit", default=None
)

_agent_seq = itertools.count(1)


def _bridge() -> Callable[[dict], None]:
    emit = subagent_emit_var.get()

    def _on_event(event: dict) -> None:
        if emit is None:
            return
        try:
            emit(event)
        except Exception:  # noqa: BLE001 — SSE hiccups must not kill the helper
            pass

    return _on_event


async def spawn_agent(description: str, prompt: str, subagent_type: str = "") -> str:
    """Delegate ONE task to a subagent and return its report.

    description — what the main agent tells the user it delegated (short).
    prompt      — the full self-contained task for the helper.
    subagent_type — optional label. Resolved against agent profiles
    (~/.ephe/agents/*.json + plugin bundles): a matching profile narrows the
    helper's tools/model/timeout. Unknown labels behave as the stock
    read-only generalist — never an error.
    """
    from core import subagent_history
    from core.subagent import Subagent
    from core.steering import current_channel
    from core.tools.session_ctx import get_current_session

    agent_id = f"subagent-{next(_agent_seq)}"
    # Visibility wave: the helper's own chat session. The agent_id counts
    # per process and is reused after a restart — as a session
    # key it is unusable, because two runs ended up with the same chat.
    # Therefore an additional run marker; agent_id stays as the label.
    chat_session_id = subagent_history.chat_session_id_for(agent_id, uuid.uuid4().hex[:8])
    # Core session context ('default' = CLI/run without a session): the parent
    # task that the helper leads back to.
    _origin = get_current_session()
    parent_session = "" if _origin == "default" else _origin
    role = (subagent_type or "general-purpose").strip() or "general-purpose"
    allowed_tools: list[str] | None = None
    timeout: float | None = None
    model: str | None = None
    instructions = ""
    max_iterations: int | None = None
    profile_id = ""
    try:
        from core import agent_profiles

        profile = agent_profiles.resolve_for_spawn(subagent_type)
        if profile:
            allowed_tools = list(profile["tools"])
            timeout = float(profile["timeout"])
            model = profile.get("model")
            instructions = str(profile.get("instructions") or "")
            max_iterations = profile.get("max_turns")
            profile_id = str(profile.get("id") or "")
    except Exception:  # noqa: BLE001 — profile problems never block delegation
        allowed_tools, timeout, model = None, None, None
        instructions, max_iterations, profile_id = "", None, ""
    # Steering: this turn's live channel, handed to the helper so a direction
    # change reaches the work the user is watching instead of waiting for the
    # parent's next round. Unset outside a chat turn (CLI, tests) — the helper
    # then runs exactly as before.
    _parent_channel = current_channel()
    started = time.perf_counter()
    runner = Subagent(
        agent_id=agent_id,
        role=role,
        task=prompt,
        model=model,
        context=description,
        on_event=_bridge(),
        allowed_tools=allowed_tools,
        timeout=timeout,
        instructions=instructions,
        max_iterations=max_iterations,
        chat_session_id=chat_session_id,
        parent_session=parent_session,
        steering=_parent_channel,
    )
    result = await runner.run()
    try:
        from core import agent_store

        agent_store.record_run(
            run_id=agent_id,
            agent_id=profile_id,
            agent_name=role,
            model=model,
            model_source="agent" if model else "global",
            source="spawn",
            status=result.status,
            duration_ms=int((time.perf_counter() - started) * 1000),
            tool_calls=len(result.tool_calls),
            prompt_chars=len(prompt),
            report_chars=len(result.report),
        )
    except Exception:  # noqa: BLE001 — a run record never fails the delegation
        pass
    header = (
        f"Subagent {agent_id} (role: {role}) finished with status '{result.status}'. "
        f"Tool calls: {len(result.tool_calls)}.\n\n"
    )
    return header + result.report


SPAWN_AGENT_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "spawn_agent",
        "description": (
            "Delegate ONE self-contained task to a subagent that runs in parallel "
            "context with read-only tools (web_search, read_file, list_directory, "
            "file_search, fetch_url, ...). Use when a task is independent, "
            "self-contained and would otherwise clutter the main thread — e.g. "
            "research, code exploration, evidence gathering. The subagent returns "
            "its full report as this tool's result. Do NOT use for tiny steps or "
            "for anything needing write/approval tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short label of the delegation, shown to the user (e.g. 'Research HTTP timeouts').",
                },
                "prompt": {
                    "type": "string",
                    "description": "The complete, self-contained task for the subagent. It cannot see this conversation — include every needed detail.",
                },
                "subagent_type": {
                    "type": "string",
                    "description": (
                        "Optional label. Built-in generalist or a user-defined agent "
                        "profile name (from ~/.ephe/agents or an installed plugin) — "
                        "a matching profile pins the helper's tools, model and timeout; "
                        "unknown labels run the stock read-only generalist."
                    ),
                },
            },
            "required": ["description", "prompt"],
        },
    },
}
