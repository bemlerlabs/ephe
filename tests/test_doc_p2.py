"""
P2 document-quality roadmap tests — callouts, tables, cover+TOC, charts, fonts.

Covers the P2 markdown extensions of create_pdf in core/tools/pdf_tools.py
(GitHub-style callout markers, pipe tables, whole-line chart embedding,
``document=True`` cover + TOC), the additive render-manifest fields, and the
additive validate_pdf_artifact criteria in core/quality.py. Documents without
markers or the document flag must behave exactly as before (backcompat pins),
and the font-strategy decision is pinned as machine-readable manifest data.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from core.doc_design import CALLOUT_KINDS, COLOR_TOKENS, ROLE_ORDER, ROLE_STYLES, blend_hex_toward_paper


# Helpers


def _redirect_output_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_output_dir", lambda: str(tmp_path))


async def _create_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    filename: str = "doc-p2-test.pdf",
    **kwargs,
) -> Path:
    """Create a PDF inside tmp_path and return its path (deliver contract checked)."""
    _redirect_output_dir(monkeypatch, tmp_path)
    from core.tools import create_pdf

    result = await create_pdf(title="Ephe P2 Structure Test", content=content, filename=filename, **kwargs)
    lines = result.splitlines()
    assert lines[0].startswith("PDF_FILE:"), result
    assert lines[1].startswith("PDF_PAGES:"), result
    return Path(lines[0].removeprefix("PDF_FILE:"))


def _manifest_for(pdf_path: Path) -> dict:
    manifest_path = pdf_path.with_suffix(".doc-manifest.json")
    assert manifest_path.exists(), f"render manifest missing: {manifest_path}"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _pages_and_text(pdf_path: Path):
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return list(pdf.pages), "\n".join(page.extract_text() or "" for page in pdf.pages)


def _write_png(dest: Path, width: int = 900, height: int = 300) -> Path:
    """Write a real (tiny) PNG via struct/zlib — 8-bit RGB, one flat color."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    row = b"\x00" + b"\x11\x18\x27" * width  # ink-ish scanline with filter byte
    raw = row * height
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    dest.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return dest


# Callout roles: GitHub-style markers -> tinted boxes


class TestCalloutTokens:

    def test_given_callout_kinds_when_inspected_then_surfaces_and_bars_come_from_color_tokens(self):
        assert set(CALLOUT_KINDS) == {"note", "tip", "warning"}
        for spec in CALLOUT_KINDS.values():
            assert spec["surface_token"] in COLOR_TOKENS
            assert spec["bar_token"] in COLOR_TOKENS

    def test_given_token_color_when_blended_toward_paper_then_the_surface_stays_deterministic(self):
        assert blend_hex_toward_paper("#22c55e") == "#e4f8ec"
        assert blend_hex_toward_paper(COLOR_TOKENS["warn"]) == "#f6eae1"
        # 0.12 keep ratio: surface must be much closer to paper than to accent.
        surface = int(blend_hex_toward_paper(COLOR_TOKENS["accent_soft"])[1:3], 16)
        token = int(COLOR_TOKENS["accent_soft"][1:3], 16)
        paper = int(COLOR_TOKENS["paper"][1:3], 16)
        assert abs(surface - paper) < abs(token - paper)


class TestCalloutRendering:

    async def test_given_note_and_warning_markers_when_pdf_created_then_callouts_render_with_manifest_counts(self, tmp_path, monkeypatch):
        content = (
            "# Executive Summary\n"
            "> [!NOTE]\n> Grounded note text.\n>\n> Second note paragraph.\n"
            "> [!WARNING]\n> Warned risk text.\n"
        )
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="callout-roundtrip.pdf")
        pages, text = _pages_and_text(pdf_path)

        assert len(pages) >= 1
        assert "Note" in text
        assert "Grounded note text." in text
        assert "Second note paragraph." in text
        assert "Warning" in text
        assert "Warned risk text." in text
        assert "> [!NOTE]" not in text and "> [!WARNING]" not in text  # markers are consumed

        manifest = _manifest_for(pdf_path)
        assert manifest["callouts"] == {"count": 2, "kinds": {"note": 1, "tip": 0, "warning": 1}}

    async def test_given_callout_document_when_validated_then_no_new_warnings_appear(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path,
            monkeypatch,
            "# Executive Summary\n> [!TIP]\n> Tip text for the callout box.\n",
            filename="callout-validate.pdf",
        )
        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.status == "passed"
        assert report.warnings == []
        assert report.checks["citations"]["integrity_ok"] is True

    async def test_given_lowercase_marker_when_pdf_created_then_no_callout_behavior_is_triggered(self, tmp_path, monkeypatch):
        content = "# Executive Summary\n> [!note]\n> lowercase is not the convention.\n"
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="callout-lowercase.pdf")
        _, text = _pages_and_text(pdf_path)

        assert "> [!note]" in text  # stays plain body text (GitHub-style strictness)
        assert _manifest_for(pdf_path)["callouts"]["count"] == 0


