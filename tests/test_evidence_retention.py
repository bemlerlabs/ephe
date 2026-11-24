"""The evidence uploads pin one retention value, so the plan and the tree cannot drift apart.

Two uploads once disagreed: `frontend-build.yml` carried 7 days, and `bench-trend.yml` set
nothing at all and so inherited an account default no file here
controls. 14 days is the chosen value, and this test holds both uploads to it: read on
2026-11-24 both carry `retention-days: 14` (`frontend-build.yml:246`, `bench-trend.yml:62`).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DAYS = 14
UPLOADS = (
    ".github/workflows/frontend-build.yml",
    ".github/workflows/bench-trend.yml",
)


def _retention_days(rel: str) -> list[int]:
    text = (ROOT / rel).read_text(encoding="utf-8")
    return [int(match) for match in re.findall(r"^\s*retention-days:\s*(\d+)\s*$", text, re.M)]


def test_both_evidence_uploads_pin_the_plan_retention():
    for rel in UPLOADS:
        days = _retention_days(rel)
        assert days, f"{rel} uploads with no retention-days, so it inherits the account default"
        assert set(days) == {EXPECTED_DAYS}, f"{rel} carries {days}; the plan states {EXPECTED_DAYS}"
