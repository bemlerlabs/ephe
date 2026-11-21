from pathlib import Path


def test_given_folder_skill_when_loaded_then_metadata_references_and_negative_triggers_are_available(tmp_path):
    """
    GIVEN a folder skill with SKILL.md and supporting files
    WHEN SkillLoader loads it
    THEN it exposes v2 metadata while preserving the legacy Skill shape.
    """
    from core.skills import SkillLoader

    skill_dir = tmp_path / "skills" / "pdf-pro"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "examples").mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: pdf-pro
trigger: /pdfpro
description: Creates report-grade PDFs.
tools: [create_pdf]
when_to_use:
  - User asks for a polished PDF report.
when_not_to_use:
  - User only asks how PDFs work.
quality_profile: artifact
artifact_types: [pdf]
allowed_tools: [create_pdf]
---

## System Prompt
Do not simulate. Use real tool output.

Output Contract:
- Create a real PDF.

Quality Gate:
- Verify the artifact.
""",
        encoding="utf-8",
    )
    (skill_dir / "references" / "rubric.md").write_text("# Rubric\n- Evidence", encoding="utf-8")
    (skill_dir / "examples" / "golden.md").write_text("# Golden\nExample", encoding="utf-8")

    skill = SkillLoader(skills_dir=tmp_path / "skills", builtin_dir=tmp_path / "empty").load("pdf-pro")

    assert skill.name == "pdf-pro"
    assert skill.trigger == "/pdfpro"
    assert skill.tools == ["create_pdf"]
    assert skill.allowed_tools == ["create_pdf"]
    assert skill.quality_profile == "artifact"
    assert skill.artifact_types == ["pdf"]
    assert "polished PDF" in skill.when_to_use[0]
    assert "only asks how PDFs work" in skill.when_not_to_use[0]
    assert skill.has_references is True
    assert "Rubric" in skill.reference_text
    assert "Golden" in skill.example_text


def test_given_negative_trigger_when_resolving_auto_skill_then_unrelated_skill_is_not_selected(tmp_path):
    """
    GIVEN a skill describes when not to use it
    WHEN automatic skill resolution sees an excluded query
    THEN it does not activate that skill.
    """
    from core.skills import SkillLoader

    skill_dir = tmp_path / "skills" / "research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: research
trigger: /research
description: Researches current facts online.
tools: [web_search]
when_to_use:
  - User asks for current facts.
when_not_to_use:
  - User asks for local files.
---

## System Prompt
Do not simulate. Use real tool output.

Output Contract:
- Cite sources.

Quality Gate:
- Verify sources.
""",
        encoding="utf-8",
    )

    loader = SkillLoader(skills_dir=tmp_path / "skills", builtin_dir=tmp_path / "empty")

    assert loader.resolve_for_message("please research current Ollama release").name == "research"
    assert loader.resolve_for_message("please research my local files") is None
