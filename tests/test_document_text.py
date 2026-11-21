"""One extractor for every document format the library takes in.

PDF text was read by three modules and Office XML by two, each with its own failure
sentence, so the same scanned PDF could answer "no extractable text" on one path and raise
on another. `core/document_text.py` is the union of what those paths already did, and the
equivalence rows below pin it against `core/source_notebook.py` file by file: a format the
notebook reads today has to come back with the same three fields from the same call.

Every fixture is generated inside the test, so a real producer (reportlab, python-docx,
openpyxl) wrote the bytes the extractor reads.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


def _write_pdf(path: Path, lines: list[str]) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    doc = canvas.Canvas(str(path), pagesize=letter)
    for row, line in enumerate(lines):
        doc.drawString(72, 700 - 24 * row, line)
        doc.showPage()
    doc.save()
    return path


def _write_scanned_pdf(path: Path) -> Path:
    """A page of drawing commands only: a PDF that carries no text layer."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    doc = canvas.Canvas(str(path), pagesize=letter)
    doc.setFillColorRGB(0.2, 0.4, 0.8)
    doc.rect(72, 400, 200, 120, fill=1)
    doc.showPage()
    doc.save()
    return path


def _write_docx(path: Path, paragraphs: list[str]) -> Path:
    from docx import Document

    doc = Document()
    for line in paragraphs:
        doc.add_paragraph(line)
    doc.save(str(path))
    return path


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _write_pptx(path: Path, slides: list[list[str]]) -> Path:
    """A hand-built OOXML package: python-pptx is not a runtime dependency here.

    The extractor reads `<a:t>` runs out of `ppt/slides/slideN.xml`, so the fixture is
    exactly that shape and nothing more.
    """
    template = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        ' xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>'
    )
    with zipfile.ZipFile(path, "w") as deck:
        deck.writestr("[Content_Types].xml", "<Types/>")
        for index, lines in enumerate(slides, 1):
            shapes = "".join(
                f'<p:sp><p:txBody><a:p><a:r><a:t>{_xml_escape(line)}</a:t></a:r></a:p>'
                f"</p:txBody></p:sp>"
                for line in lines
            )
            deck.writestr(f"ppt/slides/slide{index}.xml", template.format(shapes=shapes))
    return path


def _write_xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    from openpyxl import Workbook

    book = Workbook()
    first = book.active
    for name, rows in sheets.items():
        sheet = first if name == first.title else book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    book.save(str(path))
    return path


def test_pdf_pages_are_named(tmp_path):
    """
    GIVEN a two-page PDF with one line on each page
    WHEN the extractor reads it
    THEN both pages come back, each under its own page marker, with the pdfplumber parser
    """
    from core.document_text import extract_text

    path = _write_pdf(tmp_path / "terms.pdf", ["First clause.", "Second clause."])
    text, warning, parser = extract_text(path)
    assert parser == "pdfplumber"
    assert warning == ""
    assert "--- Page 1/2 ---" in text and "--- Page 2/2 ---" in text
    assert "First clause." in text and "Second clause." in text


def test_a_pdf_without_a_text_layer_says_so(tmp_path):
    """
    GIVEN a PDF that carries a drawing and no text layer
    WHEN the extractor reads it
    THEN it returns no text with the sentence the notebook already used
    """
    from core.document_text import PDF_NO_TEXT, extract_text

    text, warning, parser = extract_text(_write_scanned_pdf(tmp_path / "scan.pdf"))
    assert text == ""
    assert warning == PDF_NO_TEXT
    assert parser == "pdfplumber"


def test_a_pdf_that_is_not_a_pdf_is_a_warning(tmp_path):
    """
    GIVEN bytes that only pretend to be a PDF
    WHEN the extractor reads them
    THEN the failure is a sentence and an empty text, never an exception
    """
    from core.document_text import extract_text

    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4 this is not a PDF")
    text, warning, parser = extract_text(path)
    assert text == ""
    assert warning.startswith("PDF extraction failed:")
    assert parser == "pdfplumber"


def test_docx_paragraphs_come_back_in_order(tmp_path):
    """
    GIVEN a Word document with three paragraphs
    WHEN the extractor reads it
    THEN the paragraphs arrive in order under the office-xml parser
    """
    from core.document_text import extract_text

    path = _write_docx(tmp_path / "memo.docx", ["Kickoff", "Budget is capped.", "Next: sign."])
    text, warning, parser = extract_text(path)
    assert parser == "office-xml"
    assert warning == ""
    assert text.index("Kickoff") < text.index("Budget is capped.") < text.index("Next: sign.")


