"""Every built-in skill carries one tier; A-tier meets the stronger contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIERS = ROOT / "skills" / "tiers.json"
PACKS = ROOT / "skills" / "pack-index.json"


def _payload() -> dict:
    return json.loads(TIERS.read_text(encoding="utf-8"))


def test_all_51_skills_have_a_tier_and_a_reason():
    skills = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
    tiers = _payload()["skills"]
    assert len(skills) == 51
    assert sorted(tiers) == skills
    for name, entry in tiers.items():
        assert entry["tier"] in {"A", "B", "C"}, name
        assert entry["reason"].strip(), name


def test_the_distribution_is_credible():
    counts = _payload()["counts"]
    assert 15 <= counts["A"] <= 20
    assert counts["B"] > 0
    assert counts["C"] > 0
    assert sum(counts.values()) == 51


def test_a_tier_has_two_examples_contract_gate_and_tools():
    for name, entry in _payload()["skills"].items():
        if entry["tier"] != "A":
            continue
        assert entry["examples"] >= 2, name
        assert entry["output_contract"] is True, name
        assert entry["quality_gate"] is True, name
        assert entry["tools"], name


def test_b_tier_has_an_example_and_a_contract():
    for name, entry in _payload()["skills"].items():
        if entry["tier"] != "B":
            continue
        assert entry["examples"] >= 1, name
        assert entry["output_contract"] is True, name


def test_duplicates_are_marked_not_removed():
    tiers = _payload()["skills"]
    for name in ("email-writer", "meeting-notes", "explain-expert"):
        assert tiers[name]["duplicate"] is True, name
        assert len(tiers[name]["packs"]) > 1, name


def test_the_five_packs_still_cover_the_same_skills():
    packs = json.loads(PACKS.read_text(encoding="utf-8"))["packs"]
    assert len(packs) == 5
    covered = {skill for pack in packs for skill in pack["skills"]}
    assert len(covered) == 51
    assert covered == set(_payload()["skills"])