# Tables: markdown pipe tables -> reportlab Table with grid


class TestTableRendering:

    async def test_given_pipe_table_when_pdf_created_then_pdfplumber_extracts_the_cells(self, tmp_path, monkeypatch):
        content = (
            "# Executive Summary\n"
            "| Layer | Status |\n"
            "| --- | --- |\n"
            "| Renderer | done |\n"
            "| QA gate | green |\n"
        )
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="table-roundtrip.pdf")
        pages, text = _pages_and_text(pdf_path)

        tables = [table for page in pages for table in page.extract_tables()]
        assert len(tables) == 1  # roadmap G3 gate: the table is really extractable
        assert tables[0] == [
            ["Layer", "Status"],
            ["Renderer", "done"],
            ["QA gate", "green"],
        ]
        assert _manifest_for(pdf_path)["tables"] == {"count": 1, "column_counts": [2]}
        assert report_status_is_clean(pdf_path)

    async def test_given_ragged_source_rows_when_pdf_created_then_cells_are_padded_to_the_header_width(self, tmp_path, monkeypatch):
        content = (
            "# Executive Summary\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| one |\n"
            "| two | extra cell |\n"
        )
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="table-ragged.pdf")
        pages, _ = _pages_and_text(pdf_path)

        tables = [table for page in pages for table in page.extract_tables()]
        assert len(tables) == 1
        assert all(len(row) == 2 for row in tables[0])
        assert tables[0][1][0] == "one"
        assert tables[0][2][0] == "two"
        assert _manifest_for(pdf_path)["tables"]["column_counts"] == [2]

    async def test_given_pipe_line_without_separator_when_pdf_created_then_it_stays_plain_body_text(self, tmp_path, monkeypatch):
        content = "# Executive Summary\n| stray | pipe | line |\n"
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="table-backcompat.pdf")
        _, text = _pages_and_text(pdf_path)

        assert "| stray | pipe | line |" in text
        assert _manifest_for(pdf_path)["tables"]["count"] == 0


# Cover + TOC: create_pdf(document=True)


