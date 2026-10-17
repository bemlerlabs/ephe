"""Budgets on the bench's four operational axes, so section 5 of the perf dashboard has a line to cross.

docs/PERF_REGRESSION_2026-10-11.md section 5 records a per-unit cost regression between
commit 4f2778c (2026-09-24) and 9d6efcd1 (2026-10-11): wall +49%, tool calls +133%, prompt
tokens +96%, cohort cost +112%. Until this file existed none of the four had a budget, so
the move was measured but failed nothing. Each budget lives in scripts/timing-budgets.json
beside the CI runner-step budgets; this module reads that file and the comparable points of
evals/bench-trend.json and fails when an axis crosses its line.

tests/test_timing_assertion_guard.py fails when a wall-clock ceiling on a live duration
appears in the parallel leg. This file reads two committed JSON files and no clock, so it
belongs in the parallel leg and holds no ceiling over a measured duration.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUDGETS = REPO / "scripts" / "timing-budgets.json"
TREND = REPO / "evals" / "bench-trend.json"

SECTION = "bench_operational_axes"
INSTRUMENT = "tests/test_bench_budgets.py"


def _section() -> dict:
    data = json.loads(BUDGETS.read_text(encoding="utf-8"))
    return data[SECTION]


def _points() -> list[dict]:
    return json.loads(TREND.read_text(encoding="utf-8"))


def _value(point: dict, select: list[str]):
    node = point
    for key in select:
        node = node[key]
    return node


def _comparable(points: list[dict], section: dict) -> list[dict]:
    field = section["comparable_when"]["field"]
    want = section["comparable_when"]["equals"]
    return [point for point in points if point.get(field) == want]


def crossings(points: list[dict], section: dict) -> list[str]:
    """Every axis of every point that sits above its declared budget, named."""
    out: list[str] = []
    for point in points:
        for entry in section["entries"]:
            value = _value(point, entry["select"])
            if value > entry["budget"]:
                out.append(
                    f"{point['commit']} {entry['measured_as']}: {value} {entry['unit']} "
                    f"over budget {entry['budget']}"
                )
    return out


def test_each_axis_declares_a_budget_above_the_number_it_came_from() -> None:
    section = _section()
    assert section["policy"] == "bench-operational-budget", section["policy"]
    assert section["version"] == 1, section["version"]
    assert section["instrument"] == INSTRUMENT, section["instrument"]
    assert len(section["entries"]) == 4, section["entries"]
    for entry in section["entries"]:
        assert entry["rationale"].strip(), entry["measured_as"]
        assert _value(_points()[-1], entry["select"]) >= 0, entry["measured_as"]
        assert entry["budget"] > entry["measured"], (
            f"{entry['measured_as']}: budget {entry['budget']} is not above the number it "
            f"was written from ({entry['measured']}); that is a red the moment it lands"
        )


def test_the_budgets_are_read_from_the_latest_comparable_points() -> None:
    section = _section()
    points = _points()
    comparable = _comparable(points, section)
    assert comparable, f"no point matches {section['comparable_when']}"
    # The contract is that the filter reaches the newest point, so a budget can never be read
    # from a stale one. Naming a commit id made this fail the moment a new point landed, and
    # that id belongs to the trend file rather than to this test. The helper-returned value is
    # also this file's known blind spot in tests/test_value_ownership_guard.py.
    assert comparable[-1] is points[-1], (
        f"the newest comparable point is {comparable[-1]['commit']} but the series ends at "
        f"{points[-1]['commit']}: the comparison would read stale budgets"
    )


def test_no_comparable_point_sits_over_a_budget() -> None:
    section = _section()
    over = crossings(_comparable(_points(), section), section)
    assert over == [], "bench operational axis over budget:\n" + "\n".join(over)


def test_a_point_over_a_budget_is_reported_not_silent() -> None:
    """The failure path itself: an axis above its line has to name the commit and the axis."""
    section = _section()
    entry = section["entries"][0]
    tightened = {**section, "entries": [{**entry, "budget": entry["measured"] - 1}]}
    point = _comparable(_points(), section)[-1]
    reported = crossings([point], tightened)
    assert len(reported) == 1, reported
    assert entry["measured_as"] in reported[0], reported
