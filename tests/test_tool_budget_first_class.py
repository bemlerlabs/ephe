"""The tool budget as a first-class turn limit.

A turn runs under one cap: the casual default, the coding class at 40, or a caller's
own number, all clamped to the hard ceiling by ``core.chat.clamp_tool_budget``. What
these tests pin is that the number is honoured and NAMED — how many rounds the turn
spent against its cap, and which reason ended it. The reason is the part a round count
cannot carry: a turn that answers on its last allowed round reaches the same count as
one the cap cut off, so a caller reading the count alone reports a finished turn as an
exhausted budget, and a circling stop as a spent one.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat_context import _budget_exhausted_note
from core.chat_tools import (
    CIRCLING_TARGET_REPEATS,
    _ToolLoopStallGuard,
    _tool_loop_stall_note,
)
from core.loop_observability import LoopObserver

#: A workspace root no read can hit, so every call under it fails the same way.
MISSING_ROOT = "runs/202612061012T0131-w4-60x3"
TOOL_ERROR = "[TOOL-ERROR] FileNotFoundError: no such file or directory"


def _response(content: str = "", tool_calls=None):
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    message.thinking = None
    response = MagicMock()
    response.message = message
    return response


def _read(path: str):
    function = MagicMock()
    function.name = "read_file"
    function.arguments = {"path": path}
    call = MagicMock()
    call.function = function
    return call


class _ScriptedClient:
    """client.chat hands out queued responses; the last one repeats."""

    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, **kwargs):  # noqa: ARG002
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    async def aclose(self):
        return None


async def _turn(client, observer, budget, chunks=None, tool_result="file contents"):
    """Drive one turn of the shipped surface with a scripted engine."""
    from core.chat import chat_with_tools

    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value=tool_result)
    ):
        return await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "work the task"}],
            on_chunk=(chunks.append if chunks is not None else (lambda c: None)),
            allowed_tool_names=["read_file"],
            max_tool_iterations=budget,
            loop_observer=observer,
        )


@pytest.mark.asyncio
async def test_an_answer_on_the_last_allowed_round_is_not_a_spent_budget():
    """GIVEN a cap of 3 and a model that answers after its third tool round
    WHEN the turn ends
    THEN the loop names it an answer, the budget flag stays clear, and the final
    answer reaches the user instead of the exhaustion note."""
    client = _ScriptedClient(
        [
            _response(tool_calls=[_read("a.py")]),
            _response(tool_calls=[_read("b.py")]),
            _response(tool_calls=[_read("c.py")]),
            _response(content="all three files are read"),
        ]
    )
    observer = LoopObserver()
    answer = await _turn(client, observer, budget=3)

    assert answer == "all three files are read"
    assert observer.counters.tool_rounds == 3
    assert observer.counters.budget_cap == 3
    assert observer.counters.stop_reason == "answer"
    assert observer.counters.budget_exhausted is False
    assert _budget_exhausted_note(3) not in answer
    assert "loop_stop" not in [event["event"] for event in observer.events]


@pytest.mark.asyncio
async def test_a_cap_that_binds_the_turn_is_named_with_its_round_count():
    """GIVEN a cap of 3 and a model that still asks for tools on round 3
    WHEN the turn ends
    THEN the budget is the named reason, the counters report the rounds spent
    against the cap, and the answer carries the cap number."""
    client = _ScriptedClient(
        [
            _response(tool_calls=[_read("a.py")]),
            _response(tool_calls=[_read("b.py")]),
            _response(tool_calls=[_read("c.py")]),
            _response(tool_calls=[_read("d.py")]),
            _response(content="state reached so far"),
        ]
    )
    observer = LoopObserver()
    answer = await _turn(client, observer, budget=3)

    assert observer.counters.budget_exhausted is True
    assert observer.counters.stop_reason == "budget"
    assert observer.counters.tool_rounds == 3
    assert observer.counters.budget_cap == 3
    assert observer.counters.rounds_remaining == 0
    assert _budget_exhausted_note(3) in answer
    events = [event["event"] for event in observer.events]
    assert events.count("loop_stop") == 1
    # The budget event and the turn close stay the last two lines, as before.
    assert events[-2:] == ["budget_exhausted", "loop_turn"]


@pytest.mark.asyncio
async def test_a_circling_stop_on_the_cap_round_is_not_a_spent_budget():
    """GIVEN a cap of 2 and a model that keeps failing one target
    WHEN the guard trips exactly on the cap round
    THEN the turn is named a stall, the budget flag stays clear, and no budget
    note reaches the answer."""
    client = _ScriptedClient(
        [
            _response(
                tool_calls=[
                    _read(f"{MISSING_ROOT}/a.json"),
                    _read(f"{MISSING_ROOT}/b.json"),
                ]
            ),
        ]
    )
    observer = LoopObserver()
    chunks: list[str] = []
    answer = await _turn(client, observer, budget=2, chunks=chunks, tool_result=TOOL_ERROR)

    # The note the same signal produces, built from the guard rather than spelled here.
    guard = _ToolLoopStallGuard()
    stall = None
    for index in range(CIRCLING_TARGET_REPEATS):
        stall = guard.record(
            "read_file", {"path": f"{MISSING_ROOT}/f{index}.json"}, is_error=True
        )
    expected = _tool_loop_stall_note(stall)

    assert observer.counters.loop_stalled is True
    assert observer.counters.stop_reason == "stall"
    assert observer.counters.budget_exhausted is False
    assert observer.counters.tool_rounds == 2
    assert observer.counters.tool_rounds == observer.counters.budget_cap
    assert _budget_exhausted_note(2) not in answer
    assert expected in answer
    assert chunks == [expected]
