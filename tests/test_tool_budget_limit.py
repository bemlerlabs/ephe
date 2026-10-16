"""W3-35: the tool-call budget as a first-class, observable limit.

The budget is the loop's hard limit on tool rounds. These tests pin the two
observable moments that make it first-class — the cap is announced once when the
turn establishes it, and a one-shot warning fires as the rounds left fall to
``BUDGET_LOW_WATER`` — plus the exhausted end they sit in front of. A real turn
through ``chat_with_tools`` drives the warning; units drive the announcement.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.loop_observability import (
    BUDGET_LOW_WATER,
    LoopObserver,
    current_observer,
    note_budget_low,
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


class _LevelCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[tuple[str, str]] = []

    def emit(self, record):
        self.records.append((record.levelname, record.getMessage()))


# Announcement — the limit becomes a first-class fact of the turn


def test_cap_is_announced_once_when_it_changes():
    """GIVEN an observer with no cap
    WHEN the turn sets a cap and then re-seeds the same value
    THEN the limit is announced exactly once, carrying the cap."""
    observer = LoopObserver()
    assert observer.events == []

    observer.set_budget_cap(25)
    observer.set_budget_cap(25)  # re-seeding the same cap stays silent

    sets = [e for e in observer.events if e["event"] == "budget_set"]
    assert len(sets) == 1
    assert sets[0]["budget_cap"] == 25
    assert sets[0]["rounds_remaining"] == 25
    assert sets[0]["tool_rounds"] == 0


def test_a_changed_cap_is_announced_again():
    """GIVEN a turn that already announced 25
    WHEN the cap changes
    THEN a second announcement carries the new limit."""
    observer = LoopObserver()
    observer.set_budget_cap(25)
    observer.set_budget_cap(40)

    caps = [e["budget_cap"] for e in observer.events if e["event"] == "budget_set"]
    assert caps == [25, 40]


def test_constructing_with_a_cap_announces_nothing():
    """GIVEN an observer built with a cap
    WHEN nothing re-seeds it
    THEN construction is not an announcement."""
    assert LoopObserver(budget_cap=25).events == []


# Warning — the limit is observable as it is approached


def test_budget_low_warns_once_at_the_watermark():
    """GIVEN a warning threshold
    WHEN the budget first drops to it
    THEN exactly one warning carries the remaining rounds, and a lower call
    does not repeat it."""
    observer = LoopObserver(budget_cap=5)
    observer.note_tool_round(2)  # 3 left
    assert observer.note_budget_low(3)["rounds_remaining"] == 3
    assert observer.note_budget_low(2) is None  # already warned

    lows = [e for e in observer.events if e["event"] == "budget_low"]
    assert len(lows) == 1
    assert lows[0]["rounds_remaining"] == 3


def test_budget_low_treats_a_spent_budget_as_not_low():
    """GIVEN no rounds left
    WHEN the warning is requested
    THEN it is the exhausted end's job, not the low warning's — nothing fires."""
    observer = LoopObserver(budget_cap=4)
    assert observer.note_budget_low(0) is None
    assert observer.note_budget_low(-1) is None
    assert [e for e in observer.events if e["event"] == "budget_low"] == []


def test_module_note_budget_low_is_a_noop_without_an_observer():
    note_budget_low(2)
    assert current_observer() is None


@pytest.mark.asyncio
async def test_a_real_turn_warns_as_the_budget_nears_its_end():
    """GIVEN a six-round budget and a turn that spends three
    WHEN the loop runs
    THEN the limit is announced at the start, warned once when three rounds
    remain, and never claimed exhausted."""
    from core.chat import chat_with_tools

    client = _ScriptedClient(
        [_read_call_response(), _read_call_response(), _read_call_response(), _make_response(content="fertig")]
    )
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "read everything"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            max_tool_iterations=6,
            loop_observer=observer,
        )

    assert observer.counters.tool_rounds == 3
    assert observer.counters.budget_exhausted is False
    assert [e["event"] for e in observer.events] == [
        "budget_set",
        "tool_round",
        "tool_round",
        "tool_round",
        "budget_low",
        "loop_turn",
    ]
    low = next(e for e in observer.events if e["event"] == "budget_low")
    assert low["rounds_remaining"] == BUDGET_LOW_WATER == 3


@pytest.mark.asyncio
async def test_a_roomy_turn_never_warns():
    """GIVEN the default 25-round budget
    WHEN a turn spends one round
    THEN the limit is announced but never called low."""
    from core.chat import chat_with_tools

    client = _ScriptedClient([_read_call_response(), _make_response(content="fertig")])
    observer = LoopObserver()
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "read notes.txt"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["read_file"],
            loop_observer=observer,
        )

    events = [e["event"] for e in observer.events]
    assert "budget_low" not in events
    assert "budget_set" in events


# The warning is emitted as a structured log line.


def test_budget_low_is_a_structured_warning_line():
    handler = _LevelCapture()
    logger = logging.getLogger("ephe.loop")
    logger.addHandler(handler)
    try:
        observer = LoopObserver(budget_cap=5, turn_id="t-42")
        observer.note_tool_round(3)
        observer.note_budget_low(2)
    finally:
        logger.removeHandler(handler)

    low_lines = [(lvl, line) for lvl, line in handler.records if json.loads(line)["event"] == "budget_low"]
    assert low_lines
    level, line = low_lines[0]
    record = json.loads(line)
    assert level == "WARNING"
    assert record["level"] == "warning"
    assert record["scope"] == "loop"
    assert record["turn_id"] == "t-42"
    assert record["rounds_remaining"] == 2
