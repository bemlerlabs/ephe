"""core/_chat_tools_results.py — what the loop reads in a tool result, and the stop a bad run earns.

``core/chat_tools.py`` is the tool loop: the call, its approval gate, the round budget and
the turn's own bookkeeping. Two jobs sit beside it that are not about the call at all, and
they share one subject — the result that comes back.

What a result *is*: output from outside the machine — a web fetch or search, a remote MCP
tool, a ``tool_call`` forwarding to either — is third-party text an attacker can shape
(docs/SECURITY_THREAT_MODEL.md §6, E2). It reaches the model fenced as untrusted data, so it
can be read as data and never as an instruction. Local output passes through unchanged.

What a *run* of results means: working and circling look alike in call counts and differ in
what their failures do. The guard here names the difference and ends the turn on it, and the
loop's two early stops — circling and a steer's boundary — answer in the same synthetic shape.

Both blocks moved byte-identical out of ``core/chat_tools.py`` on 2026-10-14, when that file
stood at 854 lines against the frozen 400-line cap. The loop stayed where it was and imports
these names back, so every ``core.chat_tools`` name a caller or a test uses is the same object
as before.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from core.channels.injection_guard import (
    UNTRUSTED_DATA_OPEN,
    wrap_untrusted_data,
)
from core.loop_observability import note_stall
from core.steering import Steer

# E2: external tool output enters the loop as untrusted data.
# A web fetch/search or a remote MCP tool returns third-party text an attacker
# can shape (docs/SECURITY_THREAT_MODEL.md §6, E2). It reaches the model fenced
# into the channel guard's untrusted-data block — available as data, never read
# as an instruction. The fence is reused from core.channels.injection_guard, not
# reimplemented here.

#: Web tools whose output is external content.
WEB_UNTRUSTED_TOOLS: frozenset[str] = frozenset({"fetch_url", "web_search"})

#: The discovery meta tool that forwards to a tool named in its own arguments.
_META_FORWARD_TOOL = "tool_call"

#: How many tool_call forwards to walk before the chain is read as unresolved.
#: tool_call recurses without a depth bound, so the fence walk needs its own cap;
#: a chain that runs past it cannot be attributed to a named tool.
_META_FORWARD_LIMIT = 16

#: Returned when a tool_call chain runs past ``_META_FORWARD_LIMIT`` without reaching
#: a named tool. Not a real tool name; callers read any non-None origin as external,
#: so an unresolvable chain fails closed — fenced, never passed through.
_UNRESOLVED_ORIGIN = "<unresolved tool_call chain>"

#: Stands in for an external result's summary in the evidence block. A web page's
#: first line is attacker-chosen and must not land in a system message.
_UNTRUSTED_EVIDENCE = "external content, fenced as untrusted data"


def is_untrusted_tool(name: str) -> bool:
    """True when a tool returns third-party content (web fetch/search or MCP)."""
    if not name:
        return False
    if name in WEB_UNTRUSTED_TOOLS:
        return True
    from core.tools.mcp_client import is_mcp_tool

    return is_mcp_tool(name)


def untrusted_origin_tool(name: str, args: object) -> str | None:
    """The external tool behind a call, following a tool_call forward.

    tool_call executes a tool named in its own arguments, so its result carries
    that tool's origin; without this the meta router would be a way around the fence.
    The forward is walked to the first non-meta name, bounded by ``_META_FORWARD_LIMIT``.
    A chain still forwarding at the bound is read as ``_UNRESOLVED_ORIGIN`` (fenced);
    a chain that ends on a local name, or stops without a named inner tool, is ``None``.
    """
    cur_name = name
    cur_args: object = args
    if isinstance(cur_args, str):
        try:
            cur_args = json.loads(cur_args)
        except (ValueError, TypeError):
            cur_args = {}
    if not isinstance(cur_args, dict):
        cur_args = {}
    hops = 0
    while True:
        if not cur_name:
            return None
        if is_untrusted_tool(cur_name):
            return cur_name
        if cur_name != _META_FORWARD_TOOL:
            return None
        if hops >= _META_FORWARD_LIMIT:
            return _UNRESOLVED_ORIGIN
        inner = cur_args.get("name")
        if not isinstance(inner, str):
            return None
        inner_args = cur_args.get("arguments")
        if isinstance(inner_args, str):
            try:
                inner_args = json.loads(inner_args)
            except (ValueError, TypeError):
                inner_args = {}
        cur_name = inner
        cur_args = inner_args if isinstance(inner_args, dict) else {}
        hops += 1


def fence_tool_output(name: str, args: object, result: object) -> str:
    """Fences an external-origin tool result as untrusted data.

    Local output passes through unchanged. A result that already carries the
    fence (an MCP tool reached through tool_call, or a block whose tail the cap
    cut) is re-fenced once: the guard's wrap is idempotent and rebalances a
    broken pair. A failure from an external tool is fenced like its output:
    the provider status line and the error text behind it came from outside,
    so the engine must not read them as its own voice (owner decision
    2026-10-25).
    """
    text = result if isinstance(result, str) else str(result)
    if not text:
        return text
    if untrusted_origin_tool(name, args) is None and UNTRUSTED_DATA_OPEN not in text:
        return text
    return wrap_untrusted_data(text)


#: Circling guard: repeated tool-result errors that read as an agent stuck on
#: failures. A working turn fails a call here and there and keeps moving. The
#: shape K2's rep 1 left failed one invented workspace root again and again,
#: with a successful read elsewhere in between; the other reps failed whole
#: runs of results.
CIRCLING_ERROR_RUN = 5

#: How many times one target may fail, with no success on it in between, before
#: its retries are read as circling rather than working.
CIRCLING_TARGET_REPEATS = 4

#: Machine names for the two signals; both reach the user and the observer.
_STALL_TARGET_REPEAT = "repeated_failing_target"
_STALL_ERROR_RUN = "error_run"

#: Argument keys that name what a path-shaped call is aimed at.
_PATH_ARG_KEYS: tuple[str, ...] = ("path", "file", "directory", "dir")

#: Argument keys whose value is the target verbatim (a query, a command, a URL).
_VALUE_ARG_KEYS: tuple[str, ...] = ("pattern", "query", "command", "url", "name")


def tool_call_target(name: str, args: object) -> str:
    """A stable identity for what a call was aimed at, for the circling guard.

    The identity is deliberately coarser than the call: seven ``read_file``
    misses on different files under one nonexistent root are one target, not
    seven, because the thing the agent keeps reaching for is the root. A path
    without a directory keeps its value, and a call with no recognized argument
    folds to the tool alone.
    """
    data = args if isinstance(args, dict) else {}
    for key in _PATH_ARG_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip().replace("\\", "/")
            parent = text.rsplit("/", 1)[0] if "/" in text else text
            return f"{name}:dir:{parent}"
    for key in _VALUE_ARG_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return f"{name}:{value.strip()}"
    return f"{name}:<no-target>"


@dataclass(frozen=True)
class _Stall:
    """A circling stop: the named reason, the target it proved, and the count."""

    reason: str
    target: str = ""
    count: int = 0


@dataclass(frozen=True)
class _StallMessage:
    content: str
    tool_calls: tuple = ()


@dataclass(frozen=True)
class _StallResponse:
    message: _StallMessage


class _ToolLoopStallGuard:
    """Notices a tool loop circling on its own errors instead of working.

    Working and circling look alike in raw call counts: a long task spends many
    rounds too. They differ in what the failures do. Working fails a call and
    moves on, and any success on a target clears it. Circling fails one target
    over and over with no success on it, or fails a run of results in a row, and
    then keeps going. Both leave the agent without the result it is reaching
    for, which is exactly when naming the reason beats spending the rest of the
    budget.
    """

    def __init__(
        self,
        *,
        error_run: int = CIRCLING_ERROR_RUN,
        target_repeats: int = CIRCLING_TARGET_REPEATS,
    ) -> None:
        self.error_run = int(error_run)
        self.target_repeats = int(target_repeats)
        self.consecutive_errors = 0
        self.failed_targets: dict[str, int] = {}

    def record(self, name: str, args: object, *, is_error: bool) -> _Stall | None:
        """Count one tool result; return the stall it proves, or None.

        The first signal to fire wins, so a turn reports one named reason rather
        than a pile. A success clears both the consecutive run and its own
        target's failure count -- that is what keeps a legitimate long task
        uncut, since any progress on a target answers the question the guard is
        asking.
        """
        target = tool_call_target(name, args)
        if not is_error:
            self.consecutive_errors = 0
            self.failed_targets.pop(target, None)
            return None
        self.consecutive_errors += 1
        count = self.failed_targets.get(target, 0) + 1
        self.failed_targets[target] = count
        if count >= self.target_repeats:
            return _Stall(_STALL_TARGET_REPEAT, target=target, count=count)
        if self.consecutive_errors >= self.error_run:
            return _Stall(_STALL_ERROR_RUN, count=self.consecutive_errors)
        return None


def _tool_loop_stall_note(stall: _Stall) -> str:
    """The named reason the circling guard ended the turn, as user-facing text."""
    if stall.reason == _STALL_TARGET_REPEAT:
        why = f"the same target {stall.target} failed {stall.count} times with no result"
    else:
        why = f"{stall.count} tool results failed in a row"
    return (
        f"[Ephe] Tool loop stopped early: {why}. "
        "Task unfinished (no final answer). Narrow the task or send a corrected "
        "next step to continue."
    )


def _finalize_stalled(
    *,
    stall: _Stall,
    iteration: int,
    messages: list,
    on_chunk: Callable[[str], None] | None,
) -> tuple[int, bool, object]:
    """End the turn on a named circling reason instead of a spent budget.

    The note reaches the user through the chat stream and the model through the
    history, so a later round inherits the reason instead of repeating the dead
    calls. ``detection_streamed`` is returned True because the note has already
    gone out live; the caller must not emit it a second time.
    """
    note = _tool_loop_stall_note(stall)
    detail = f"{stall.target} x{stall.count}" if stall.target else f"x{stall.count}"
    note_stall(stall.reason, detail)
    messages.append({"role": "system", "content": note})
    if on_chunk is not None:
        on_chunk(note)
    return iteration, True, _StallResponse(message=_StallMessage(content=note))


def _steer_stop_note(steer: Steer, boundary: int) -> str:
    """What the user reads when a steer ended the turn, and what the model keeps.

    The boundary is named because it is the promise: nothing was cut off
    mid-write. A reader who cannot check that has to take the sentence on trust.
    The note does not claim the turn produced nothing — a streaming engine may
    already have put part of an answer on screen before the boundary.
    """
    who = "the user" if steer.actor == "user" else f"the {steer.actor}"
    return (
        f"[Ephe] Stopped at {who}'s request after tool round {boundary}. "
        "No tool call was cut off mid-write; this turn ends here and is unfinished."
    )


def _finalize_steer_stop(
    *,
    steer: Steer,
    boundary: int,
    messages: list,
    on_chunk: Callable[[str], None] | None,
) -> tuple[int, bool, object]:
    """End the turn at a round boundary because a steer asked for it.

    Same shape as the circling stop — a synthetic response that carries no tool
    calls and whose text has already gone out live — so both stops reach the
    caller the same way and neither is re-emitted.
    """
    note = _steer_stop_note(steer, boundary)
    messages.append({"role": "system", "content": note})
    if on_chunk is not None:
        on_chunk(note)
    return boundary, True, _StallResponse(message=_StallMessage(content=note))