class TestCoverAndToc:

    async def test_given_document_true_when_pdf_created_then_cover_toc_and_content_render(self, tmp_path, monkeypatch):
        content = "# Executive Summary\nBody text of the report.\n## Findings\n- Finding one.\n"
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="cover-toc.pdf", document=True)
        pages, text = _pages_and_text(pdf_path)

        assert len(pages) >= 3  # cover + TOC + content
        page1 = pages[0].extract_text() or ""
        assert "Ephe" in page1
        assert "Ephe P2 Structure Test" in page1  # display title on the cover
        assert "Inhaltsverzeichnis" in (pages[1].extract_text() or "")
        assert "Executive Summary" in (pages[1].extract_text() or "")  # TOC lists the H1

        manifest = _manifest_for(pdf_path)
        assert manifest["has_cover"] is True
        entry_texts = [entry["text"] for entry in manifest["toc_entries"]]
        assert "Executive Summary" in entry_texts and "Findings" in entry_texts
        assert all(entry["page"] >= 3 for entry in manifest["toc_entries"])  # none point at cover/TOC

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))
        assert report.status == "passed"
        assert report.warnings == []
        assert report.checks["cover"] == {"declared": True, "present": True}

    async def test_given_document_true_when_pages_measured_then_the_deliver_contract_counts_the_cover(self, tmp_path, monkeypatch):
        _redirect_output_dir(monkeypatch, tmp_path)
        from core.tools import create_pdf

        result = await create_pdf(
            title="Ephe P2 Structure Test",
            content="# Executive Summary\nTiny body.\n",
            filename="cover-page-count.pdf",
            document=True,
        )
        lines = result.splitlines()
        pdf_path = Path(lines[0].removeprefix("PDF_FILE:"))
        pages, _ = _pages_and_text(pdf_path)

        assert int(lines[1].removeprefix("PDF_PAGES:")) == len(pages)  # measured, cover included
        assert len(pages) == 3

    async def test_given_document_true_when_toc_built_then_entries_match_the_h1_h2_set_in_content_order(self, tmp_path, monkeypatch):
        # All required report sections present, so the template adds no
        # backfill headings and the TOC order is the pure content order.
        content = (
            "# Executive Summary\nText.\n"
            "## Findings\nMore text.\n"
            "## Next Steps\nEven more text.\n"
            "### Source Notes\n- note\n"
        )
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="cover-toc-order.pdf", document=True)

        manifest = _manifest_for(pdf_path)
        # H1 and H2 of the content, in render order; the H3 stays out.
        assert [(entry["level"], entry["text"]) for entry in manifest["toc_entries"]] == [
            (1, "Executive Summary"),
            (2, "Findings"),
            (2, "Next Steps"),
        ]

    async def test_given_default_document_false_when_pdf_created_then_no_cover_or_toc_is_added(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nPlain short body.\n", filename="no-cover.pdf"
        )
        pages, text = _pages_and_text(pdf_path)

        assert len(pages) == 1
        assert "Inhaltsverzeichnis" not in text
        manifest = _manifest_for(pdf_path)
        assert manifest["has_cover"] is False
        assert manifest["toc_entries"] == []
        assert _manifest_for(pdf_path)["callouts"]["count"] == 0

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))
        assert report.status == "passed"
        assert report.warnings == []


# Chart embedding: ![chart](/absolute/path.png)


class TestChartEmbedding:

    async def test_given_existing_png_when_referenced_then_the_image_embeds_at_content_width(self, tmp_path, monkeypatch):
        chart = _write_png(tmp_path / "chart.png", width=900, height=300)
        content = f"# Executive Summary\n![chart]({chart})\nBody after the chart.\n"
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="chart-embed.pdf")
        pages, text = _pages_and_text(pdf_path)

        images = [image for page in pages for image in page.images]
        assert len(images) == 1
        content_width = pages[0].width - 2 * 56.0  # A4 width minus the token margins
        assert images[0]["width"] == pytest.approx(content_width, abs=1.5)
        assert images[0]["width"] / images[0]["height"] == pytest.approx(3.0, abs=0.05)  # aspect preserved
        assert "![chart]" not in text  # the marker is consumed by the renderer

        manifest = _manifest_for(pdf_path)
        assert manifest["images"] == {"count": 1, "missing_count": 0}

    async def test_given_missing_png_when_referenced_then_an_honest_placeholder_renders_without_crash(self, tmp_path, monkeypatch):
        missing = tmp_path / "nowhere" / "chart.png"
        content = f"# Executive Summary\n![chart]({missing})\n"
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="chart-missing.pdf")
        _, text = _pages_and_text(pdf_path)

        # Long unbreakable paths wrap mid-word in the placeholder paragraph,
        # so the path itself is checked on the de-linebroken glyph stream.
        assert "[chart missing:" in text
        assert str(missing) in text.replace("\n", "")
        manifest = _manifest_for(pdf_path)
        assert manifest["images"] == {"count": 0, "missing_count": 1}

    async def test_given_unreadable_image_file_when_referenced_then_a_placeholder_renders_without_crash(self, tmp_path, monkeypatch):
        bogus = tmp_path / "bogus.png"
        bogus.write_bytes(b"this is not a png")
        content = f"# Executive Summary\n![chart]({bogus})\n"
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="chart-bogus.pdf")
        _, text = _pages_and_text(pdf_path)

        assert "[chart missing:" in text
        assert str(bogus) in text.replace("\n", "")
        assert _manifest_for(pdf_path)["images"]["missing_count"] == 1


# Font strategy pin: honest evaluation, documented decision


