"""One text extractor for the document formats the product reads.

PDF text was produced by three modules and Office XML by two, each with its own failure
sentence, so one scanned PDF could answer "no extractable text" on the notebook path and
raise on another. This module is the union of what those paths already did, page for page,
and `core/source_notebook.py` reads through it. A workbook is what the union adds: the
notebook had no sheet reader and took its bytes as plain text.

Text arrives as data for an index. Nothing here judges what a document says.
"""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

#: The budget every index path in this area already carries (`MAX_SOURCE_CHARS`,
#: `source_notebook.py:16`). A document longer than this is cut and says so.
MAX_DOC_CHARS = 180_000
#: A sheet is read row by row; the cap bounds one workbook with many sheets.
MAX_SHEET_ROWS = 5_000
MAX_SHEET_COLS = 64

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".toml", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".java", ".go", ".rs", ".swift", ".kt", ".php", ".rb", ".sh", ".sql",
}
PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {".docx", ".pptx"}
SHEET_EXTENSIONS = {".xlsx", ".xlsm"}
EXTRACT_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | OFFICE_EXTENSIONS | SHEET_EXTENSIONS

PDF_NO_TEXT = "PDF has no extractable text."
OFFICE_NO_TEXT = "Office file has no extractable text."
SHEET_NO_TEXT = "Spreadsheet has no readable cells."
TRUNCATED = "Source truncated by per-file character limit."


def is_extractable(path: str | Path) -> bool:
    """Whether this file's kind has a reader here — the allow-list the surfaces share."""
    return Path(path).suffix.lower() in EXTRACT_EXTENSIONS


def extract_text(path: str | Path, *, max_chars: int = MAX_DOC_CHARS) -> tuple[str, str, str]:
    """Read (text, warning, parser) from one file.

    Never raises: a format with no text layer, a broken package and a path with nothing
    behind it all answer with an empty text and the sentence that names them. The parser
    is the reader that ran, so the surface can say which one came up empty.
    """
    file_path = Path(path)
    extension = file_path.suffix.lower()
    if extension in PDF_EXTENSIONS:
        return _cap(_read_pdf(file_path), max_chars)
    if extension in OFFICE_EXTENSIONS:
        return _cap(_read_office(file_path), max_chars)
    if extension in SHEET_EXTENSIONS:
        return _cap(_read_sheet(file_path), max_chars)
    if extension in TEXT_EXTENSIONS:
        return _cap(_read_plain(file_path), max_chars)
    return "", f"Unsupported file type: {extension or 'no extension'}", "none"


def _cap(result: tuple[str, str, str], max_chars: int) -> tuple[str, str, str]:
    text, warning, parser = result
    if len(text) <= max_chars:
        return result
    cut = text[:max_chars]
    return cut, f"{warning} {TRUNCATED}".strip(), parser


def _read_plain(path: Path) -> tuple[str, str, str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace"), "", "plain"
    except Exception as exc:  # noqa: BLE001 — a file that will not read is an answer
        return "", f"Text extraction failed: {exc}", "plain"


def _read_pdf(path: Path) -> tuple[str, str, str]:
    try:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            for index, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"--- Page {index}/{total} ---\n{text.strip()}")
        return "\n\n".join(pages), "" if pages else PDF_NO_TEXT, "pdfplumber"
    except Exception as exc:  # noqa: BLE001 — a damaged PDF is an answer
        return "", f"PDF extraction failed: {exc}", "pdfplumber"


def _read_office(path: Path) -> tuple[str, str, str]:
    """Text of a docx/pptx package, read as OOXML parts with the standard library."""
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if path.suffix.lower() == ".docx":
                xml_names = [name for name in names if name.startswith("word/") and name.endswith(".xml")]
            else:
                xml_names = [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
            parts: list[str] = []
            for index, name in enumerate(sorted(xml_names), 1):
                xml = package.read(name).decode("utf-8", errors="replace")
                matches = re.findall(r"<a:t>(.*?)</a:t>|<w:t[^>]*>(.*?)</w:t>", xml)
                flat = [
                    html.unescape(item).strip()
                    for pair in matches
                    for item in pair
                    if item and item.strip()
                ]
                if flat:
                    marker = f"--- Slide {index} ---" if path.suffix.lower() == ".pptx" else f"--- Part {index} ---"
                    parts.append(marker + "\n" + "\n".join(flat))
            return "\n\n".join(parts), "" if parts else OFFICE_NO_TEXT, "office-xml"
    except Exception as exc:  # noqa: BLE001 — a package that will not open is an answer
        return "", f"Office extraction failed: {exc}", "office-xml"


def _read_sheet(path: Path) -> tuple[str, str, str]:
    """Every sheet of a workbook as named rows, cells in reading order."""
    try:
        from openpyxl import load_workbook

        book = load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — a workbook that will not open is an answer
        return "", f"Spreadsheet extraction failed: {exc}", "openpyxl"
    try:
        parts: list[str] = []
        for sheet in book.worksheets:
            rows: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                if len(rows) >= MAX_SHEET_ROWS:
                    break
                cells = ["" if cell is None else str(cell) for cell in row[:MAX_SHEET_COLS]]
                if any(cells):
                    rows.append(" | ".join(cells).rstrip(" |"))
            if rows:
                parts.append(f"--- Sheet: {sheet.title} ---\n" + "\n".join(rows))
        return "\n\n".join(parts), "" if parts else SHEET_NO_TEXT, "openpyxl"
    except Exception as exc:  # noqa: BLE001 — a sheet that stops mid-read is an answer
        return "", f"Spreadsheet extraction failed: {exc}", "openpyxl"
    finally:
        book.close()