def test_pptx_slides_are_named(tmp_path):
    """
    GIVEN a deck with two slides
    WHEN the extractor reads it
    THEN each slide's runs arrive under its own slide marker
    """
    from core.document_text import extract_text

    path = _write_pptx(
        tmp_path / "pitch.pptx",
        [["Market size", "40 billion"], ["Roadmap", "Two quarters"]],
    )
    text, warning, parser = extract_text(path)
    assert parser == "office-xml"
    assert warning == ""
    assert "--- Slide 1 ---" in text and "--- Slide 2 ---" in text
    assert "40 billion" in text and "Two quarters" in text


def test_xlsx_rows_read_as_text(tmp_path):
    """
    GIVEN a workbook with two sheets
    WHEN the extractor reads it
    THEN every sheet is named and its rows arrive as cell text
    """
    from core.document_text import extract_text

    path = _write_xlsx(
        tmp_path / "costs.xlsx",
        {"Sheet": [["Item", "Cost"], ["Server", 1200]], "Archive": [["Old", 7]]},
    )
    text, warning, parser = extract_text(path)
    assert parser == "openpyxl"
    assert warning == ""
    assert "Item" in text and "1200" in text and "Archive" in text


def test_plain_text_is_read_as_it_stands(tmp_path):
    """
    GIVEN a Markdown file
    WHEN the extractor reads it
    THEN the bytes arrive unchanged under the plain parser
    """
    from core.document_text import extract_text

    path = tmp_path / "notes.md"
    path.write_text("# Notes\n\nA sentence worth keeping.\n", encoding="utf-8")
    text, warning, parser = extract_text(path)
    assert parser == "plain"
    assert warning == ""
    assert "A sentence worth keeping." in text


def test_a_file_over_the_budget_is_cut_and_says_so(tmp_path):
    """
    GIVEN a text file longer than the character budget
    WHEN the extractor reads it with a small budget
    THEN the text stops at the budget and the warning names the cut
    """
    from core.document_text import TRUNCATED, extract_text

    path = tmp_path / "long.txt"
    path.write_text("a" * 500, encoding="utf-8")
    text, warning, parser = extract_text(path, max_chars=120)
    assert len(text) == 120
    assert warning == TRUNCATED
    assert parser == "plain"


def test_an_unsupported_kind_is_refused_before_reading(tmp_path):
    """
    GIVEN a file whose extension the library does not take
    WHEN the surface asks whether it is readable
    THEN the answer is no, and reading it says which type arrived
    """
    from core.document_text import extract_text, is_extractable

    path = tmp_path / "movie.mkv"
    path.write_bytes(b"\x1aE\xdf\xa3not a document")
    assert is_extractable(path) is False
    text, warning, parser = extract_text(path)
    assert text == ""
    assert "Unsupported file type" in warning
    assert parser == "none"


def test_a_file_that_is_not_there_is_a_warning(tmp_path):
    """
    GIVEN a path with no file behind it
    WHEN the extractor reads it
    THEN the failure is the sentence the notebook already answered with
    """
    from core.document_text import extract_text

    text, warning, parser = extract_text(tmp_path / "gone.txt")
    assert text == ""
    assert warning.startswith("Text extraction failed:")
    assert parser == "plain"


#: The formats the notebook already parsed. A workbook is the format this union
#: adds: the notebook read its bytes as plain text, so there is no old behaviour of
#: that one to be equal to (the sheet rows are pinned by their own test above).
FORMATS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".md": "plain",
}


def _fixture(tmp_path: Path, kind: str) -> Path:
    if kind == "pdf":
        return _write_pdf(tmp_path / "source.pdf", ["A clause.", "Another clause."])
    if kind == "docx":
        return _write_docx(tmp_path / "source.docx", ["A clause.", "Another clause."])
    if kind == "pptx":
        return _write_pptx(tmp_path / "source.pptx", [["A clause.", "Another clause."]])
    if kind == "xlsx":
        return _write_xlsx(tmp_path / "source.xlsx", {"Sheet": [["A clause.", "Another clause."]]})
    path = tmp_path / "source.md"
    path.write_text("A clause.\n\nAnother clause.\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("extension,kind", sorted(FORMATS.items()))
def test_the_notebook_and_the_extractor_agree(tmp_path, extension, kind):
    """
    GIVEN one real file per format the notebook reads today
    WHEN both the notebook's own reader and the shared extractor read it
    THEN they return the same text, warning and parser
    """
    from core.document_text import extract_text
    from core.source_notebook import _read_source_text

    path = _fixture(tmp_path, kind)
    assert path.suffix == extension
    assert extract_text(path) == _read_source_text(path), path.name
