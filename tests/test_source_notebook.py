from pathlib import Path
import json
import zipfile


def test_given_local_sources_when_create_notebook_then_manifest_has_citeable_chunks(tmp_path):
    """
    GIVEN local source files
    WHEN create_source_notebook_index indexes them
    THEN a local manifest with source IDs and citeable chunks is created
    """
    from core.source_notebook import create_source_notebook_index

    source = tmp_path / "market_notes.md"
    source.write_text(
        "# Market Notes\n\nEnterprise buyers require evidence registers, clear ROI, and conservative claims.",
        encoding="utf-8",
    )

    out = create_source_notebook_index(paths=[str(source)], title="Market Notebook")

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert '"source_id": "S001"' in text
    assert '"chunk_id": "S001-C001"' in text
    assert "Enterprise buyers" in text
    assert payload["schema_version"] == 2
    assert payload["coverage"]["indexed_sources"] == 1
    assert payload["claim_ledger"]
    assert payload["chunks"][0]["vector"]
    assert payload["chunks"][0]["ref"]


def test_given_notebook_when_query_then_answer_contains_evidence_citations(tmp_path):
    """
    GIVEN a source notebook
    WHEN query_source_notebook_index asks about a covered topic
    THEN the response is grounded and includes chunk citations
    """
    from core.source_notebook import create_source_notebook_index, query_source_notebook_index

    source = tmp_path / "deck_strategy.md"
    source.write_text(
        "The deck must avoid amateur language. It should include proof objects, source notes, and an evidence register.",
        encoding="utf-8",
    )
    notebook = create_source_notebook_index(paths=str(source), title="Deck Quality")

    result = query_source_notebook_index(
        notebook_path=str(notebook),
        question="What quality controls should the deck include?",
    )

    assert result["status"] == "grounded"
    assert result["evidence"]
    assert "[S001-C001]" in result["answer"]


def test_given_notebook_when_export_brief_then_brief_has_manifest_and_evidence(tmp_path):
    """
    GIVEN a source notebook
    WHEN export_source_brief_file is called
    THEN the Markdown brief contains executive summary, evidence, and source manifest
    """
    from core.source_notebook import create_source_notebook_index, export_source_brief_file

    source = tmp_path / "research.md"
    source.write_text(
        "NotebookLM-style quality depends on source grounding, citations, and local manifests.",
        encoding="utf-8",
    )
    notebook = create_source_notebook_index(paths=[str(source)], title="Research Notebook")

    brief = export_source_brief_file(
        notebook_path=str(notebook),
        question="What does high quality depend on?",
        filename="source_notebook_brief.md",
    )

    content = brief.read_text(encoding="utf-8")
    assert "Executive Summary" in content
    assert "Evidence Register" in content
    assert "Source Manifest" in content
    assert "Source Coverage" in content
    assert "Claim Ledger" in content
    assert "[S001-C001]" in content


def test_given_pptx_source_when_create_notebook_then_office_text_is_indexed(tmp_path):
    """
    GIVEN a local PPTX source
    WHEN Source Notebook v2 indexes it
    THEN slide text is extracted without external services
    """
    from core.source_notebook import create_source_notebook_index

    pptx = tmp_path / "strategy.pptx"
    with zipfile.ZipFile(pptx, "w") as package:
        package.writestr("ppt/slides/slide1.xml", "<p:sld><a:t>AI architecture operating model</a:t><a:t>Evidence-led platform strategy</a:t></p:sld>")

    out = create_source_notebook_index(paths=[str(pptx)], title="PPTX Notebook")
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["sources"][0]["parser"] == "office-xml"
    assert "AI architecture operating model" in payload["chunks"][0]["text"]


def test_given_source_notebook_skill_when_loaded_then_metadata_is_exposed():
    """
    GIVEN built-in source-notebook skill
    WHEN SkillLoader loads built-ins
    THEN /notebook resolves with source-grounded tools and artifacts
    """
    from core.skills import SkillLoader

    skill = SkillLoader().resolve_trigger("/notebook")

    assert skill is not None
    assert skill.name == "source-notebook"
    assert "create_source_notebook" in skill.tools
    assert "query_source_notebook" in skill.tools
    assert "notebook" in skill.artifact_types


def test_given_natural_notebooklm_slides_request_when_resolved_then_source_notebook_skill_is_used():
    """
    GIVEN a natural NotebookLM slide request without slash command
    WHEN the chat route resolves the skill
    THEN /notebook is selected so the deterministic artifact path can run
    """
    from server.routes.chat import _resolve_skill_invocation

    skill, content = _resolve_skill_invocation(
        "erstelle mir ein notebook lm slides für ki architektur mit bilder"
    )

    assert skill is not None
    assert skill.name == "source-notebook"
    assert content.startswith("erstelle mir")


def test_given_tool_schemas_when_loaded_then_source_notebook_tools_exist():
    """
    GIVEN tool schemas
    WHEN get_tool_schemas is called
    THEN source notebook tools are available to the model
    """
    from core.tools import get_tool_schemas

    names = {schema["function"]["name"] for schema in get_tool_schemas()}

    assert {"create_source_notebook", "query_source_notebook", "export_source_brief"} <= names


# The fast-path wrapper tests (DECK_STUDIO/SOURCE_BRIEF answer composition,
# web research in the PDF fast path) were retired with R36, together with the
# skill_fastpath module — test_quality_gate.py pins the studio-HTML quality
# markers (QA-/manifest links) at deck-render level instead.


def test_given_source_artifacts_when_normalized_then_quality_can_validate(tmp_path):
    """
    GIVEN notebook and brief artifact markers
    WHEN normalize_tool_result and validate_artifact run
    THEN both artifacts validate as real local outputs
    """
    from core.quality import normalize_tool_result, validate_artifact
    from core.source_notebook import create_source_notebook_index, export_source_brief_file

    source = tmp_path / "quality.md"
    source.write_text("Cited source notebooks need chunk IDs and source manifests.", encoding="utf-8")
    notebook = create_source_notebook_index(paths=[str(source)], title="Quality")
    brief = export_source_brief_file(notebook_path=str(notebook), question="What is needed?")

    notebook_result = normalize_tool_result("create_source_notebook", f"SOURCE_NOTEBOOK_FILE:{notebook}")
    brief_result = normalize_tool_result("export_source_brief", f"SOURCE_BRIEF_FILE:{brief}")

    assert notebook_result.artifacts[0]["type"] == "notebook"
    assert brief_result.artifacts[0]["type"] == "source_brief"
    assert validate_artifact(notebook_result.artifacts[0]).status == "passed"
    assert validate_artifact(brief_result.artifacts[0]).status == "passed"
