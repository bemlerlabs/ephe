"""
P1 document-quality roadmap tests — design tokens, citation pipeline, PDF QA gates.

Covers core/doc_design.py (modular type scale, 8 pt spacing grid, color
tokens, role styles), the token-driven create_pdf renderer in
core/tools/pdf_tools.py (heading page-break policy, citation roundtrip,
render manifest), and the extended validate_pdf_artifact criteria in
core/quality.py. Documents without citation markers must behave exactly as
before (backcompat pins).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.doc_design import (
    CITATION_MARKER_SIZE_PT,
    COLOR_TOKENS,
    HEADING_ROLES,
    MARGIN_FLOOR_MM,
    MARGINS_MM,
    MARGINS_PT,
    ROLE_ORDER,
    ROLE_STYLES,
    SPACING_UNIT_PT,
    TYPE_SCALE_PT,
    TYPE_SCALE_RATIO,
    citation_reference_text,
    is_on_type_scale,
    scan_citation_numbers,
)


# Helpers


def _redirect_output_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_output_dir", lambda: str(tmp_path))


async def _create_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    filename: str = "doc-design-test.pdf",
    **kwargs,
) -> Path:
    """Create a PDF inside tmp_path and return its path (deliver contract checked)."""
    _redirect_output_dir(monkeypatch, tmp_path)
    from core.tools import create_pdf

    result = await create_pdf(title="Ephe Doc Design Test", content=content, filename=filename, **kwargs)
    lines = result.splitlines()
    assert lines[0].startswith("PDF_FILE:"), result
    assert lines[1].startswith("PDF_PAGES:"), result
    return Path(lines[0].removeprefix("PDF_FILE:"))


def _manifest_for(pdf_path: Path) -> dict:
    manifest_path = pdf_path.with_suffix(".doc-manifest.json")
    assert manifest_path.exists(), f"render manifest missing: {manifest_path}"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _extracted_text(pdf_path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


# Design tokens: type scale, spacing grid, colors, role styles


class TestTypeScale:

    def test_given_token_module_when_scale_inspected_then_modular_ratio_holds(self):
        assert TYPE_SCALE_RATIO == 1.25
        assert 10.0 in TYPE_SCALE_PT  # body step anchors the scale
        ratios = [higher / lower for lower, higher in zip(TYPE_SCALE_PT, TYPE_SCALE_PT[1:])]
        assert all(1.2 <= ratio <= 1.3 for ratio in ratios)

    def test_given_token_module_when_scale_inspected_then_values_are_deterministic(self):
        assert TYPE_SCALE_PT == (6.5, 8.0, 10.0, 12.5, 15.5, 19.5, 24.5)

    def test_given_arbitrary_sizes_when_checked_then_scale_membership_is_exact(self):
        for size in TYPE_SCALE_PT:
            assert is_on_type_scale(size)
        assert not is_on_type_scale(11.0)
        assert not is_on_type_scale(23.0)


class TestSpacingGrid:

    def test_given_margins_when_inspected_then_the_18mm_print_floor_is_met(self):
        assert min(MARGINS_MM.values()) >= MARGIN_FLOOR_MM == 18.0

    def test_given_margins_when_inspected_then_they_snap_to_the_8pt_grid(self):
        assert all(value % SPACING_UNIT_PT == 0 for value in MARGINS_PT.values())
        assert MARGINS_MM["left"] == pytest.approx(19.76, abs=0.01)
        assert MARGINS_MM["top"] == pytest.approx(25.4, abs=0.01)

    def test_given_role_styles_when_inspected_then_spacing_uses_grid_multiples(self):
        for role, spec in ROLE_STYLES.items():
            for key in ("space_before_pt", "space_after_pt", "left_indent_pt", "bullet_indent_pt"):
                if key in spec:
                    assert spec[key] % (SPACING_UNIT_PT / 2) == 0, (role, key, spec[key])


class TestColorTokens:

    def test_given_color_tokens_when_inspected_then_the_ephe_palette_is_pinned(self):
        assert COLOR_TOKENS["accent"] == "#16a34a"
        assert COLOR_TOKENS["accent_soft"] == "#22c55e"
        assert COLOR_TOKENS["ink"] == "#111827"
        assert COLOR_TOKENS["muted"] == "#6b7280"

    def test_given_color_tokens_when_inspected_then_all_are_valid_hex(self):
        for name, value in COLOR_TOKENS.items():
            assert re.fullmatch(r"#[0-9a-f]{6}", value), (name, value)


class TestRoleStyles:

    def test_given_role_styles_when_inspected_then_all_required_roles_exist(self):
        required = {"title", "h1", "h2", "body", "bullet", "caption", "citation"}
        assert required <= set(ROLE_ORDER)
        assert set(ROLE_ORDER) == set(ROLE_STYLES)

    def test_given_role_styles_when_inspected_then_sizes_are_on_the_token_scale(self):
        for role, spec in ROLE_STYLES.items():
            assert is_on_type_scale(spec["font_size_pt"]), role

    def test_given_heading_roles_when_inspected_then_they_keep_with_the_next_flowable(self):
        for role in HEADING_ROLES:
            assert ROLE_STYLES[role]["keep_with_next"] is True, role
        assert ROLE_STYLES["title"]["keep_with_next"] is True

    def test_given_text_roles_when_inspected_then_widow_and_orphan_protection_is_on(self):
        for role in ("body", "bullet", "numbered", "caption", "citation", "meta", "appendix"):
            assert ROLE_STYLES[role]["no_widows"] is True, role
            assert ROLE_STYLES[role]["no_orphans"] is True, role


# Citation pipeline: marker scan, superscript rendering, references section


class TestCitationScan:

    def test_given_markers_when_scanned_then_numbers_follow_first_appearance_order(self):
        content = "b [S002-C001] a [S001-C003] c [S002-C001] d"
        assert scan_citation_numbers(content) == {"S002-C001": 1, "S001-C003": 2}

    def test_given_content_without_markers_when_scanned_then_the_map_is_empty(self):
        assert scan_citation_numbers("plain text without chunk markers") == {}

    def test_given_chunk_id_when_reference_entry_built_then_the_format_is_stable(self):
        assert citation_reference_text(2, "S001-C001") == "[2] Source S001 - Chunk C001"


class TestCitationRoundtrip:

    async def test_given_marked_content_when_pdf_created_then_counters_and_references_render(self, tmp_path, monkeypatch):
        content = (
            "# Executive Summary\n"
            "Grounded claim one. [S001-C001]\n"
            "Grounded claim two. [S002-C001]\n"
            "Repeated grounding of claim one. [S001-C001]\n"
        )
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="citation-roundtrip.pdf")
        text = _extracted_text(pdf_path)

        assert "References" in text
        assert "[1] Source S001 - Chunk C001" in text
        assert "[2] Source S002 - Chunk C001" in text
        assert "[S001-C001]" not in text  # raw chunk markers are consumed by the renderer

        manifest = _manifest_for(pdf_path)
        assert manifest["citations"]["inline_count"] == 3
        assert manifest["citations"]["references"] == [
            {"number": 1, "chunk_id": "S001-C001"},
            {"number": 2, "chunk_id": "S002-C001"},
        ]
        assert CITATION_MARKER_SIZE_PT in manifest["font_sizes_pt"]

    async def test_given_marked_content_when_validated_then_citation_integrity_passes(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nClaim. [S001-C001]\n", filename="citation-integrity.pdf"
        )
        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.status == "passed"
        assert report.warnings == []
        assert report.checks["citations"] == {
            "inline_count": 1,
            "reference_count": 1,
            "integrity_ok": True,
        }

    async def test_given_content_without_markers_when_pdf_created_then_no_references_section_is_added(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path,
            monkeypatch,
            "# Executive Summary\nPlain grounded text without chunk markers.\n",
            filename="no-markers.pdf",
        )
        text = _extracted_text(pdf_path)

        assert "References" not in text
        manifest = _manifest_for(pdf_path)
        assert manifest["citations"] == {"marker_format": "S###-C###", "inline_count": 0, "references": []}


# Heading page-break policy (render-level pin)


class TestHeadingPolicy:

    async def test_given_multipage_document_when_validated_then_no_heading_sits_in_the_bottom_10_percent(self, tmp_path, monkeypatch):
        filler = "Deterministic filler sentence for the page break policy check. " * 20
        sections = "\n".join(f"## Section {index:02d}\n{filler}" for index in range(1, 9))
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, f"# Executive Summary\n{sections}", filename="heading-policy.pdf"
        )

        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            assert len(pdf.pages) >= 2  # the fixture really spans multiple pages

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.checks["manifest_ok"] is True
        assert report.checks["heading_bottom_pages"] == []
        assert all("bottom 10%" not in warning for warning in report.warnings)


# Extended validate_pdf_artifact criteria


def _write_probe_manifest(tmp_path: Path, manifest: dict) -> Path:
    """Write a minimal artifact + manifest for direct helper-level checks."""
    pdf_path = tmp_path / "probe.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    pdf_path.with_suffix(".doc-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pdf_path


class TestExtendedValidation:

    async def test_given_token_build_when_validated_then_margin_and_scale_checks_pass(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nBody text.\n", filename="extended-checks.pdf"
        )
        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.checks["margins_ok"] is True
        assert min(report.checks["margins_mm"].values()) >= 18.0
        assert report.checks["type_scale_ok"] is True
        assert report.checks["off_scale_sizes_pt"] == []

    def test_given_off_scale_font_sizes_in_manifest_when_validated_then_a_warning_is_emitted(self, tmp_path):
        from core.quality import _extended_pdf_doc_checks

        pdf_path = _write_probe_manifest(tmp_path, {
            "margins_mm": {"left": 19.76, "right": 19.76, "top": 25.4, "bottom": 25.4},
            "font_sizes_pt": [10.0, 11.3],
            "roles": {},
            "heading_roles": [],
            "citations": {"inline_count": 0, "references": []},
        })

        warnings, checks = _extended_pdf_doc_checks(pdf_path, "")

        assert checks["type_scale_ok"] is False
        assert checks["off_scale_sizes_pt"] == [11.3]
        assert any("type scale" in warning for warning in warnings)

    def test_given_margin_violation_in_manifest_when_validated_then_a_warning_is_emitted(self, tmp_path):
        from core.quality import _extended_pdf_doc_checks

        pdf_path = _write_probe_manifest(tmp_path, {
            "margins_mm": {"left": 15.0, "right": 15.0, "top": 25.4, "bottom": 25.4},
            "font_sizes_pt": [10.0],
            "roles": {},
            "heading_roles": [],
            "citations": {"inline_count": 0, "references": []},
        })

        warnings, checks = _extended_pdf_doc_checks(pdf_path, "")

        assert checks["margins_ok"] is False
        assert any("18 mm" in warning for warning in warnings)

    def test_given_missing_reference_entry_when_validated_then_integrity_fails(self, tmp_path):
        from core.quality import _extended_pdf_doc_checks

        pdf_path = _write_probe_manifest(tmp_path, {
            "margins_mm": {"left": 19.76, "right": 19.76, "top": 25.4, "bottom": 25.4},
            "font_sizes_pt": [10.0],
            "roles": {},
            "heading_roles": [],
            "citations": {
                "inline_count": 1,
                "references": [{"number": 1, "chunk_id": "S001-C001"}],
            },
        })

        warnings, checks = _extended_pdf_doc_checks(pdf_path, "")

        assert checks["citations"]["integrity_ok"] is False
        assert any("reference entry missing" in warning for warning in warnings)

    def test_given_orphan_reference_entries_without_markers_when_validated_then_a_warning_is_emitted(self, tmp_path):
        from core.quality import _extended_pdf_doc_checks

        pdf_path = _write_probe_manifest(tmp_path, {
            "margins_mm": {"left": 19.76, "right": 19.76, "top": 25.4, "bottom": 25.4},
            "font_sizes_pt": [10.0],
            "roles": {},
            "heading_roles": [],
            "citations": {"inline_count": 0, "references": []},
        })

        warnings, checks = _extended_pdf_doc_checks(pdf_path, "[2] Source S001 - Chunk C001")

        assert checks["citations"]["integrity_ok"] is False
        assert any("without inline citation markers" in warning for warning in warnings)

    def test_given_unreadable_manifest_when_validated_then_a_warning_is_emitted(self, tmp_path):
        from core.quality import _extended_pdf_doc_checks

        pdf_path = tmp_path / "broken.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        pdf_path.with_suffix(".doc-manifest.json").write_text("{not json", encoding="utf-8")

        warnings, checks = _extended_pdf_doc_checks(pdf_path, "")

        assert checks == {"manifest_ok": False}
        assert any("manifest is unreadable" in warning for warning in warnings)


# Backcompat pins: documents without markers / without manifest


class TestBackcompatPins:

    async def test_given_document_without_markers_when_validated_then_it_stays_valid_without_warnings(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path,
            monkeypatch,
            "# Executive Summary\nReadable text with <literal> value.\n## Source Notes\n- local test",
            filename="backcompat.pdf",
        )
        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.status == "passed"
        assert report.warnings == []
        assert report.checks["citations"]["integrity_ok"] is True
        assert report.checks["margins_ok"] is True

    async def test_given_pdf_without_render_manifest_when_validated_then_extended_checks_are_skipped(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nLegacy style document.\n", filename="no-manifest.pdf"
        )
        pdf_path.with_suffix(".doc-manifest.json").unlink()
        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.status == "passed"
        assert report.warnings == []
        assert report.checks == {}  # no manifest, no extended criteria applied

    async def test_given_create_pdf_when_called_then_the_deliver_contract_is_unchanged(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nHello.\n", filename="Weird Name!!.pdf"
        )

        assert pdf_path.name == "Weird_Name.pdf"
        assert pdf_path.exists()
        manifest = _manifest_for(pdf_path)
        assert manifest["schema_version"] == 1
        assert manifest["heading_roles"] == ["h1", "h2", "h3"]
        assert manifest["type_scale_ratio"] == 1.25
