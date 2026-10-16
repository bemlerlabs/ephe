"""Tests for Wave 2 (P1): architecture patterns.

  P1-1: two-tier semantic routing (TF-IDF + hard veto)
  P1-3: skill-stratified sidecar budget
"""
from __future__ import annotations

import pathlib
import pytest


# P1-1: Two-Tier Semantic Routing

def test_p1_1_stem_prefix_matches_tests_to_test():
    """German inflection: "tests" ~ "test" via 3-char stem prefix."""
    from core.skills import _idf_weighted_score
    table = {"test": 3.5}
    score = _idf_weighted_score("schreibe tests", ["test schreiben"], table)
    assert score >= 2.0  # "tests" matches "test" via stem


def test_p1_1_stem_prefix_matches_schreibe_schreiben():
    from core.skills import _idf_weighted_score
    table = {"schreiben": 2.0, "test": 2.0}
    score = _idf_weighted_score("schreibe test", ["schreiben", "test schreiben"], table)
    assert score >= 2.0  # 2 word matches: schreibe~schreiben + test~test  # language-gate: ignore (names the German pair in the literals above)


def test_p1_1_veto_blocks_matching_negative():
    """when_not_to_use veto: >=3-char stem-prefix overlap -> skill blocked."""
    from core.skills import _veto_hit
    assert _veto_hit("refactor den code", ["refactor", "debug"])


def test_p1_1_veto_no_false_positive():
    from core.skills import _veto_hit
    assert not _veto_hit("erstell ein pdf", ["refactor", "debug"])


def test_p1_1_routing_test_writer_beats_coding_agent():
    """test-writer should win for "schreibe tests fuer die parser funktion".  # language-gate: ignore (German routing prompt under test, line 46)
    coding-agent has "tests" only in its description, test-writer in when_to_use."""
    from core.skills import SkillLoader, BUILTIN_SKILLS_DIR
    sl = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    sl._clear_cache()
    s = sl.resolve_for_message("schreibe tests fuer die parser funktion")
    assert s is not None
    assert s.name == "test-writer"


def test_p1_1_routing_pitch_deck_routes_to_deck_creator():
    from core.skills import SkillLoader, BUILTIN_SKILLS_DIR
    sl = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    sl._clear_cache()
    s = sl.resolve_for_message("ich brauche ein pitch deck fuer investor")
    assert s is not None
    assert s.name == "deck-creator"


def test_p1_1_routing_debugger_for_stack_trace():
    from core.skills import SkillLoader, BUILTIN_SKILLS_DIR
    sl = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    sl._clear_cache()
    s = sl.resolve_for_message("debug den fehler im stack trace")
    assert s is not None
    assert s.name == "debugger"


# P1-3: skill-stratified sidecar budget

def test_p1_3_budget_table_has_three_profiles():
    from core.skills import _SIDECAR_BUDGETS
    assert set(_SIDECAR_BUDGETS.keys()) == {"standard", "artifact", "source_grounded"}


def test_p1_3_source_grounded_has_largest_example_budget():
    from core.skills import _SIDECAR_BUDGETS
    sg_ex = _SIDECAR_BUDGETS["source_grounded"][0]
    art_ex = _SIDECAR_BUDGETS["artifact"][0]
    std_ex = _SIDECAR_BUDGETS["standard"][0]
    assert sg_ex >= art_ex >= std_ex
    assert sg_ex == 2400


def test_p1_3_document_factory_uses_source_grounded_profile():
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill
    df = BUILTIN_SKILLS_DIR / "document-factory"
    s = _parse_skill("document-factory", (df / "SKILL.md").read_text(encoding="utf-8"), skill_dir=df)
    assert s.quality_profile == "source_grounded"


def test_p1_3_artifact_skills_carry_artifact_profile():
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill
    p = BUILTIN_SKILLS_DIR / "pdf-creator"
    s = _parse_skill("pdf-creator", (p / "SKILL.md").read_text(encoding="utf-8"), skill_dir=p)
    assert s.quality_profile == "artifact"
    assert len(s.example_text) <= 2400


def test_p1_3_no_skill_exceeds_source_grounded_cap():
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill, _SIDECAR_BUDGETS
    max_ex = max(v[0] for v in _SIDECAR_BUDGETS.values())
    for md in sorted(BUILTIN_SKILLS_DIR.glob("*/SKILL.md")):
        s = _parse_skill(md.parent.name, md.read_text(encoding="utf-8"), skill_dir=md.parent)
        assert len(s.example_text) <= max_ex + 10, f"{s.name}: example exceeds cap"


# P1-A: the inline ## Example fenced block is parsed + injected (S1)

def test_p1a_example_block_parsed_into_field():
    """The inline ```json block from the SKILL.md body lands in example_block."""
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill
    p = BUILTIN_SKILLS_DIR / "pdf-creator"
    s = _parse_skill("pdf-creator", (p / "SKILL.md").read_text(encoding="utf-8"), skill_dir=p)
    assert s.example_block.startswith("```json")
    assert "```" in s.example_block


def test_p1a_all_example_skills_expose_json_fewshot():
    """Every builtin skill ships the json few-shot block — 51 of 51, measured today.

    The floor used to be `>= 50` under a docstring that claimed 14 skills, so a skill
    losing its block stayed green while the sentence above it was already false. The
    gate is the directory now: each `SKILL.md` has to carry the heading and parse into
    the block, and the names that fail are named. `w8-missing-skill`, which the old
    comment excepted, is an API-test fixture name and no file in `skills/`.
    """
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill
    missing_heading: list[str] = []
    checked = 0
    for md in sorted(BUILTIN_SKILLS_DIR.glob("*/SKILL.md")):
        body = md.read_text(encoding="utf-8")
        if "## Example" not in body:
            missing_heading.append(md.parent.name)
            continue
        s = _parse_skill(md.parent.name, body, skill_dir=md.parent)
        assert "```json" in (s.system_prompt + " " + s.example_text), s.name
        assert "```json" in s.example_block, s.name
        checked += 1
    assert not missing_heading, f"skills with no json few-shot block: {missing_heading}"
    assert checked >= 51, f"few-shot coverage fell: {checked} of {checked + len(missing_heading)}"


# P1-B: per-turn context budget (S2)

def test_p1b_composed_block_respects_small_budget(monkeypatch):
    """With the 6000-char cap every composed block incl. the guard stays under the limit."""
    from core.skills import SkillLoader, BUILTIN_SKILLS_DIR
    import server.routes.chat as c
    monkeypatch.setenv("EPHE_MAX_CONTEXT_CHARS", "6000")
    sl = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    sl._clear_cache()
    for ask in (False, True):
        for s in sl.load_all():
            composed = c._compose_extra_system(s, ask_mode=ask) or ""
            assert len(composed) <= 6000, f"{s.name} ask={ask} len={len(composed)}"


def test_p1b_base_prompt_survives_tiny_budget(monkeypatch):
    """The base system prompt (mandatory) survives even under a tight cap."""
    from core.skills import SkillLoader, BUILTIN_SKILLS_DIR
    import server.routes.chat as c
    monkeypatch.setenv("EPHE_MAX_CONTEXT_CHARS", "6000")
    sl = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    sl._clear_cache()
    s = next(x for x in sl.load_all() if x.name == "pdf-creator")
    composed = c._compose_extra_system(s, ask_mode=False) or ""
    assert composed.startswith(s.system_prompt[:40])
