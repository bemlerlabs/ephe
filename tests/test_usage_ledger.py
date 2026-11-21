"""tests/test_usage_ledger.py — wave 3: content-free token accounting.

Privacy contract: numbers only (d/h/in/out/cached/est), never content. Crash-safe
against corrupt lines; costs come from the engine.json pricing in the route.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from core import usage_ledger as UL


def _write(tmp_path, rows: list[dict]) -> None:
    p = tmp_path / "usage.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_record_writes_privacy_shape(tmp_path):
    p = tmp_path / "usage.jsonl"
    row = UL.record_usage(
        in_tokens=1200, out_tokens=340, cached_tokens=100, estimated=False,
        now=datetime(2026, 10, 1, 14, 30), store=p,
    )
    assert set(row.keys()) <= UL._FIELDS | set()
    assert set(row.keys()) == {"d", "h", "in", "out", "cached", "est"}
    assert row["d"] == "2026-10-01" and row["h"] == 14
    # The file is user-only (0o600), same model as the session mirror
    assert (p.stat().st_mode & 0o777) == 0o600


def test_summary_aggregates_by_day_and_totals(tmp_path):
    _write(tmp_path, [
        {"d": "2026-10-01", "h": 9, "in": 1000, "out": 200, "cached": 300, "est": False},
        {"d": "2026-10-01", "h": 15, "in": 500, "out": 100, "cached": 0, "est": True},
        {"d": "2026-09-20", "h": 8, "in": 10_000, "out": 2_000, "cached": 0, "est": False},
    ])
    rep = UL.summarize(7, today=date(2026, 10, 1), store=tmp_path / "usage.jsonl")
    assert rep["days"] == 7
    t = rep["totals"]
    # 7-day window (25.09–01.10): the 20.09 is correctly outside it
    assert t["in"] == 1_500 and t["out"] == 300 and t["cached"] == 300
    assert t["turns"] == 2 and t["est_turns"] == 1
    today_row = next(d for d in rep["by_day"] if d["d"] == "2026-10-01")
    assert today_row["in"] == 1_500 and today_row["turns"] == 2
    assert all(d["d"] != "2026-09-20" for d in rep["by_day"])
    # 30-day window: the 20.09 falls inside it
    rep30 = UL.summarize(30, today=date(2026, 10, 1), store=tmp_path / "usage.jsonl")
    assert rep30["totals"]["in"] == 11_500 and rep30["totals"]["turns"] == 3


def test_summary_survives_corrupt_lines_and_missing_file(tmp_path):
    p = tmp_path / "usage.jsonl"
    p.write_text(
        json.dumps({"d": "2026-10-01", "h": 1, "in": 10, "out": 5, "cached": 0, "est": False})
        + "\n{corrupt!!!\nnull\n",
        encoding="utf-8",
    )
    rep = UL.summarize(3, today=date(2026, 10, 1), store=p)
    assert rep["totals"]["in"] == 10
    # Missing file: empty aggregation, no crash
    empty = UL.summarize(3, today=date(2026, 10, 1), store=tmp_path / "nope.jsonl")
    assert empty["totals"]["in"] == 0 and len(empty["by_day"]) == 3


def test_summary_clamps_span():
    rep = UL.summarize(100_000, today=date(2026, 10, 1), store=None)
    assert rep["days"] == 365
