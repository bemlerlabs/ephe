import asyncio

import pytest


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch):
    """Issue #16: create_pdf resolves output_dir from the real user config —
    keep this suite from writing into a configured directory."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    yield
    import core.model_provider as mp

    mp._ACTIVE_OVERRIDE = None


def test_given_tool_artifact_result_when_normalized_then_contract_fields_are_available():
    from core.quality import normalize_tool_result

    result = normalize_tool_result("create_pdf", "PDF_FILE:/Users/test/Downloads/report.pdf")

    assert result.status == "success"
    assert result.summary == "PDF artifact created"
    assert result.artifacts == [{"type": "pdf", "path": "/Users/test/Downloads/report.pdf"}]
    assert result.evidence
    assert result.raw == "PDF_FILE:/Users/test/Downloads/report.pdf"


def test_given_multi_marker_deck_result_when_normalized_then_all_artifacts_are_available():
    from core.quality import normalize_tool_result

    raw = "\n".join([
        "PITCH_DECK_FILE:/Users/test/Downloads/deck.pdf",
        "DECK_SPEC_FILE:/Users/test/Downloads/deck.deck-spec.json",
        "VISUAL_QA_FILE:/Users/test/Downloads/deck.visual-qa.json",
        "EVIDENCE_LEDGER_FILE:/Users/test/Downloads/deck.evidence-ledger.json",
    ])

    result = normalize_tool_result("create_pitch_deck", raw)

    assert result.status == "success"
    assert result.summary == "4 artifacts created"
    assert result.artifacts == [
        {"type": "deck", "path": "/Users/test/Downloads/deck.pdf"},
        {"type": "deck_spec", "path": "/Users/test/Downloads/deck.deck-spec.json"},
        {"type": "visual_qa", "path": "/Users/test/Downloads/deck.visual-qa.json"},
        {"type": "evidence_ledger", "path": "/Users/test/Downloads/deck.evidence-ledger.json"},
    ]


def test_given_tool_error_when_normalized_then_warning_and_error_status_are_available():
    from core.quality import normalize_tool_result

    result = normalize_tool_result("read_file", "[Tool-Fehler 'read_file': missing path]")

    assert result.status == "error"
    assert "missing path" in result.summary
    assert result.warnings
    assert result.artifacts == []


def test_given_pdf_skill_answer_without_artifact_when_quality_checked_then_it_fails():
    from core.quality import ToolResult, evaluate_quality
    from core.skills import Skill

    skill = Skill(
        name="pdf-creator",
        trigger="/pdf",
        description="PDF",
        tools=["create_pdf"],
        system_prompt="Do not simulate. Output Contract:\nQuality Gate:",
        artifact_types=["pdf"],
        quality_profile="artifact",
    )

    report = evaluate_quality(
        answer="Done, I created the PDF in Downloads.",
        skill=skill,
        tool_results=[ToolResult(tool="create_pdf", status="error", summary="failed", raw="[pdf-Fehler]")],
    )

    assert report.status == "failed"
    assert report.needs_revision is True
    assert any("pdf artifact" in issue.lower() for issue in report.issues)


def test_given_pdf_skill_answer_with_artifact_when_quality_checked_then_it_passes():
    from core.quality import normalize_tool_result, evaluate_quality
    from core.skills import Skill

    skill = Skill(
        name="pdf-creator",
        trigger="/pdf",
        description="PDF",
        tools=["create_pdf"],
        system_prompt="Do not simulate. Output Contract:\nQuality Gate:",
        artifact_types=["pdf"],
        quality_profile="artifact",
    )

    report = evaluate_quality(
        answer="PDF saved at /Users/test/Downloads/report.pdf",
        skill=skill,
        tool_results=[normalize_tool_result("create_pdf", "PDF_FILE:/Users/test/Downloads/report.pdf")],
    )

    assert report.status == "passed"
    assert report.needs_revision is False
    assert report.issues == []


def test_given_deck_studio_without_real_download_links_when_validated_then_it_fails(tmp_path):
    """
    GIVEN a Slide Studio page with visible labels but no local file links
    WHEN the artifact validator checks it
    THEN it fails instead of accepting a fake-success studio.
    """
    from core.quality import validate_deck_studio_artifact

    studio = tmp_path / "fake.studio.html"
    studio.write_text(
        "Ephe Slide Studio\nChoose Output\nSlide Contact Sheet\n"
        "Download PDF\nDownload PPTX\nOpen QA Report\nOpen Claim Manifest",
        encoding="utf-8",
    )

    report = validate_deck_studio_artifact(str(studio))

    assert report.status == "failed"
    assert any("local download link" in warning.lower() for warning in report.warnings)


def test_given_pdf_created_when_artifact_validated_then_render_and_text_checks_pass():
    from pathlib import Path
    from core.quality import validate_pdf_artifact
    from core.tools import create_pdf

    result = asyncio.run(
        create_pdf(
            title="Quality Artifact Validation",
            content="# Executive Summary\nReadable text with <literal> value.\n## Source Notes\n- local test",
            filename="quality-artifact-validation.pdf",
        )
    )
    lines = result.splitlines()
    assert lines[0].startswith("PDF_FILE:") and lines[1].startswith("PDF_PAGES:")
    path = Path(lines[0].removeprefix("PDF_FILE:"))

    report = validate_pdf_artifact(str(path))

    assert report.status == "passed"
    assert report.path == str(path)
    assert report.warnings == []
