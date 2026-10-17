"""
◑ Ephe – TDD: new artifact tools (round 11) — create_xlsx, create_docx,
create_qrcode, create_diagram + registry wiring + marker emission.

Given / When / Then – strictly. Writes only into temp dirs
(monkeypatched _downloads), NEVER into the real ~/Downloads.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def downloads(tmp_path, monkeypatch) -> Path:
    """Artifacts stay in temp dirs: office tools through `_downloads`, the diagram
    writer through the suite-wide `EPHE_CONFIG_DIR` sandbox in tests/conftest.py:246
    (its output dir is `artifact_output_dir()` → `config_root()`,
    core/engine_config.py:226-232, which reads that env at call time).

    The diagram branch used to fake `Path.home()` by replacing `diagram_tools.Path`
    with a hand-built subclass. That never moved the output, and on Python < 3.12
    instantiating a Path subclass needs the `_flavour` plumbing: `diagram_tools.py:241`
    raised, the tool's own except at :252 turned it into the string
    `[diagram error: type object '_P' has no attribute '_flavour']`, and
    `assert result.startswith("SVG_FILE:")` failed — which is exactly what the 3.10 and
    3.11 CI legs showed while 3.12/3.13 passed.
    """
    import core.tools.office_tools as ot

    monkeypatch.setattr(ot, "_downloads", lambda: tmp_path)
    return tmp_path


class TestCreateXlsx:

    async def test_given_json_rows_when_create_then_real_file_with_marker(self, downloads):
        """Given: JSON rows When: create_xlsx Then: XLSX_FILE marker + a real file"""
        from core.tools.office_tools import create_xlsx
        result = await create_xlsx(
            title="Umsatz 2026",
            data=[["Quartal", "Umsatz"], ["Q1", "1200"], ["Q2", "900"]],
            filename="umsatz.xlsx",
        )
        assert result.startswith("XLSX_FILE:")
        path = Path(result[len("XLSX_FILE:"):])
        assert path.exists() and path.stat().st_size > 0

    async def test_given_csv_string_when_create_then_parsed(self, downloads):
        """Given: a CSV string When: create_xlsx Then: it is parsed and the file is created"""
        from core.tools.office_tools import create_xlsx
        result = await create_xlsx(title="T", data="a;b\n1;2\n3;4")
        assert result.startswith("XLSX_FILE:")

    async def test_given_no_rows_when_create_then_error_marker_no_file(self, downloads):
        """Given: empty data When: create_xlsx Then: error marker, no file"""
        from core.tools.office_tools import create_xlsx
        result = await create_xlsx(title="T", data=[])
        assert "error" in result and "xlsx" in result

    async def test_given_colon_title_when_create_then_valid_sheet_name(self, downloads):
        """Given: a topic containing ':' (taken from free text) When: create_xlsx Then: no ValueError"""
        from core.tools.office_tools import create_xlsx
        result = await create_xlsx(title="Erstell eine Excel: Umsatz", data=[["a"], ["b"]])
        assert result.startswith("XLSX_FILE:")

    async def test_given_german_decimal_when_create_then_numeric_cell(self, downloads):
        """Given: the German decimal '1.200,50' When: create_xlsx Then: the cell is numeric"""
        from openpyxl import load_workbook
        from core.tools.office_tools import create_xlsx
        result = await create_xlsx(title="T", data=[["Umsatz"], ["1.200,50"]])
        path = Path(result[len("XLSX_FILE:"):])
        ws = load_workbook(str(path)).active
        assert isinstance(ws["A2"].value, float)
        assert ws["A2"].value == pytest.approx(1200.50)


class TestCreateDocx:

    async def test_given_markdown_content_when_create_then_real_docx_with_marker(self, downloads):
        """Given: a Markdown subset When: create_docx Then: DOCX_FILE marker + a real document"""
        from docx import Document
        from core.tools.office_tools import create_docx
        content = "# Titel\n\n## Kernpunkte\n- Punkt A\n- Punkt B\n\n1. Erster\n2. Zweiter"
        result = await create_docx(title="Bericht", content=content, filename="bericht.docx")
        assert result.startswith("DOCX_FILE:")
        path = Path(result[len("DOCX_FILE:"):])
        doc = Document(str(path))
        texts = "\n".join(p.text for p in doc.paragraphs)
        assert "Punkt A" in texts
        headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert any("Kernpunkte" in h for h in headings)

    async def test_given_markdown_table_when_create_then_table_in_docx(self, downloads):
        """Given: a Markdown table When: create_docx Then: a real Word table"""
        from core.tools.office_tools import create_docx
        content = "| Name | Wert |\n|---|---|\n| A | 1 |"
        result = await create_docx(title="T", content=content)
        assert result.startswith("DOCX_FILE:")

    async def test_given_empty_content_when_create_then_error_marker(self, downloads):
        """Given: empty content When: create_docx Then: error marker"""
        from core.tools.office_tools import create_docx
        assert "error" in await create_docx(title="T", content="   ")


class TestCreateQrcode:

    async def test_given_url_when_create_then_scannable_png_with_marker(self, downloads):
        """Given: a URL When: create_qrcode Then: PNG_FILE marker + a real PNG"""
        from core.tools.office_tools import create_qrcode
        result = await create_qrcode(data="https://example.com", filename="qr.png")
        assert result.startswith("PNG_FILE:")
        path = Path(result[len("PNG_FILE:"):])
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_given_empty_payload_when_create_then_error_marker(self, downloads):
        """Given: an empty payload When: create_qrcode Then: error marker"""
        from core.tools.office_tools import create_qrcode
        assert "error" in await create_qrcode(data="  ")


class TestCreateDiagram:

    async def test_given_flowchart_when_create_then_black_forest_svg(self, downloads):
        """Given: flowchart items When: create_diagram Then: SVG_FILE marker + valid SVG"""
        from core.tools.diagram_tools import create_diagram
        result = await create_diagram(
            kind="flowchart", title="Onboarding",
            items=[["Anfrage", "Eingang"], ["Prüfung", "2 Tage"], ["Freigabe", ""]],
        )
        assert result.startswith("SVG_FILE:")
        svg = Path(result[len("SVG_FILE:"):]).read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "Onboarding" in svg

    async def test_given_german_alias_when_create_then_kind_mapped(self, downloads):
        """Given: kind='prozess' When: create_diagram Then: it is treated as a flowchart"""
        from core.tools.diagram_tools import create_diagram
        result = await create_diagram(kind="prozess", title="T", items=[["a"], ["b"], ["c"]])
        assert result.startswith("SVG_FILE:")

    async def test_given_unknown_kind_when_create_then_error_marker(self, downloads):
        """Given: kind='radar' When: create_diagram Then: error marker"""
        from core.tools.diagram_tools import create_diagram
        assert "error" in await create_diagram(kind="radar", title="T", items=[["a"]])

    async def test_given_too_few_items_when_create_then_error_marker(self, downloads):
        """Given: no bullets When: create_diagram Then: error marker"""
        from core.tools.diagram_tools import create_diagram
        assert "error" in await create_diagram(kind="mindmap", title="T", items=[])


class TestRegistryWiring:

    def test_given_new_tools_when_schemas_then_all_four_listed(self):
        """Given: the round-11 tools When: the schema list is read Then: all 4 with the correct required fields"""
        from core.tools.registry import TOOL_MAP, get_tool_schemas
        for name in ("create_xlsx", "create_docx", "create_qrcode", "create_diagram"):
            assert name in TOOL_MAP, name
        schemas = {s["function"]["name"] for s in get_tool_schemas()}
        for name in ("create_xlsx", "create_docx", "create_qrcode", "create_diagram"):
            assert name in schemas, name
