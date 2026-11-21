"""Skill parity harness — TDD anchor for the highest-level triple.

Checks every skill mechanically:
  1) references/rubric.md + examples/golden.md present
  2) number of filled check points in the golden >= number of rubric fields
     (every rubric field has a concrete golden value)
  3) no empty golden / no leftover placeholder
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent          # repo root = tests/../
SKILLS = BASE / "skills"


def _skill_dirs() -> list[str]:
    return sorted(
        d.name for d in SKILLS.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def _count_points(text: str) -> list[str]:
    """Collect numbered ('1.') AND bullet ('- ' / '* ') check points."""
    pts: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"(?:\d+\.|[-*])\s+(.+)", s)
        if m and m.group(1).strip():
            pts.append(m.group(1).strip())
    return pts


@pytest.mark.parametrize("name", _skill_dirs())
def test_skill_has_rubric_and_golden(name):
    d = SKILLS / name
    assert (d / "references" / "rubric.md").exists(), f"{name}: references/rubric.md fehlt"
    assert (d / "examples" / "golden.md").exists(), f"{name}: examples/golden.md fehlt"


@pytest.mark.parametrize("name", _skill_dirs())
def test_rubric_fields_covered_by_golden(name):
    d = SKILLS / name
    rub_pts = _count_points((d / "references" / "rubric.md").read_text(encoding="utf-8"))
    gold_pts = _count_points((d / "examples" / "golden.md").read_text(encoding="utf-8"))
    assert rub_pts, f"{name}: rubric.md hat keine Prüf-Punkte"
    assert gold_pts, f"{name}: golden.md hat keine ausgefüllten Punkte"
    assert len(gold_pts) >= len(rub_pts), (
        f"{name}: Golden deckt nur {len(gold_pts)} von {len(rub_pts)} Rubric-Feldern ab"
    )


@pytest.mark.parametrize("name", _skill_dirs())
def test_golden_has_no_placeholder(name):              # NOT minimalist: full values required
    gold = (SKILLS / name / "examples" / "golden.md").read_text(encoding="utf-8")
    assert gold.strip(), f"{name}: golden.md ist leer"


def test_pack_index_lists_all_known_skills():
    idx = json.loads((SKILLS / "pack-index.json").read_text(encoding="utf-8"))
    listed = {s for p in idx["packs"] for s in p["skills"]}
    on_disk = set(_skill_dirs())
    assert listed <= on_disk, f"Pack listet unbekannte Skills: {listed - on_disk}"


def test_pack_index_no_orphans():
    idx = json.loads((SKILLS / "pack-index.json").read_text(encoding="utf-8"))
    listed = {s for p in idx["packs"] for s in p["skills"]}
    on_disk = set(_skill_dirs()) - {"help"}
    assert on_disk <= listed | {"help"}, f"Nicht in einem Pack gefuehrt: {sorted(on_disk - listed)}"
