from pathlib import Path
import asyncio
import zipfile

import pytest


def _bundle(pdf_or_pptx: Path) -> Path:
    """Since wave 8 the diagnose sidecars live in <out>/artifacts/<stem>/."""
    return pdf_or_pptx.parent / "artifacts" / pdf_or_pptx.stem


class TestPitchDeckArtifactPerspective:
    def test_given_minimal_pitch_request_when_created_then_deck_pdf_and_preview_exist(self, werkbank):
        """
        GIVEN a user asks for a premium pitchdeck with little source material
        WHEN create_pitch_deck is called
        THEN it creates a real 16:9 PDF deck and animated HTML preview.
        """
        from core.tools import create_pitch_deck

        filename = "ephe_pytest_pitch_deck.pdf"
        pdf_path = werkbank / filename
        preview_path = pdf_path.with_suffix(".preview.html")
        for path in (pdf_path, preview_path):
            if path.exists():
                path.unlink()

        result = asyncio.run(
            create_pitch_deck(
                topic="Ephe Local AI",
                audience="investors",
                thesis="Local AI needs artifact-grade workflows.",
                filename=filename,
            )
        )

        assert result.startswith("PITCH_DECK_FILE:")
        assert str(pdf_path) in result
        assert str(preview_path) in result
        assert pdf_path.exists()
        assert preview_path.exists()
        assert "@keyframes enter" in preview_path.read_text(encoding="utf-8")
        assert (_bundle(pdf_path) / "scorecard.json").exists()
        assert (_bundle(pdf_path) / "manifest.json").exists()

    def test_given_pitch_deck_created_when_text_extracted_then_has_story_markers(self, werkbank):
        """
        GIVEN a generated deck artifact
        WHEN its PDF text is extracted
        THEN it contains deck-specific structure, not a plain report.
        """
        from core.tools import create_pitch_deck
        import pdfplumber

        filename = "ephe_pytest_deck_text.pdf"
        pdf_path = werkbank / filename
        if pdf_path.exists():
            pdf_path.unlink()

        result = asyncio.run(create_pitch_deck(topic="Ephe", filename=filename))
        assert result.startswith("PITCH_DECK_FILE:")

        with pdfplumber.open(str(pdf_path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            assert len(pdf.pages) >= 10

        assert "Animation Plan" not in text
        assert "Proof Object:" not in text
        assert "Evidence: assumptions" not in text
        assert "Problem" in text
        assert "Architecture Options" in text
        assert "Decision Ask" in text
        assert "TBD" not in text

    def test_given_pitch_deck_created_when_scorecard_read_then_quality_metadata_is_present(self, werkbank):
        """
        GIVEN a generated high-end deck
        WHEN its scorecard is read
        THEN Ephe exposes measurable quality criteria for the artifact.
        """
        from core.tools import create_pitch_deck
        import json

        filename = "ephe_pytest_scored_deck.pdf"
        pdf_path = werkbank / filename
        score_path = _bundle(pdf_path) / "scorecard.json"
        if score_path.exists():
            score_path.unlink()

        result = asyncio.run(
            create_pitch_deck(
                topic="Ephe Elite Deck",
                filename=filename,
                deck_profile="engineering-platform",
                design_theme="executive",
                source_notes="Based on local Ephe repository analysis.",
            )
        )

        assert "SCORECARD_FILE:" in result
        score = json.loads(score_path.read_text(encoding="utf-8"))
        assert score["quality_score"] >= 85
        assert score["minimum_score"] >= 86
        assert score["enterprise_grade"] is True
        assert score["narrative_score"] >= 90
        assert score["layout_score"] >= 90
        assert score["checks"]["slide_contract_complete"] is True
        assert score["checks"]["no_amateur_language"] is True

    def test_given_amateur_language_when_enterprise_deck_created_then_text_is_normalized_and_manifest_exists(self, werkbank):
        """
        GIVEN user-provided slide text contains amateur or playful wording
        WHEN a deck is generated whose score carries enterprise_grade
        THEN the exported deck removes that tone and writes a claim-spine manifest.
        """
        from core.tools import create_pitch_deck
        import json
        import pdfplumber

        filename = "ephe_pytest_enterprise_clean_deck.pdf"
        pdf_path = werkbank / filename
        result = asyncio.run(
            create_pitch_deck(
                topic="Fortune 500 AI Operating Model",
                filename=filename,
                slides=[
                    {
                        "title": "Awesome magic AI",
                        "claim": "This super cool workflow changes everything",
                        "body": "No fake metrics; use an executive proof spine.",
                        "visual": "system",
                        "proof": "Operating model",
                    }
                ] * 8,
                source_notes="User-provided concept; no external metrics.",
                evidence_level="user-provided",
                enterprise_grade=True,
            )
        )

        assert "MANIFEST_FILE:" in result
        assert "DECK_SPEC_FILE:" in result
        assert "VISUAL_QA_FILE:" in result
        assert "EVIDENCE_LEDGER_FILE:" in result
        with pdfplumber.open(str(pdf_path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages).lower()
        assert "awesome" not in text
        assert "magic ai" not in text
        assert "super cool" not in text
        manifest = json.loads((_bundle(pdf_path) / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["enterprise_grade"] is True
        assert len(manifest["claim_spine"]) == 8

    def test_given_minimal_deck_request_when_deck_spec_built_then_every_slide_has_v2_contract(self):
        """
        GIVEN a minimal deck request
        WHEN the DeckSpec is generated
        THEN each slide has role, headline, takeaway, visual spec, and source status.
        """
        from core.deck_model import build_deck_spec

        spec = build_deck_spec(
            title="KI Architektur 2026",
            audience="board",
            thesis="AI architecture decisions need source-grounded, local execution.",
            source_notes="Generated from user prompt; no external sources.",
            evidence_level="assumptions",
        )

        assert spec["title"] == "KI Architektur 2026"
        assert len(spec["slides"]) >= 10
        assert spec["adapter_strategy"]["active"] == "local_engine_v2"
        assert spec["adapter_strategy"]["hard_dependency"] is False
        assert spec["adapter_strategy"]["adapters"]["presenton"]["hard_dependency"] is False
        assert spec["adapter_strategy"]["adapters"]["pptxgenjs"]["hard_dependency"] is False
        for slide in spec["slides"]:
            assert slide["role"]
            assert slide["headline"]
            assert slide["takeaway"]
            assert slide["visual_spec"]["type"]
            assert slide["source_status"] in {"assumption_led", "source_grounded", "user_provided", "mixed"}

    def test_given_ten_slide_deck_when_visual_qa_runs_then_layout_roles_are_varied(self):
        """
        GIVEN a generated enterprise DeckSpec
        WHEN visual QA runs
        THEN it detects at least seven distinct layout or visual roles.
        """
        from core.deck_model import build_deck_spec
        from core.deck_quality import score_deck_spec

        spec = build_deck_spec(
            title="AI Architecture Board Deck",
            audience="board",
            thesis="AI architecture needs a decision-ready operating model.",
            source_notes="Generated from user prompt; no external sources.",
            evidence_level="assumptions",
        )
        score = score_deck_spec(spec, render_qa={"status": "passed", "checks": {"extractable_text": True}})

        assert score["visual_variety_score"] >= 90
        assert score["checks"]["layout_roles_varied"] is True
        assert score["checks"]["no_repeated_standard_visuals"] is True

    def test_given_repeated_placeholder_visuals_when_scored_then_enterprise_status_fails(self):
        """
        GIVEN a DeckSpec with repeated placeholder visuals
        WHEN quality scoring runs
        THEN enterprise quality fails instead of accepting a generic layout.
        """
        from core.deck_model import build_deck_spec
        from core.deck_quality import score_deck_spec

        spec = build_deck_spec(
            title="Weak Deck",
            audience="board",
            thesis="A weak deck repeats the same object.",
            source_notes="Generated from user prompt; no external sources.",
            evidence_level="assumptions",
        )
        for slide in spec["slides"]:
            slide["role"] = "problem"
            slide["visual_spec"] = {"type": "placeholder", "intent": "placeholder"}

        score = score_deck_spec(spec, render_qa={"status": "passed", "checks": {"extractable_text": True}})

        assert score["status"] == "failed"
        assert score["checks"]["layout_roles_varied"] is False
        assert score["checks"]["no_repeated_standard_visuals"] is False

    def test_given_pitch_deck_rendered_when_inspected_then_visual_quality_contract_passes(self, werkbank):
        """
        GIVEN a generated 16:9 pitch deck
        WHEN PDF text positions are inspected
        THEN v2 render QA passes without internal markers or unbounded visuals.
        """
        from core.tools import create_pitch_deck
        import json

        filename = "ephe_pytest_visual_bounds.pdf"
        pdf_path = werkbank / filename
        result = asyncio.run(create_pitch_deck(
            topic="KI Architektur 2026",
            audience="board and executive committee",
            thesis="KI Architektur 2026 braucht sichere lokale Agenten, Quellenbindung und nachvollziehbare Artefakte.",
            filename=filename,
        ))

        assert result.startswith("PITCH_DECK_FILE:")
        render_qa = json.loads((_bundle(pdf_path) / "render-qa.json").read_text(encoding="utf-8"))
        assert render_qa["status"] == "passed"
        assert render_qa["checks"]["no_internal_markers"] is True
        assert render_qa["checks"]["visuals_bounded"] is True
        assert render_qa["checks"]["layout_roles_varied"] is True

    def test_given_generated_pitch_deck_when_validated_then_render_quality_sidecar_passes(self, werkbank):
        """
        GIVEN a generated pitch deck PDF
        WHEN artifact validation runs
        THEN rendered layout QA is represented in the sidecar and validation passes.
        """
        from core.quality import validate_pitch_deck_artifact
        from core.tools import create_pitch_deck
        import json

        filename = "ephe_pytest_render_qa.pdf"
        pdf_path = werkbank / filename
        asyncio.run(create_pitch_deck(topic="Render QA Deck", filename=filename))

        report = validate_pitch_deck_artifact(str(pdf_path))
        qa_path = _bundle(pdf_path) / "render-qa.json"

        assert qa_path.exists()
        render_qa = json.loads(qa_path.read_text(encoding="utf-8"))
        assert render_qa["status"] == "passed"
        assert render_qa["checks"]["no_text_in_visual_column"] is True
        assert render_qa["checks"]["visuals_bounded"] is True
        assert report.status == "passed"


class TestPitchDeckContractsPerspective:
    def test_given_native_pptx_requested_when_created_then_package_has_editable_slides_and_sidecars(self, werkbank):
        """
        GIVEN a user asks for an editable enterprise deck
        WHEN create_pptx_deck is called
        THEN it creates a native PPTX package with editable text runs and quality sidecars.
        """
        from core.tools import create_pptx_deck

        filename = "ephe_pytest_native_deck.pptx"
        pptx_path = werkbank / filename
        if pptx_path.exists():
            pptx_path.unlink()
        for name in ("scorecard.json", "manifest.json", "qa.json"):
            side = _bundle(pptx_path) / name
            if side.exists():
                side.unlink()

        result = asyncio.run(
            create_pptx_deck(
                topic="Ephe Native PPTX",
                filename=filename,
                source_notes="User-provided enterprise objective.",
                evidence_level="user-provided",
                enterprise_grade=True,
            )
        )

        assert result.startswith("PPTX_DECK_FILE:")
        assert pptx_path.exists()
        assert (_bundle(pptx_path) / "scorecard.json").exists()
        assert (_bundle(pptx_path) / "manifest.json").exists()
        assert (_bundle(pptx_path) / "qa.json").exists()
        assert pptx_path.with_suffix(".contact-sheet.html").exists()

        with zipfile.ZipFile(pptx_path) as pptx:
            names = set(pptx.namelist())
            assert "ppt/presentation.xml" in names
            slide_names = sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            assert len(slide_names) >= 10
            slide_xml = pptx.read(slide_names[0]).decode("utf-8")
            assert "<a:t>" in slide_xml
            assert "Proof Object:" not in slide_xml
            assert "Animation Plan" not in slide_xml
            assert "Decision Thesis" in slide_xml or "Executive Summary" in slide_xml

    def test_given_tool_schema_when_inspected_then_pitch_deck_tool_is_available(self):
        """
        GIVEN Ephe exposes local tools to the model
        WHEN tool schemas are inspected
        THEN create_pitch_deck is available with deck-specific wording.
        """
        from core.tools import get_tool_schemas

        schemas = get_tool_schemas()
        schema = next(s["function"] for s in schemas if s["function"]["name"] == "create_pitch_deck")
        assert "pitch deck" in schema["description"].lower() and "slides" in schema["description"].lower()
        assert "topic" in schema["parameters"]["required"]
        assert "deck_profile" in schema["parameters"]["properties"]
        assert "design_theme" in schema["parameters"]["properties"]
        assert "evidence_level" in schema["parameters"]["properties"]
        assert "enterprise_grade" in schema["parameters"]["properties"]
        assert "deck_quality_profile" in schema["parameters"]["properties"]
        assert "source_notebook_path" in schema["parameters"]["properties"]
        assert "asset_paths" in schema["parameters"]["properties"]
        assert "brand_kit" in schema["parameters"]["properties"]

        pptx_schema = next(s["function"] for s in schemas if s["function"]["name"] == "create_pptx_deck")
        assert "editable" in pptx_schema["description"].lower() and ".pptx" in pptx_schema["description"].lower()
        assert "topic" in pptx_schema["parameters"]["required"]
        assert "template_path" in pptx_schema["parameters"]["properties"]
        assert "brand_primary" in pptx_schema["parameters"]["properties"]
        assert "deck_quality_profile" in pptx_schema["parameters"]["properties"]
        assert "source_notebook_path" in pptx_schema["parameters"]["properties"]
        assert "asset_paths" in pptx_schema["parameters"]["properties"]

    def test_given_deck_artifact_when_validated_then_quality_gate_passes(self, werkbank):
        """
        GIVEN a generated pitch deck PDF
        WHEN artifact validation runs
        THEN deck-specific validation passes.

        The deck is built here by itself: since the workbench runs per test, a test
        may no longer borrow another test's file name as proof of existence —
        that used to end quietly in a skip instead of in a check.
        """
        from core.quality import validate_pitch_deck_artifact
        from core.tools import create_pitch_deck

        filename = "ephe_pytest_gate_deck.pdf"
        asyncio.run(create_pitch_deck(topic="Ephe Gate Deck", filename=filename))
        pdf_path = werkbank / filename
        assert pdf_path.exists()

        report = validate_pitch_deck_artifact(str(pdf_path))
        assert report.artifact_type == "deck"
        assert report.status == "passed"
        assert report.warnings == []

    def test_given_existing_pptx_when_inspected_and_edited_then_template_layout_is_preserved(self, werkbank):
        """
        GIVEN an existing PPTX generated by Ephe
        WHEN the template tools inspect and edit it
        THEN the package remains a valid PPTX with QA/contact-sheet sidecars.
        """
        from core.tools import create_pptx_deck, edit_pptx_template, inspect_pptx_template
        from core.quality import validate_pptx_deck_artifact
        import json

        base = werkbank / "ephe_pytest_template_source.pptx"
        asyncio.run(
            create_pptx_deck(
                topic="Template Source",
                filename=base.name,
                source_notes="Template fixture.",
                evidence_level="user-provided",
            )
        )

        analysis_result = asyncio.run(inspect_pptx_template(str(base)))
        analysis_path = Path(analysis_result.removeprefix("PPTX_TEMPLATE_ANALYSIS_FILE:"))
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert analysis["slide_count"] >= 8
        assert analysis["editable_text_runs"] > 20

        edited_result = asyncio.run(
            edit_pptx_template(
                template_path=str(base),
                replacements={"Template Source": "Template Edited"},
                filename="ephe_pytest_template_edited.pptx",
            )
        )
        edited_path = Path(edited_result.splitlines()[0].removeprefix("PPTX_DECK_FILE:"))
        assert edited_path.exists()
        assert (_bundle(edited_path) / "qa.json").exists()
        assert edited_path.with_suffix(".contact-sheet.html").exists()
        assert validate_pptx_deck_artifact(str(edited_path)).status == "passed"

    def test_given_native_pptx_when_validated_then_quality_gate_passes(self, werkbank):
        """
        GIVEN a native PPTX deck with scorecard and manifest
        WHEN artifact validation runs
        THEN the PPTX-specific quality gate passes.

        Also without a borrowed proof from another test (see the deck gate).
        """
        from core.quality import validate_pptx_deck_artifact
        from core.tools import create_pptx_deck

        filename = "ephe_pytest_gate_deck.pptx"
        asyncio.run(create_pptx_deck(topic="Ephe Gate PPTX", filename=filename))
        pptx_path = werkbank / filename
        assert pptx_path.exists()

        report = validate_pptx_deck_artifact(str(pptx_path))
        assert report.artifact_type == "pptx"
        assert report.status == "passed"
        assert report.warnings == []