class TestFontStrategy:

    async def test_given_font_evaluation_when_pdf_created_then_the_helvetica_decision_is_pinned(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nBody.\n", filename="font-strategy.pdf"
        )

        manifest = _manifest_for(pdf_path)
        assert manifest["font_strategy"] == "base14-helvetica-winansi"
        # All role fonts stay in the base-14 Helvetica family.
        assert all(
            ROLE_STYLES[role]["font_name"] in ("Helvetica", "Helvetica-Bold")
            for role in ROLE_ORDER
        )


# P2 QA checks: additive warning criteria in validate_pdf_artifact


def _doctored_manifest(pdf_path: Path, **overrides) -> None:
    """Rewrite the render manifest of a real PDF with P2 field overrides."""
    manifest = _manifest_for(pdf_path)
    manifest.update(overrides)
    pdf_path.with_suffix(".doc-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def report_status_is_clean(pdf_path: Path) -> bool:
    from core.quality import validate_pdf_artifact

    report = validate_pdf_artifact(str(pdf_path))
    return report.status == "passed" and report.warnings == []


class TestP2QualityChecks:

    def test_given_ragged_extracted_table_when_checked_then_a_column_consistency_warning_is_emitted(self):
        from core.quality import _table_column_consistency_warnings

        ragged = [[["a", "b"], ["c"], ["d", "e", "f"]]]
        warnings = _table_column_consistency_warnings(ragged)
        assert len(warnings) == 1
        assert "inconsistent column counts" in warnings[0]

        assert _table_column_consistency_warnings([[["a", "b"], ["c", "d"]]]) == []

    async def test_given_manifest_with_tables_but_none_extractable_when_validated_then_a_warning_is_emitted(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nNo tables here.\n", filename="qa-tables.pdf"
        )
        _doctored_manifest(pdf_path, tables={"count": 1, "column_counts": [2]})

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert any("declares tables but none were extractable" in warning for warning in report.warnings)
        assert report.checks["tables"]["extracted"] == 0

    async def test_given_manifest_claims_cover_when_page_1_has_none_then_a_warning_is_emitted(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nPlain one-pager.\n", filename="qa-cover.pdf"
        )
        _doctored_manifest(pdf_path, has_cover=True)

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert any("cover markers missing" in warning for warning in report.warnings)
        assert report.checks["cover"] == {"declared": True, "present": False}

    async def test_given_manifest_with_bogus_toc_entry_when_validated_then_a_warning_is_emitted(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nPlain body.\n", filename="qa-toc.pdf"
        )
        _doctored_manifest(pdf_path, toc_entries=[{"level": 1, "text": "Ghost Section", "page": 99}])

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert any("TOC entries missing" in warning for warning in report.warnings)
        assert report.checks["toc"]["missing"] == ["Ghost Section"]

    async def test_given_p1_manifest_without_p2_fields_when_validated_then_it_stays_warning_free(self, tmp_path, monkeypatch):
        pdf_path = await _create_pdf(
            tmp_path, monkeypatch, "# Executive Summary\nReadable text.\n", filename="qa-legacy.pdf"
        )
        manifest = _manifest_for(pdf_path)
        for key in ("callouts", "tables", "images", "has_cover", "toc_entries", "title", "font_strategy"):
            manifest.pop(key, None)
        pdf_path.with_suffix(".doc-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        from core.quality import validate_pdf_artifact

        report = validate_pdf_artifact(str(pdf_path))

        assert report.status == "passed"
        assert report.warnings == []


    async def test_given_colon_alignment_when_table_rendered_then_cells_align(self, tmp_path, monkeypatch):
        """P2 leftover item: ':---:' centers, '---:' right-aligns — geometry via
        pdfplumber: the right-aligned short cell ('42') starts further to the right
        than the horizontal middle of the second column."""
        content = (
            "# Alignment\n"
            "| name | value |\n"
            "|:-----|------:|\n"
            "| left-aligned-long | 42 |\n"
        )
        pdf_path = await _create_pdf(tmp_path, monkeypatch, content, filename="alignment-check.pdf")
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            words = pdf.pages[0].extract_words()
        by_text = {w["text"]: w for w in words if w["text"] in ("left-aligned-long", "42")}
        assert "left-aligned-long" in by_text and "42" in by_text
        table = pdf_path  # the right column starts at content_width/2 + the left margin
        assert by_text["42"]["x0"] > 300  # right-aligned → the right table half
