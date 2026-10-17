"""Narrow tests for the per-case call/cap receipt (`evals/call_cap_receipt.py`).

The receipt exists to keep a miss at the cap apart from a miss the turn chose. These tests
pin the three things that separation rests on: the round read from the loop's own phase
line, the cap read from the product's own clamp, and the verdict a transcript earns — all
without a model or a surface.
"""
from __future__ import annotations

import json

from core.chat import TOOL_BUDGET_HARD_CAP, clamp_tool_budget
from core.chat_context import _budget_exhausted_note
from evals.call_cap_receipt import (
    ERROR,
    HIT,
    MISS_AT_CAP,
    MISS_CAP_UNKNOWN,
    MISS_NOT_AT_CAP,
    OUTCOME_UNKNOWN,
    cap_for,
    classify,
    ended_at_cap,
    parse_transcript,
    rounds_in_phase,
    tally,
    turn_from_events,
)
from evals.live_eval import parse_events


def _events() -> list[dict]:
    """One transcript with a round line, a shim call and its dispatch, and answer text."""
    return [
        {"type": "model_info", "model": "m"},
        {"type": "activity", "cmd": "Tool round 1…", "status": "running"},
        {"type": "tool_start", "tool": "tool_search", "args": {"query": "search"}},
        {"type": "tool_start", "tool": "tool_call", "args": {"name": "web_search"}},
        {"type": "chunk", "data": "hello "},
        {"type": "activity", "cmd": "Tool round 2… (nudge 1)", "status": "running"},
        {"type": "chunk", "data": "world"},
    ]


def test_rounds_are_read_from_the_phase_line():
    assert rounds_in_phase("Tool round 7…") == 7
    assert rounds_in_phase("Tool round 7… (nudge 2)") == 7
    assert rounds_in_phase("Processing results…") == 0
    assert rounds_in_phase("") == 0


def test_transcript_reader_agrees_with_the_live_runner():
    """The receipt's reader and the live runner's reader must not drift in silence."""
    events = _events()
    tools, dispatched, answer, counts, rounds, error = parse_transcript(events)
    ref_tools, ref_dispatched, ref_answer, ref_counts, ref_error = parse_events(
        ["data: " + json.dumps(event) for event in events]
    )
    assert tools == ref_tools
    assert dispatched == ref_dispatched
    assert answer == ref_answer
    assert counts == ref_counts
    assert error == ref_error
    assert rounds == 2


def test_turn_folds_the_discovery_shim():
    turn = turn_from_events(_events())
    assert "tool_search" not in turn["tools"]
    assert "tool_call" not in turn["tools"]
    assert "web_search" in turn["tools"]
    assert turn["rounds"] == 2
    assert turn["counts"]["tool_start"] == 2


def test_turn_keeps_a_dispatch_at_its_firing_position():
    """The receipt folds through the live runner's reader, so the order must arrive intact."""
    events = [
        {"type": "activity", "cmd": "Tool round 1…", "status": "running"},
        {"type": "tool_start", "tool": "tool_search", "args": {"query": "deck"}},
        {"type": "tool_start", "tool": "tool_call", "args": {"name": "create_pdf"}},
        {"type": "tool_start", "tool": "run_shell", "args": {"command": "open deck.pdf"}},
        {"type": "chunk", "data": "deck built"},
    ]

    turn = turn_from_events(events)

    assert turn["tools"] == ["create_pdf", "run_shell"]
    assert turn["dispatched"] == ["create_pdf"]
    assert turn["rounds"] == 1


def test_cap_is_read_from_the_product_clamp():
    assert cap_for(None) == clamp_tool_budget(None)
    assert cap_for(999) == TOOL_BUDGET_HARD_CAP
    assert cap_for(TOOL_BUDGET_HARD_CAP) == clamp_tool_budget(TOOL_BUDGET_HARD_CAP)


def test_cap_end_uses_the_loops_own_evidence():
    cap = cap_for(40)
    assert ended_at_cap(_budget_exhausted_note(cap), 1, cap) is True
    assert ended_at_cap("", cap, cap) is True  # stopped exactly at the ceiling
    assert ended_at_cap("a final answer", 2, cap) is False


def test_verdicts_separate_the_cap_from_the_choice():
    cap = cap_for(40)
    note = _budget_exhausted_note(cap)
    assert classify(outcome=True, answer="done", rounds=1, cap=cap, error=None) == HIT
    assert classify(outcome=False, answer=note, rounds=3, cap=cap, error=None) == MISS_AT_CAP
    assert classify(outcome=False, answer="an answer", rounds=2, cap=cap, error=None) == MISS_NOT_AT_CAP
    assert classify(outcome=False, answer="", rounds=0, cap=cap, error=None) == MISS_CAP_UNKNOWN
    assert classify(outcome=None, answer="", rounds=0, cap=cap, error=None) == OUTCOME_UNKNOWN
    assert classify(outcome=False, answer="x", rounds=1, cap=cap, error="boom") == ERROR


def test_tally_counts_every_verdict():
    rows = [{"verdict": HIT}, {"verdict": MISS_AT_CAP}, {"verdict": MISS_AT_CAP}]
    counts = tally(rows)
    assert counts[HIT] == 1
    assert counts[MISS_AT_CAP] == 2
    assert counts[MISS_NOT_AT_CAP] == 0
