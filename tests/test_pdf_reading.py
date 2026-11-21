"""
PDF reading tests — GWT method, 3x depth from different angles.

GIVEN: a PDF file on the filesystem
WHEN:  read_file() is called with it
THEN:  the text content is returned correctly

GIVEN: a corrupt / non-PDF file with a .pdf extension
WHEN:  read_file() is called with it
THEN:  an informative error text is returned (no crash)

GIVEN: the tool schema for read_file
WHEN:  it is checked for PDF support
THEN:  the description mentions PDF as a supported format
"""

import os
import struct
import tempfile
import asyncio
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch):
    """Issue #16: create_pdf resolved output_dir from the REAL
    ~/.ephe/engine.json at call time — with a user-configured output_dir
    the ~/Downloads pins failed. Same isolation pattern as
    tests/test_setup_status.py: every test sees a pristine default config."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    yield
    import core.model_provider as mp

    mp._ACTIVE_OVERRIDE = None


# Angle 1: unit — read_file with a real PDF

class TestPDFReadUnitPerspective:
    """GIVEN a real minimal PDF, WHEN read_file called, THEN text extracted."""

    def _make_real_pdf(self, dest: Path, content: str = "Ephe PDF Test Content") -> Path:
        """Creates a real, pdfplumber-readable PDF via reportlab or fpdf2."""
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            pdf.cell(0, 10, content)
            pdf.output(str(dest))
            return dest
        except ImportError:
            pass
        # Fallback: use pdfplumber + minimal PDF bytes (Latin-1 text)
        import struct
        # Write a minimal PDF with a text stream (UTF-compatible subset)
        minimal = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length 44>>\nstream\nBT /F1 12 Tf 100 700 Td"
            b" (Ephe Test) Tj ET\nendstream\nendobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"0000000266 00000 n \n"
            b"0000000360 00000 n \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n441\n%%EOF\n"
        )
        dest.write_bytes(minimal)
        return dest

    @pytest.mark.asyncio
    async def test_given_pdf_when_read_file_then_returns_text(self):
        """
        GIVEN: a .pdf file sits in the allowed /tmp path
        WHEN:  read_file() is called
        THEN:  the return value is a non-empty string (no crash)
        """
        from core.tools import read_file
        import tempfile

        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            pdf_path = Path(tmp) / "test.pdf"
            self._make_real_pdf(pdf_path)

            result = await read_file(str(pdf_path))

            # Perspective 1: type check
            assert isinstance(result, str), "THEN: result muss ein String sein"
            # Perspective 2: not empty
            assert len(result.strip()) > 0, "THEN: result darf nicht leer sein"
            # Perspective 3: no raw binary dump
            assert "%PDF" not in result, "THEN: Keine rohen PDF-Bytes im Output"

    @pytest.mark.asyncio
    async def test_given_corrupt_pdf_when_read_file_then_no_crash(self):
        """
        GIVEN: a .pdf file with invalid content (null bytes)
        WHEN:  read_file() is called
        THEN:  no crash — informative fallback text as a string
        """
        from core.tools import read_file
        import tempfile

        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            corrupt_pdf = Path(tmp) / "corrupt.pdf"
            corrupt_pdf.write_bytes(b"\x00" * 100)

            result = await read_file(str(corrupt_pdf))

            # Perspective 1: no exception crash
            assert isinstance(result, str), "THEN: Auch Fehler muss String sein"
            # Perspective 2: the content explains the problem
            assert len(result) > 0, "THEN: Fehler-String darf nicht leer sein"
            # Perspective 3: carries the file name for user context
            assert "corrupt.pdf" in result or "Could not" in result or "no extractable" in result, (
                f"THEN: Fehler-String soll hilfreich sein, got: {result[:100]}"
            )


# Angle 2: integration — the tool schema documents PDF support

class TestPDFToolSchemaIntegrationPerspective:
    """GIVEN the tool schema, WHEN inspected, THEN PDF is mentioned."""

    def test_given_tool_schema_when_read_file_checked_then_mentions_pdf(self):
        """
        GIVEN: the tool schema system is loaded
        WHEN:  the description of read_file is fetched
        THEN:  PDF is mentioned as a supported format
        """
        from core.tools import get_tool_schemas
        schemas = get_tool_schemas()
        read_file_schema = next(
            (s for s in schemas if s.get("function", {}).get("name") == "read_file"),
            None
        )
        assert read_file_schema is not None, "THEN: read_file muss im Schema existieren"
        description = read_file_schema.get("function", {}).get("description", "")
        assert "pdf" in description.lower(), (
            f"THEN: Tool-Schema sollte 'pdf' erwähnen, got: {description[:200]}"
        )


# Angle 3: system level — pyproject.toml carries pdfplumber

class TestPDFDependencySystemPerspective:
    """GIVEN pyproject.toml, WHEN inspected, THEN pdfplumber is listed."""

    def test_given_pyproject_when_read_then_pdfplumber_in_dependencies(self):
        """
        GIVEN: pyproject.toml exists
        WHEN:  the dependencies are read
        THEN:  pdfplumber is listed as a dependency
        """
        from tests.toml_compat import tomllib
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        assert pyproject.exists(), "THEN: pyproject.toml muss existieren"
        data = tomllib.loads(pyproject.read_text())
        deps = data.get("project", {}).get("dependencies", [])
        dep_names = [d.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
                     for d in deps]
        assert "pdfplumber" in dep_names, (
            f"THEN: pdfplumber muss in dependencies sein, found: {dep_names}"
        )

    def test_given_venv_when_import_attempted_then_pdfplumber_importable(self):
        """
        GIVEN: the virtual environment is activated
        WHEN:  pdfplumber is imported
        THEN:  the import does not fail
        """
        try:
            import pdfplumber
        except ImportError:
            pytest.fail("THEN: pdfplumber muss importierbar sein — führe 'pip install pdfplumber' aus")


def _pdf_path_from(result: str) -> Path:
    """B3 deliver contract: 'PDF_FILE:<path>\nPDF_PAGES:<n>' → path + page-count pin."""
    lines = result.splitlines()
    assert lines[0].startswith("PDF_FILE:"), result
    assert len(lines) > 1 and lines[1].startswith("PDF_PAGES:"), result
    assert int(lines[1].removeprefix("PDF_PAGES:")) >= 1, result
    return Path(lines[0].removeprefix("PDF_FILE:"))


class TestPDFCreationPerspective:
    """GIVEN create_pdf writes a user-facing PDF, WHEN text is extracted, THEN glyphs are clean."""

    @pytest.mark.asyncio
    async def test_given_pdf_created_when_text_extracted_then_no_broken_glyphs(self, werkbank):
        from core.tools import create_pdf
        import pdfplumber

        filename = "ephe_pytest_glyph_check.pdf"
        path = werkbank / filename
        if path.exists():
            path.unlink()

        result = await create_pdf(
            title="Ephe PDF Glyph Check",
            content="# Ergebnis\n- Robuste Bullet-Zeile\nNormaler Absatz",
            filename=filename,
        )

        assert result == f"PDF_FILE:{path}\nPDF_PAGES:1"  # B3: the deliver names the path + page count
        assert path.exists()
        with pdfplumber.open(str(path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        assert "Ephe PDF Glyph Check" in text
        assert "Ephe" in text
        assert "(cid:" not in text
        assert "Erstellt von n Ephe" not in text

    @pytest.mark.asyncio
    async def test_given_high_end_report_when_created_then_sections_footer_and_clean_filename_exist(self, werkbank):
        """
        GIVEN a user asks for a polished report with an unsafe filename
        WHEN create_pdf writes the file
        THEN the PDF has clean extractable sections and a sanitized local filename.
        """
        from core.tools import create_pdf
        import pdfplumber

        result = await create_pdf(
            title="Ephe Projektanalyse",
            content="# Ist-Zustand\n## Risiken\n- Fehlende Tests\n## Nächste Schritte\n- pytest ausführen",
            filename="../Ephe Projektanalyse 2026!!.pdf",
        )

        assert result.startswith("PDF_FILE:")
        output = _pdf_path_from(result)
        assert output.parent == werkbank, "A1: geboren in der Werkbank, nicht im Downloads-Ordner"
        assert output.name == "Ephe_Projektanalyse_2026.pdf"
        assert output.exists()

        with pdfplumber.open(str(output)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        assert "Ephe Projektanalyse" in text
        assert "Ist-Zustand" in text
        assert "Risiken" in text
        assert "Nächste Schritte" in text
        assert "Seite 1" in text

    @pytest.mark.asyncio
    async def test_given_pdf_created_with_markdown_and_angle_brackets_then_text_is_clean_and_extractable(self):
        """
        GIVEN a report contains markdown emphasis, numbered actions, and angle brackets
        WHEN create_pdf writes the document
        THEN user content remains extractable and is not interpreted as broken markup.
        """
        from core.tools import create_pdf
        import pdfplumber

        result = await create_pdf(
            title="Ephe Artifact Quality",
            content=(
                "# Executive Summary\n"
                "This PDF must keep **important** details and literal values like <project-id>.\n"
                "1. Validate layout\n"
                "2. Confirm extractable text\n"
                "### Source Notes\n"
                "- Generated from a local user request\n"
            ),
            filename="ephe-artifact-quality.pdf",
        )

        output = _pdf_path_from(result)
        assert output.exists()

        with pdfplumber.open(str(output)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        assert "Executive Summary" in text
        assert "important" in text
        assert "<project-id>" in text
        assert "1. Validate layout" in text
        assert "2. Confirm extractable text" in text
        assert "Source Notes" in text
        assert "(cid:" not in text

    @pytest.mark.asyncio
    async def test_given_pdf_rendered_when_body_text_is_inspected_then_it_is_legible_on_white_page(self, tmp_path):
        """
        GIVEN a PDF is generated for a user-facing artifact
        WHEN the first page is rendered to a bitmap
        THEN body text is dark enough to be legible on the white page.
        """
        if not shutil.which("pdftoppm"):
            pytest.skip("pdftoppm is required for PDF render inspection")
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow is required for PDF render inspection")

        from core.tools import create_pdf

        result = await create_pdf(
            title="Ephe Render Contrast",
            content=(
                "# Executive Summary\n"
                "This body line must render as dark, readable text on a white page.\n"
                "## Findings\n"
                "- Contrast is a user-facing artifact quality requirement.\n"
            ),
            filename="ephe-render-contrast.pdf",
        )
        output = _pdf_path_from(result)
        render_prefix = tmp_path / "rendered"

        subprocess.run(
            ["pdftoppm", "-png", "-f", "1", "-l", "1", str(output), str(render_prefix)],
            check=True,
            capture_output=True,
            text=True,
        )
        image = Image.open(tmp_path / "rendered-1.png").convert("RGB")
        width, height = image.size
        crop = image.crop((int(width * 0.08), int(height * 0.16), int(width * 0.92), int(height * 0.42)))
        pixels = crop.tobytes()
        dark_pixels = sum(
            1
            for index in range(0, len(pixels), 3)
            if pixels[index] < 90 and pixels[index + 1] < 90 and pixels[index + 2] < 90
        )

        assert dark_pixels > 500

    @pytest.mark.asyncio
    async def test_given_pdf_template_brief_when_created_then_required_sections_are_inserted(self):
        """
        GIVEN the PDF tool supports high-end templates
        WHEN a brief is created with sparse content
        THEN the generated PDF includes the expected brief sections.
        """
        from core.tools import create_pdf
        import pdfplumber

        result = await create_pdf(
            title="Local AI Brief",
            content="Ephe should stay strictly local.",
            filename="local-ai-brief-template.pdf",
            template="brief",
        )
        output = _pdf_path_from(result)

        with pdfplumber.open(str(output)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        assert "Executive Summary" in text
        assert "Key Points" in text
        assert "Source Notes" in text
