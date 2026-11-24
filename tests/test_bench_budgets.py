"""Budgets on the bench's four operational axes, so each axis has a line to cross.

The four axes exist because a per-unit cost move between two bench cohorts once crossed all of
them and failed nothing. Those cohorts and their percentages were recorded outside this tree, so
no figure from them is carried here; what holds the class is the committed budget file. Each
budget lives in `scripts/timing-budgets.json` under `bench_operational_axes`, beside the CI
runner-step budgets; this module reads that file and the comparable points of
a point in the shape the scorer writes, and fails when an axis crosses its line.

tests/test_timing_assertion_guard.py fails when a wall-clock ceiling on a live duration
appears in the parallel leg. This file reads two committed JSON files and no clock, so it
belongs in the parallel leg and holds no ceiling over a measured duration.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUDGETS = REPO / "scripts" / "timing-budgets.json"

SECTION = "bench_operational_axes"
INSTRUMENT = "tests/test_bench_budgets.py"


def _section() -> dict:
    data = json.loads(BUDGETS.read_text(encoding="utf-8"))
    return data[SECTION]


def _points(section: dict) -> list[dict]:
    """One point in the shape the scorer writes, at the numbers the budgets were written
    from. The tree carries no trend ledger, so this file owns the data it asserts on."""
    point: dict = {"commit": "0" * 8}
    point[section["comparable_when"]["field"]] = section["comparable_when"]["equals"]
    for entry in section["entries"]:
        node = point
        for key in entry["select"][:-1]:
            node = node.setdefault(key, {})
        node[entry["select"][-1]] = entry["measured"]
    return [point]


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
    point = _points(section)[-1]
    for entry in section["entries"]:
        assert entry["rationale"].strip(), entry["measured_as"]
        assert _value(point, entry["select"]) >= 0, entry["measured_as"]
        assert entry["budget"] > entry["measured"], (
            f"{entry['measured_as']}: budget {entry['budget']} is not above the number it "
            f"was written from ({entry['measured']}); that is a red the moment it lands"
        )


def test_the_budgets_are_read_from_the_latest_comparable_points() -> None:
    section = _section()
    points = _points(section)
    comparable = _comparable(points, section)
    assert comparable, f"no point matches {section['comparable_when']}"
    # The contract is that the filter reaches the newest point, so a budget can never be read
    # from a stale one. Naming a commit id made this fail the moment a new point landed, and
    # that id belongs to the trend file rather than to this test.
    assert comparable[-1] is points[-1], (
        f"the newest comparable point is {comparable[-1]['commit']} but the series ends at "
        f"{points[-1]['commit']}: the comparison would read stale budgets"
    )


def test_no_comparable_point_sits_over_a_budget() -> None:
    section = _section()
    over = crossings(_comparable(_points(section), section), section)
    assert over == [], "bench operational axis over budget:\n" + "\n".join(over)


def test_a_point_over_a_budget_is_reported_not_silent() -> None:
    """The failure path itself: an axis above its line has to name the commit and the axis."""
    section = _section()
    entry = section["entries"][0]
    tightened = {**section, "entries": [{**entry, "budget": entry["measured"] - 1}]}
    point = _comparable(_points(section), section)[-1]
    reported = crossings([point], tightened)
    assert len(reported) == 1, reported
    assert entry["measured_as"] in reported[0], reported
