"""
Ephe — R38: skill-routing sovereignty.

Pins:
  1. The artifact-verb heuristic beats the generic score loop (intent first).
  2. An explicitly named tool = no fuzzy-score hijack: the skill that declares
     that name wins deterministically.
  3. Fast paths do not overwrite the user artifact path (xlsx: an existing path
     taken from the prompt becomes the output path; without a path the default stays).
  4. Expectation-based quality gate: the expectations a skill declares in its
     test (expect_contains / expect_tool) are hard checks.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import pytest


# 1 + 2: routing sovereignty

def test_artefakt_verb_intent_beats_generic_score():
    """GIVEN a sentence with a verb plus an artifact noun
    WHEN resolve_for_message()
    THEN the intent heuristic (/pdf) wins over the generic score loop."""
    from core.skills import SkillLoader

    skill = SkillLoader().resolve_for_message("erstelle ein PDF aus diesen Daten: a; b")
    assert skill is not None
    assert skill.trigger == "/pdf"


def test_single_word_does_not_hijack():
    """GIVEN a single word without a verb combination
    WHEN resolve_for_message()
    THEN no skill (the score threshold >=2 stays the barrier)."""
    from core.skills import SkillLoader

    assert SkillLoader().resolve_for_message("text") is None


def test_explicit_tool_name_selects_declaring_skill():
    """GIVEN a prompt that names a tool explicitly
    WHEN resolve_for_message()
    THEN the skill carrying that tool declaration wins (no fuzzy hijack);
    with several candidates it is a coding-class skill."""
    from core.skills import SkillLoader

    loader = SkillLoader()
    sn = loader.resolve_for_message("query_source_notebook fuer Ordner")
    assert sn is not None and sn.name == "source-notebook"
    cs = loader.resolve_for_message("run_tests ausfuehren")
    assert cs is not None and cs.name in {"coding-agent", "ephe-agent"}


def test_explicit_tool_name_not_hijacked_by_other_skill():
    """GIVEN 'edit_file README.md' (edit_file is declared in several skills)
    WHEN resolve_for_message()
    THEN the first declaring skill in the load order wins deterministically
    (no fuzzy hijack by the score loop)."""
    from core.skills import SkillLoader

    skill = SkillLoader().resolve_for_message("edit_file README.md")
    assert skill is not None
    assert skill.name == "api-designer"


# 3: expectation-based quality gate

def _fake_skill():
    from core.skills import Skill, SkillTest

    return Skill(
        name="fake",
        trigger="/fake",
        description="fake",
        system_prompt="x",
        tools=["create_xlsx"],
        test=SkillTest(
            input="i",
            expect_tool="create_xlsx",
            expect_contains="Excel-Tabelle erstellt",
        ),
    )


def test_quality_gate_fails_on_missing_expected_content():
    """GIVEN a skill with expect_contains and the current question == the TEST input
    WHEN evaluate_quality()
    THEN fail + the issue names the missing expectation (hard in the input case)."""
    from core.quality import evaluate_quality, normalize_tool_result

    tr = [normalize_tool_result("create_xlsx", "XLSX_FILE:/tmp/x.xlsx")]
    report = evaluate_quality(
        answer="some other words",
        skill=_fake_skill(),
        tool_results=tr,
        question="i",
    )
    assert report.status == "failed"
    assert any("Excel-Tabelle erstellt" in issue for issue in report.issues)


def test_quality_gate_fails_on_missing_expected_tool():
    """GIVEN a skill with expect_tool, but the tool did not run (input case)
    WHEN evaluate_quality()
    THEN fail + the issue names the missing tool."""
    from core.quality import evaluate_quality, normalize_tool_result

    tr = [normalize_tool_result("read_file", "1\tcontent")]
    report = evaluate_quality(
        answer="Excel-Tabelle erstellt",
        skill=_fake_skill(),
        tool_results=tr,
        question="i",
    )
    assert report.status == "failed"
    assert any("create_xlsx" in issue for issue in report.issues)


def test_quality_gate_advisory_for_other_question():
    """GIVEN the current question deviates from the declared TEST input
    WHEN evaluate_quality()
    THEN the expectations count only as advisory (warnings), the status stays passed
    — no pseudo-fail on a foreign input (1:1 test semantics)."""
    from core.quality import evaluate_quality, normalize_tool_result

    tr = [normalize_tool_result("read_file", "1\tcontent")]
    report = evaluate_quality(
        answer="irgendwas",
        skill=_fake_skill(),
        tool_results=tr,
        question="andere frage",
    )
    assert report.status == "passed"
    assert report.issues == []
    assert any("Expected" in w for w in report.warnings)


def test_quality_gate_passes_when_expectations_met():
    """GIVEN every declared expectation is met
    WHEN evaluate_quality()
    THEN passed, no issues."""
    from core.quality import evaluate_quality, normalize_tool_result

    tr = [normalize_tool_result("create_xlsx", "XLSX_FILE:/tmp/x.xlsx")]
    report = evaluate_quality(
        answer="## Excel-Tabelle erstellt",
        skill=_fake_skill(),
        tool_results=tr,
    )
    assert report.status == "passed"
    assert report.issues == []
