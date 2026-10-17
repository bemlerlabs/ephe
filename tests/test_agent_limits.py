"""Bounds on a wave of parallel agents, enforced at each boundary.

GIVEN fifty agents may run at once
WHEN any single bound is reached
THEN `check()` names it, `admit()` refuses, and one reading below the bound is allowed.

`core/agent_limits.py` is pure by design: every measurement arrives in the state dict, so
these tests hand in a saturated box, a full disk and a clock that ran out without starting
a process, loading the machine or reading the time.

Failing without the module: `core/agent_limits.py` is the only place a bound is compared,
so a tree without it cannot even collect this file — and nothing else in the tree refuses
the fifty-first agent.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from core import agent_limits, load_bar
from core.agent_limits import Limits, admit, check, defaults
from tests import timing_segment

LIMITS = Limits(
    max_agents=50,
    max_turns_per_agent=40,
    max_cpu_share=0.75,
    max_disk_mb=2048,
    max_runtime_s=1800,
)

# key, the reading that sits exactly on the bound, one reading below it, the reason it must
# produce. One key per case, so the boundary of one limit cannot hide behind another's.
BOUNDARIES: tuple[tuple[str, dict, dict, str], ...] = (
    ("agents", {"agents": 50}, {"agents": 49}, "50 agents running, cap 50"),
    ("turns", {"turns": {"a1": 40}}, {"turns": {"a1": 39}}, "agent a1 at 40 turns, cap 40"),
    ("cpu_share", {"cpu_share": 0.75}, {"cpu_share": 0.74}, "cpu share 0.75 of the box, cap 0.75"),
    (
        "load_per_cpu",
        {"load_per_cpu": load_bar.LOAD_BAR_PER_CPU},
        {"load_per_cpu": load_bar.LOAD_BAR_PER_CPU - 0.1},
        "load 2.0 runnable tasks per CPU, bar 2.0",
    ),
    ("disk_mb", {"disk_mb": 2048}, {"disk_mb": 2047}, "2048 MB written, cap 2048"),
    ("runtime_s", {"runtime_s": 1800}, {"runtime_s": 1799}, "1800 s elapsed, cap 1800"),
)


@pytest.mark.parametrize(
    "key,at_boundary,below,expected",
    BOUNDARIES,
    ids=[case[0] for case in BOUNDARIES],
)
def test_each_bound_refuses_at_itself_and_admits_one_below(
    key: str, at_boundary: dict, below: dict, expected: str
) -> None:
    """GIVEN one reading WHEN it reaches a bound THEN that bound refuses and one below allows."""
    reasons = check(LIMITS, dict(at_boundary))

    assert len(reasons) == 1, f"{key} produced {reasons}"
    assert reasons[0] == f"{agent_limits.REASON_TAG}: {expected}"
    assert not admit(LIMITS, at_boundary)

    assert check(LIMITS, dict(below)) == []
    assert admit(LIMITS, below)


def test_fifty_agents_is_the_admission_edge() -> None:
    """GIVEN the shipped limits WHEN the wave is full THEN the fifty-first agent is refused."""
    limits = defaults()

    assert admit(limits, {"agents": 49})
    assert not admit(limits, {"agents": 50})
    assert admit(limits, {"agents": 0})
    assert limits.max_turns_per_agent == 40
    assert limits.max_runtime_s == 1800


# One bar, two readers


def test_the_load_rule_and_the_timing_segment_share_one_constant() -> None:
    """GIVEN the repo's load bar WHEN both readers import it THEN it is one object, not two."""
    assert agent_limits.LOAD_BAR_PER_CPU is load_bar.LOAD_BAR_PER_CPU
    assert timing_segment.LOAD_BAR_PER_CPU is load_bar.LOAD_BAR_PER_CPU
    assert agent_limits.LOAD_BAR_PER_CPU is timing_segment.LOAD_BAR_PER_CPU


def test_both_readers_stand_down_at_the_same_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN the bar WHEN the timing segment and the gate read it THEN both stand down there."""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    bar = timing_segment.LOAD_BAR_PER_CPU
    monkeypatch.setattr(timing_segment, "load_per_cpu", lambda: bar)

    busy = timing_segment.unmeasurable_reason()

    assert busy is not None and "load" in busy
    assert "load 2.0 runnable tasks per CPU" in check(LIMITS, {"load_per_cpu": bar})[0]

    monkeypatch.setattr(timing_segment, "load_per_cpu", lambda: bar - 0.1)

    assert timing_segment.unmeasurable_reason() is None
    assert check(LIMITS, {"load_per_cpu": bar - 0.1}) == []


# state the caller did not measure


def test_missing_and_unusable_fields_neither_refuse_nor_crash() -> None:
    """GIVEN state without the readings WHEN checked THEN no bound is claimed and nothing raises."""
    assert check(LIMITS, {}) == []
    assert admit(LIMITS, {}) is True

    # A bool is not a reading, and neither is a nan or an infinity: each is skipped rather
    # than compared, so an unmeasured dimension never turns into a refusal by accident.
    unusable: dict[str, Any] = {
        "agents": "many",
        "turns": None,
        "cpu_share": True,
        "load_per_cpu": float("nan"),
        "disk_mb": float("inf"),
        "runtime_s": [],
    }

    assert check(LIMITS, unusable) == []
    assert admit(LIMITS, unusable) is True


def test_a_half_reported_state_judges_only_what_it_reports() -> None:
    """GIVEN only the agent count WHEN it is over the cap THEN only the agent bound refuses."""
    reasons = check(LIMITS, {"agents": 61})

    assert len(reasons) == 1
    assert "61 agents running, cap 50" in reasons[0]


def test_the_state_dict_is_read_never_written_and_never_remembered() -> None:
    """GIVEN one overloaded state WHEN checked twice THEN it is unchanged and repeats itself."""
    state = {"agents": 50, "turns": {"a1": 41, "a2": 0}, "load_per_cpu": 3.4}
    snapshot = copy.deepcopy(state)

    first = check(LIMITS, state)

    assert state == snapshot
    assert first == check(LIMITS, state)
    assert len(first) == 3
    # Every call judges the state dict it is handed.
    assert check(LIMITS, {"agents": 1, "turns": {"b1": 1}, "load_per_cpu": 0.4}) == []


def test_the_turn_cap_names_the_agents_that_reached_it() -> None:
    """GIVEN three agents WHEN two sit at the cap THEN both are named and the third is not."""
    reasons = check(LIMITS, {"turns": {"a1": 40, "a2": 47, "a3": 39}})

    assert len(reasons) == 2
    assert "agent a1 at 40 turns" in reasons[0]
    assert "agent a2 at 47 turns" in reasons[1]
