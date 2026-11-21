"""Enforced bounds on a wave of parallel agents.

Fifty agents on one box is a capacity question, so the bounds are checked before work
starts instead of being documented beside it. `check()` names every bound the state has
reached, `admit()` is the conjunction of those names, and `defaults()` is the shipped set.

Both functions are pure: the caller passes the measurements in `current`, so a test hands
in a loaded box, a full disk or an expired clock without touching the machine, and there is
no clock read here to make such a test lie.

Measured 2026-10-13, 10-core box: thirteen agents saturated it (load 246, forty vitest
processes), two agents got Vite server errors and one full run was killed. A count alone
never bounded that, which is why the CPU rule below reads the same bar
(`core/load_bar.py`) that `tests/timing_segment.py` stands down on.

State keys (`current`), every one of them a reading the caller took:

  agents        int    agents running now
  turns         dict   agent id -> turns that agent has taken
  cpu_share     float  fraction of the box's CPUs the wave holds
  load_per_cpu  float  runnable tasks per CPU now (`os.getloadavg()[0] / cpu_count()`)
  disk_mb       float  megabytes the wave has written
  runtime_s     float  seconds since the wave started

A key that is absent, of the wrong type, or not a finite number is skipped rather than
refused: the gate refuses on a reading, never on a bound nobody instrumented. So
`admit(limits, {})` is True, and the caller owns the instruments — a wave whose
orchestrator does not report a quantity is simply not bounded in that one dimension.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.load_bar import LOAD_BAR_PER_CPU

#: every reason this module produces starts with it, so one grep finds the whole gate
REASON_TAG = "agent-limit"


@dataclass(frozen=True)
class Limits:
    """Ceilings one wave of agents may not cross, each checked at its own boundary."""

    max_agents: int
    max_turns_per_agent: int
    max_cpu_share: float
    max_disk_mb: float
    max_runtime_s: float


def defaults() -> Limits:
    """The shipped bounds for a fifty-agent wave, sized so the box stays usable.

    `max_agents` is the declared width of one wave and not the safety net the 2026-10-13
    run proved a count cannot be; what holds the machine is the load rule in `check()`,
    while the count bounds API calls, processes and memory. The other four come from
    bounds this repository already declares: 1800 s is the ceiling `advanced.api_timeout`
    allows one request, and forty turns reach it at a turn every 45 s, so a stalled agent
    dies on the turn cap before it dies on the clock.
    """
    return Limits(
        max_agents=50,
        max_turns_per_agent=40,
        max_cpu_share=0.75,
        max_disk_mb=2048,
        max_runtime_s=1800,
    )


def _number(current: dict[str, Any], key: str) -> float | None:
    """The value under `key` when it is a real reading, otherwise None.

    `True` is skipped although Python counts it as one: a boolean flag reaching an
    admission rule is a caller bug, and reading it as a measurement would hide the bug
    behind a plausible number.
    """
    value = current.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _turns(current: dict[str, Any], key: str) -> dict[str, int]:
    """The per-agent turn counts the caller reported, with unreadable entries dropped."""
    reported = current.get(key)
    if not isinstance(reported, dict):
        return {}
    counted: dict[str, int] = {}
    for agent, value in reported.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(value) and value >= 0:
            counted[str(agent)] = int(value)
    return counted


def check(limits: Limits, current: dict[str, Any]) -> list[str]:
    """Every bound `current` has reached, in a fixed order; an empty list admits.

    A bound is reached *at* its value and not only beyond it: a cap of 50 refuses the
    fifty-first agent, and the load rule refuses at 2.0 runnable tasks per CPU exactly
    where `tests/timing_segment.py` stops trusting a wall clock (`load >= bar`).
    `current` is never written to.
    """
    reasons: list[str] = []

    agents = _number(current, "agents")
    if agents is not None and agents >= limits.max_agents:
        reasons.append(
            f"{REASON_TAG}: {agents:.0f} agents running, cap {limits.max_agents}"
        )

    for agent, count in sorted(_turns(current, "turns").items()):
        if count >= limits.max_turns_per_agent:
            reasons.append(
                f"{REASON_TAG}: agent {agent} at {count} turns, "
                f"cap {limits.max_turns_per_agent}"
            )

    share = _number(current, "cpu_share")
    if share is not None and share >= limits.max_cpu_share:
        reasons.append(
            f"{REASON_TAG}: cpu share {share:.2f} of the box, cap {limits.max_cpu_share:.2f}"
        )

    load = _number(current, "load_per_cpu")
    if load is not None and load >= LOAD_BAR_PER_CPU:
        reasons.append(
            f"{REASON_TAG}: load {load:.1f} runnable tasks per CPU, "
            f"bar {LOAD_BAR_PER_CPU:.1f}"
        )

    disk = _number(current, "disk_mb")
    if disk is not None and disk >= limits.max_disk_mb:
        reasons.append(
            f"{REASON_TAG}: {disk:.0f} MB written, cap {limits.max_disk_mb:.0f}"
        )

    runtime = _number(current, "runtime_s")
    if runtime is not None and runtime >= limits.max_runtime_s:
        reasons.append(
            f"{REASON_TAG}: {runtime:.0f} s elapsed, cap {limits.max_runtime_s:.0f}"
        )

    return reasons


def admit(limits: Limits, current: dict[str, Any]) -> bool:
    """True when no bound in `current` is reached, so one more unit of work may start."""
    return not check(limits, current)
