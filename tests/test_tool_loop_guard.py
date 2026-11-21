"""W7-2: the circling guard for the tool loop.

K2's reps ended without a final answer: rep 1 kept calling one invented
workspace root while its budget drained, and the repair budget never noticed
because successful reads elsewhere reset it. These tests pin the guard that
names the circling shape and stops on it, and they pin the line between
circling and a legitimate long task — a guard that cuts real work would be
worse than the budget burn it prevents.

The distinction the guard draws: working spends many rounds and fails a call
here and there, and a success on a target clears it. Circling fails one target
over and over with no success on it, or fails a run of results in a row.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat_tools import (
    CIRCLING_ERROR_RUN,
    CIRCLING_TARGET_REPEATS,
    _ToolLoopStallGuard,
    tool_call_target,
)
from core.loop_observability import LoopObserver, bind_observer, reset_observer

#: The root K2's rep 1 invented and then hit again and again.
INVENTED_ROOT = "runs/202612061012T0131-w4-60x3"

TOOL_ERROR = "[TOOL-ERROR] FileNotFoundError: no such file or directory"


def _make_response(content: str = "", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = msg
    return response


def _make_tool_call(name: str, arguments: dict):
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc = MagicMock()
    tc.function = func
    return tc


def _read(path: str):
    return _make_tool_call("read_file", {"path": path})


class _ScriptedClient:
    """client.chat hands out queued responses; the last one repeats."""

    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, **kwargs):  # noqa: ARG002
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    async def aclose(self):
        return None


class _OllamaProvider:
    provider = "ollama"


# The detector: what separates circling from working.


def test_a_long_working_run_is_never_cut():
    """GIVEN seventy successful reads and one stray miss that then succeeds
    WHEN each result passes the guard
    THEN nothing trips: many calls are not the signal, repeated failure is."""
    guard = _ToolLoopStallGuard()
    for i in range(70):
        assert guard.record("read_file", {"path": f"pkg/mod_{i}.py"}, is_error=False) is None
    assert guard.record("read_file", {"path": "pkg/gone.py"}, is_error=True) is None
    assert guard.record("read_file", {"path": "pkg/found.py"}, is_error=False) is None
    assert guard.consecutive_errors == 0
    assert guard.failed_targets == {}


def test_a_target_that_keeps_failing_trips_at_the_threshold():
    """GIVEN the K2 shape — one invented root hit with different file names
    WHEN the target has failed CIRCLING_TARGET_REPEATS times with no success
    THEN the guard names the repeated target rather than the call count."""
    guard = _ToolLoopStallGuard()
    trips = [
        guard.record("read_file", {"path": f"{INVENTED_ROOT}/kdoc_{i}.json"}, is_error=True)
        for i in range(CIRCLING_TARGET_REPEATS)
    ]
    assert trips[:-1] == [None] * (CIRCLING_TARGET_REPEATS - 1)
    stall = trips[-1]
    assert stall is not None
    assert stall.reason == "repeated_failing_target"
    assert stall.count == CIRCLING_TARGET_REPEATS
    assert stall.target == f"read_file:dir:{INVENTED_ROOT}"


def test_progress_on_other_targets_does_not_excuse_a_dead_one():
    """GIVEN the interleaving K2's rep 1 leaves — a successful read between the
    WHEN the same root keeps failing
    THEN the successes elsewhere do not reset it, and the guard still fires."""
    guard = _ToolLoopStallGuard()
    assert guard.record("read_file", {"path": f"{INVENTED_ROOT}/a.json"}, is_error=True) is None
    assert guard.record("read_file", {"path": "real/one.py"}, is_error=False) is None
    assert guard.record("read_file", {"path": f"{INVENTED_ROOT}/b.json"}, is_error=True) is None
    assert guard.record("read_file", {"path": "real/two.py"}, is_error=False) is None
    assert guard.record("read_file", {"path": f"{INVENTED_ROOT}/c.json"}, is_error=True) is None
    stall = guard.record("read_file", {"path": f"{INVENTED_ROOT}/d.json"}, is_error=True)
    assert stall is not None and stall.reason == "repeated_failing_target"


def test_a_run_of_errors_trips_across_different_targets():
    """GIVEN failures that never repeat a target but never stop either
    WHEN CIRCLING_ERROR_RUN results fail in a row
    THEN the guard names the run."""
    guard = _ToolLoopStallGuard()
    trips = [
        guard.record("read_file", {"path": f"probe{i}/x.txt"}, is_error=True)
        for i in range(CIRCLING_ERROR_RUN)
    ]
    assert trips[:-1] == [None] * (CIRCLING_ERROR_RUN - 1)
    stall = trips[-1]
    assert stall is not None and stall.reason == "error_run"
    assert stall.count == CIRCLING_ERROR_RUN


def test_the_target_identity_folds_a_directory_and_keeps_a_bare_value():
    """GIVEN path-shaped and value-shaped arguments
    WHEN their identity is derived
    THEN a path folds to its directory, a query or command stands verbatim, and
    a call with no recognized argument folds to the tool alone."""
    assert tool_call_target("read_file", {"path": "a/b/c.txt"}) == "read_file:dir:a/b"
    assert tool_call_target("read_file", {"path": "a/b/d.txt"}) == "read_file:dir:a/b"
    assert tool_call_target("read_file", {"path": "notes.txt"}) == "read_file:dir:notes.txt"
    assert tool_call_target("grep", {"pattern": "needle"}) == "grep:needle"
    assert tool_call_target("run_shell", {"command": "ls nope"}) == "run_shell:ls nope"
    assert tool_call_target("read_file", {}) == "read_file:<no-target>"
    assert tool_call_target("read_file", "not-a-dict") == "read_file:<no-target>"


# The stop reaches the user, the model, and the observer.


async def _read_tool_result(name, args, policy=None):  # noqa: ARG001
    """The invented root is missing; anything else reads fine."""
    path = args.get("path", "") if isinstance(args, dict) else ""
    return TOOL_ERROR if INVENTED_ROOT in path else "file contents"


@pytest.mark.asyncio
async def test_a_circling_turn_stops_with_a_named_reason():
    """GIVEN K2's rep-1 shape — one invented root failing while a real read
    succeeds in between, which resets the per-round repair budget
    WHEN the loop runs under a cap far larger than it will need
    THEN it stops early, the user sees the named reason, the observer records
    one stall, and neither the repair budget nor the cap ended the turn."""
    from core.chat import chat_with_tools

    def read_response(path):
        return _make_response(tool_calls=[_read(path)])

    # A faithful interleave: two failing rounds, a successful one that resets
    # the repair budget, then the failure again. The loop reaches round 5 only
    # because the repair budget alone cannot see this pattern.
    client = _ScriptedClient(
        [
            read_response(f"{INVENTED_ROOT}/a.json"),
            read_response(f"{INVENTED_ROOT}/b.json"),
            read_response("real/ok.py"),
            read_response(f"{INVENTED_ROOT}/c.json"),
            read_response(f"{INVENTED_ROOT}/d.json"),
        ]
    )
    observer = LoopObserver()
    chunks: list[str] = []
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(side_effect=_read_tool_result)
    ):
        answer = await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "read the run records"}],
            on_chunk=chunks.append,
            allowed_tool_names=["read_file"],
            max_tool_iterations=25,
            loop_observer=observer,
        )

    assert "Tool loop stopped early" in answer
    assert chunks and "Tool loop stopped early" in "".join(chunks)
    assert observer.counters.loop_stalled is True
    assert observer.counters.budget_exhausted is False
    stalls = [e for e in observer.events if e["event"] == "loop_stalled"]
    assert len(stalls) == 1
    assert stalls[0]["reason"] == "repeated_failing_target"
    assert stalls[0]["detail"] == f"read_file:dir:{INVENTED_ROOT} x{CIRCLING_TARGET_REPEATS}"
    # Four failures on the root across five rounds, none in a row: the guard
    # ends it at the fourth, well before the twenty-five-round cap.
    assert observer.counters.tool_rounds == 5


@pytest.mark.asyncio
async def test_the_reason_reaches_the_model_and_the_user():
    """GIVEN the loop driven directly on a circling target
    WHEN the guard trips
    THEN the reason is in the history the model would read and in the stream
    the user sees, and the loop reports the stop rather than the budget end."""
    from core.chat import _run_tool_loop

    client = _ScriptedClient(
        [
            _make_response(
                tool_calls=[
                    _read(f"{INVENTED_ROOT}/kdoc_b.json"),
                    _read(f"{INVENTED_ROOT}/kdoc_c.json"),
                ]
            )
        ]
    )
    messages: list = [{"role": "user", "content": "read the run records"}]
    observer = LoopObserver()
    token = bind_observer(observer)
    chunks: list[str] = []
    try:
        with patch("core.chat.execute_tool", new=AsyncMock(return_value=TOOL_ERROR)):
            iteration, streamed, response = await _run_tool_loop(
                client=client,
                provider=_OllamaProvider(),
                model="gemma4:12b",
                messages=messages,
                tools=[],
                response=_make_response(
                    tool_calls=[
                        _read(f"{INVENTED_ROOT}/kdoc_a.json"),
                        _read(f"{INVENTED_ROOT}/kdoc_d.json"),
                    ]
                ),
                detection_streamed=False,
                on_chunk=chunks.append,
                on_thinking=None,
                on_tool_start=None,
                on_tool_done=None,
                on_phase=None,
                on_shell_confirm=None,
                on_tool_confirm=None,
                approval_policy=None,
                budget_cap=25,
                turn_id="t-stall",
            )
    finally:
        reset_observer(token)

    note = response.message.content
    assert "Tool loop stopped early" in note
    assert any(m.get("role") == "system" and m.get("content") == note for m in messages)
    assert chunks == [note]
    # The note went out live, so the caller must not emit it a second time.
    assert streamed is True
    # The fourth failure lands in the second round; two calls a round get there
    # before the round-counting repair budget can.
    assert iteration == 2
    assert observer.counters.loop_stalled is True
    assert observer.counters.budget_exhausted is False
    assert [e["event"] for e in observer.events if e["event"] == "loop_stalled"] == ["loop_stalled"]


@pytest.mark.asyncio
async def test_a_working_turn_never_sets_the_stall_flag():
    """GIVEN a turn whose reads succeed
    WHEN the loop runs
    THEN the guard stays silent — neither the flag nor the event appears."""
    from core.chat import chat_with_tools

    client = _ScriptedClient(
        [
            _make_response(tool_calls=[_read("real/a.py"), _read("real/b.py")]),
            _make_response(content="done"),
        ]
    )
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="file contents")
    ):
        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "read two files"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            max_tool_iterations=25,
            loop_observer=observer,
        )

    assert observer.counters.loop_stalled is False
    assert [e for e in observer.events if e["event"] == "loop_stalled"] == []
