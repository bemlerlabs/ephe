"""The identity a tool call carries through a turn.

The loop's own id is an audit stamp (turn, round, position); the engine's id is
what a ``role: "tool"`` message has to answer. Kept apart from the detection
loop so both readers share one definition of "the same call".
"""

from __future__ import annotations

import uuid
from collections.abc import Callable


def _call_id(turn_id: str, idx: int, round_no: int = 0) -> str:
    """Ephe's own identifier for a tool call: turn, round, position.

    The plain loop index ("0") was no identifier: twenty turns have a
    call number zero. With only the turn prefix, two tool rounds of one turn
    still produced the same id for their first call — the round belongs in the
    identity because that is the scope a result answers.
    """
    if turn_id:
        return f"{turn_id[:8]}-r{round_no}-{idx}"
    return f"c{idx}-{uuid.uuid4().hex[:6]}"


def _parse_tool_calls(
    response: object,
    turn_id: str,
    on_tool_start: Callable | None,
    round_no: int = 0,
) -> tuple[list[tuple[int, str, dict]], dict[int, str]]:
    """Parse ``response.message.tool_calls`` index-stable into (idx, name, args).

    The identifier is created once per call: turn, round and position, with a
    random fallback when ``turn_id`` is empty, so start and done stamps for the
    same call always carry the same id (W15-P3 spans) and two rounds cannot
    collide.
    """
    parsed: list[tuple[int, str, dict]] = []
    call_ids: dict[int, str] = {}
    for idx, tool_call in enumerate(response.message.tool_calls):
        if isinstance(tool_call, dict):
            function = tool_call.get("function") or tool_call
            name = str(function.get("name", ""))
            args = function.get("arguments") or {}
        else:
            function = tool_call.function
            name = str(tool_call.function.name)
            args = tool_call.function.arguments or {}
        parsed.append((idx, name, args))
        call_ids[idx] = _call_id(turn_id, idx, round_no)
        if on_tool_start is not None:
            on_tool_start(name, args, call_ids[idx])
    return parsed, call_ids


def engine_tool_call_ids(response: object) -> dict[int, str]:
    """The ids the engine assigned, by call index, for the tool messages that answer them.

    The loop's own ids are audit stamps. The engine's ids are what a `role: "tool"`
    message has to answer, and relying on positional correlation alone is what let a
    result reach an engine without its block (measured 2026-10-17).
    """
    out: dict[int, str] = {}
    calls = getattr(getattr(response, "message", None), "tool_calls", None) or []
    for idx, call in enumerate(calls):
        call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
        if call_id:
            out[idx] = str(call_id)
    return out
