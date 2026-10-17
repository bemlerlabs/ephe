"""W1-7: tool-budget and compaction counters of the agent loop.

The loop is the only place that knows how many tool rounds a turn spent and
whether its history had to be trimmed. These tests read those counters back from
the same turn: units for the observer, a real log line for the event shape, and
scripted turns through ``chat_with_tools``: the budget end, the plain completion,
a forced window trim, a failing turn that still has to close its observer, and a
turn that supplies none (the default observer the loop builds itself).
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.loop_observability import (
    LoopCounters,
    LoopObserver,
    bind_observer,
    current_observer,
    note_budget_exhausted,
    note_compaction,
    note_tool_round,
    note_turn_end,
    reset_observer,
)


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


def _read_call_response():
    return _make_response(tool_calls=[_make_tool_call("read_file", {"path": "notes.txt"})])


class _ScriptedClient:
    """client.chat hands out queued responses; the last one repeats."""

    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, **kwargs):  # noqa: ARG002
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    async def aclose(self):
        return None


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


# Counters


def test_counters_start_empty():
    counters = LoopCounters(budget_cap=5)
    assert counters.tool_rounds == 0
    assert counters.rounds_remaining == 5
    assert counters.budget_exhausted is False
    assert counters.as_dict()["compaction_events"] == 0


def test_set_budget_cap_seeds_counters():
    observer = LoopObserver()
    observer.set_budget_cap(7)
    assert observer.budget_cap == 7
    assert observer.counters.budget_cap == 7


def test_note_tool_round_counts_and_keeps_the_high_water_mark():
    observer = LoopObserver(budget_cap=3)
    observer.note_tool_round(1)
    observer.note_tool_round(2)
    assert observer.counters.tool_rounds == 2
    assert observer.counters.rounds_remaining == 1
    assert [e["event"] for e in observer.events] == ["tool_round", "tool_round"]


def test_note_compaction_of_zero_counts_nothing():
    observer = LoopObserver()
    assert observer.note_compaction("window", 0) is None
    assert observer.counters.compaction_events == 0
    assert observer.events == []


def test_note_compaction_accumulates_dropped_messages():
    observer = LoopObserver()
    observer.note_compaction("window", 3)
    observer.note_compaction("history", 2)
    assert observer.counters.compaction_events == 2
    assert observer.counters.messages_dropped == 5
    assert observer.events[-1]["source"] == "history"


def test_note_budget_exhausted_flags_the_counter():
    observer = LoopObserver(budget_cap=4)
    observer.note_budget_exhausted()
    assert observer.counters.budget_exhausted is True
    assert observer.counters.as_dict()["budget_exhausted"] is True


def test_note_turn_end_appends_a_summary_event():
    observer = LoopObserver(budget_cap=2)
    observer.note_turn_end()
    assert observer.events[-1]["event"] == "loop_turn"
    assert "wall_ms" in observer.events[-1]


# Context binding


def test_module_notes_are_a_noop_without_an_observer():
    note_tool_round(1)
    note_compaction("window", 4)
    note_budget_exhausted()
    note_turn_end()
    assert current_observer() is None


def test_binding_routes_notes_to_that_observer_and_reset_clears_it():
    observer = LoopObserver(budget_cap=3)
    token = bind_observer(observer)
    try:
        note_tool_round(2)
        note_compaction("window", 1)
        assert current_observer() is observer
        assert observer.counters.tool_rounds == 2
        assert observer.counters.compaction_events == 1
    finally:
        reset_observer(token)
    assert current_observer() is None


# Event shape


def test_tool_round_event_is_a_structured_json_line():
    handler = _Capture()
    logger = logging.getLogger("ephe.loop")
    logger.addHandler(handler)
    try:
        observer = LoopObserver(budget_cap=3, turn_id="t-9")
        observer.note_tool_round(1)
    finally:
        logger.removeHandler(handler)

    round_lines = [line for line in handler.lines if json.loads(line)["event"] == "tool_round"]
    assert round_lines
    record = json.loads(round_lines[0])
    assert record["scope"] == "loop"
    assert record["turn_id"] == "t-9"
    assert record["round"] == 1
    assert record["budget_cap"] == 3
    assert record["rounds_remaining"] == 2


# Scripted turns


@pytest.mark.asyncio
async def test_budget_exhaustion_is_counted_and_flagged():
    from core.chat import chat_with_tools

    client = _ScriptedClient([_read_call_response()] * 4 + [_make_response(content="state summary")])
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "arbeite alles ab"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            max_tool_iterations=3,
            loop_observer=observer,
        )

    assert observer.counters.tool_rounds == 3
    assert observer.counters.budget_exhausted is True
    assert observer.counters.compaction_events == 0
    events = [e["event"] for e in observer.events]
    assert events.count("tool_round") == 3
    assert events[-2:] == ["budget_exhausted", "loop_turn"]


@pytest.mark.asyncio
async def test_plain_completion_counts_one_round_and_no_budget_end():
    from core.chat import chat_with_tools

    client = _ScriptedClient([_read_call_response(), _make_response(content="fertig")])
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        answer = await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "lies notes.txt"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            loop_observer=observer,
        )

    assert answer == "fertig"
    assert observer.counters.tool_rounds == 1
    assert observer.counters.budget_exhausted is False
    assert observer.counters.compaction_events == 0
    assert [e["event"] for e in observer.events] == ["budget_set", "tool_round", "loop_turn"]


@pytest.mark.asyncio
async def test_window_trim_is_counted_as_a_compaction_event():
    from core.chat import chat_with_tools

    client = _ScriptedClient([_read_call_response(), _make_response(content="fertig")])
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ), patch("core.chat_tools._active_context_window", return_value=1):
        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "lies notes.txt"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            loop_observer=observer,
        )

    assert observer.counters.compaction_events >= 1
    assert observer.counters.messages_dropped > 0
    window_events = [e for e in observer.events if e["event"] == "compaction"]
    assert window_events and all(e["source"] == "window" for e in window_events)
    assert all(e["dropped"] > 0 for e in window_events)


@pytest.mark.asyncio
async def test_history_compaction_is_counted_before_the_first_round():
    from core.chat import chat_with_tools

    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"} for i in range(14)]
    client = _ScriptedClient([_read_call_response(), _make_response(content="fertig")])
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ), patch("core.conversation_compactor.window_threshold", return_value=1):
        await chat_with_tools(
            model="gemma4:12b",
            history=history,
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            loop_observer=observer,
        )

    history_events = [e for e in observer.events if e["event"] == "compaction" and e["source"] == "history"]
    assert len(history_events) == 1
    assert history_events[0]["dropped"] == 2


@pytest.mark.asyncio
async def test_the_bound_observer_is_cleared_when_the_turn_returns():
    from core.chat import chat_with_tools

    client = _ScriptedClient([_read_call_response(), _make_response(content="fertig")])
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "lies notes.txt"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            loop_observer=observer,
        )

    assert current_observer() is None


@pytest.mark.asyncio
async def test_a_failing_turn_still_closes_and_unbinds_the_observer():
    from core.chat import chat_with_tools

    class _FailingClient:
        async def chat(self, **kwargs):  # noqa: ARG002
            raise RuntimeError("engine blew up")

        async def aclose(self):
            return None

    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=_FailingClient()):
        with pytest.raises(RuntimeError):
            await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "lies notes.txt"}],
                on_chunk=lambda c: None,
                allowed_tool_names=["read_file"],
                loop_observer=observer,
            )

    # The finally block must close the turn and drop the binding even when the
    # engine raised, or a broken turn leaks its observer into the next task.
    assert observer.events[-1]["event"] == "loop_turn"
    assert current_observer() is None


@pytest.mark.asyncio
async def test_a_default_observer_still_emits_the_turn_event():
    from core.chat import chat_with_tools

    handler = _Capture()
    logger = logging.getLogger("ephe.loop")
    logger.addHandler(handler)
    try:
        client = _ScriptedClient([_read_call_response(), _make_response(content="fertig")])
        with patch("core.chat.build_provider_client", return_value=client), patch(
            "core.chat.execute_tool", new=AsyncMock(return_value="ok")
        ):
            await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "lies notes.txt"}],
                on_chunk=lambda c: None,
                allowed_tool_names=["read_file"],
            )
    finally:
        logger.removeHandler(handler)

    turn_lines = [
        json.loads(line) for line in handler.lines if json.loads(line)["event"] == "loop_turn"
    ]
    assert turn_lines, "a turn with no caller-supplied observer still reports loop_turn"
    assert turn_lines[-1]["scope"] == "loop"
    # The closing event carries the turn's accumulated counter, not a zero.
    assert turn_lines[-1]["tool_rounds"] == 1
    assert current_observer() is None
