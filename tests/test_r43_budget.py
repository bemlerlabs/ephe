"""
◑ Ephe – R43 (round 3): tool budget of the casual class at 10.
tests/test_r43_budget.py

RULE: tests written BEFORE the implementation.
Coding sessions need more than 5 rounds without the user having to top the
budget up; the hard cap stays 40, /ephe stays 25.
"""
from __future__ import annotations


def test_casual_default_budget_is_25():
    """GIVEN the casual class with no explicit budget value
    WHEN clamp_tool_budget(None) and MAX_TOOL_ITERATIONS are read
    THEN the default is 25 (R46: normal chat is coding mode — long
    work orders were cut off at 10 in the middle of the work), never 0, never
    above the hard cap."""
    from core.chat import MAX_TOOL_ITERATIONS, clamp_tool_budget

    assert MAX_TOOL_ITERATIONS == 25
    assert clamp_tool_budget(None) == 25
    assert clamp_tool_budget(0) == 25
    assert clamp_tool_budget(7) == 7
    assert clamp_tool_budget(99) == 40
