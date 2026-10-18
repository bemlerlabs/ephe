"""F1 regression: a general call to action must not be routed onto a skill fast path
(previously: a shell prompt -> project-assistant -> its German "no matching code
projects found" reply)."""
from pathlib import Path

from core.skills import SkillLoader


def test_given_shell_execution_prompt_when_resolved_then_no_skill_fastpath():
    """R38: an explicitly named tool name such as run_shell resolves the declaring
    skill deterministically (first-declarer in load order) — no fuzzy hijack."""
    loader = SkillLoader()
    msg = (
        "Führe exakt diesen Shell-Befehl mit dem run_shell Tool aus: "
        "echo SMOKE_OK. Rufe kein anderes Tool auf. Antworte danach mit der Ausgabe."
    )
    skill = loader.resolve_for_message(msg)
    assert skill is not None and skill.name == "code-reviewer"


def test_given_explicit_slash_trigger_when_resolved_then_skill_still_matches():
    loader = SkillLoader()
    skill = loader.resolve_trigger("/project")
    assert skill is not None and skill.name == "project-assistant"


def test_given_edit_file_prompt_when_resolved_then_no_single_word_fastpath():
    """F2 + R38: the single-word score stays a threshold; the explicit tool name
    edit_file resolves the first declaring skill deterministically."""
    loader = SkillLoader()
    msg = ("Ersetze in der Datei /tmp/ephe_smoke_edit.txt den Text ZEILE_A "
           "durch ZEILE_B mit dem Tool edit_file.")
    skill = loader.resolve_for_message(msg)
    assert skill is not None and skill.name == "api-designer"


def test_given_research_compare_prompt_when_resolved_then_no_notebook_hijack():
    """W19 bench lever: comparison/research prompts carrying 'source URL' must
    NOT route to source-notebook — its source_grounded quality profile would then
    demand notebook/PPTX artifacts and fail the clean turn.
    (Bench r3: 3/3 'Missing real notebook artifact evidence'.)"""
    loader = SkillLoader()
    msg = ("Compare local on-device inference vs remote API inference for a "
           "privacy-focused assistant. Deliver exactly 3 pros and 3 cons per "
           "side, each with a source URL you actually fetched.")
    skill = loader.resolve_for_message(msg)
    assert skill is None or skill.name != "source-notebook"


def test_given_fetch_and_pdf_prompt_when_resolved_then_document_skill_wins():
    """The M1 bench prompt ('… create a brief PDF … Sources section') stays
    with the pdf-creator (artifact intent wins over the 'sources' word)."""
    loader = SkillLoader()
    msg = ("Fetch the 2 most relevant sources on agentic tool use in 2026, "
           "then create a brief PDF summarizing them with a Sources section "
           "listing the URLs.")
    skill = loader.resolve_for_message(msg)
    assert skill is not None and skill.name == "pdf-creator"


def test_all_skill_packs_declare_when_to_use_and_when_not_to_use(tmp_path):
    """Issue #22: every built-in pack carries at least two positive routing
    terms and two veto terms — a pack with one entry routes too eagerly and
    cannot be kept out of the wrong turn."""
    builtin = Path(__file__).resolve().parents[1] / "skills"
    loader = SkillLoader(skills_dir=tmp_path, builtin_dir=builtin, plugin_root=tmp_path)
    skills = loader.load_all()
    assert len(skills) >= 40, "the built-in pack directory did not load"
    short = {
        skill.name: (len(skill.when_to_use), len(skill.when_not_to_use))
        for skill in skills
        if len(skill.when_to_use) < 2 or len(skill.when_not_to_use) < 2
    }
    assert short == {}
