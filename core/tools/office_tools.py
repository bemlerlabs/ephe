"""Ephe – office_tools: create_xlsx, create_docx, create_qrcode.

Real, deterministic office artifacts (round 11 skill expansion). All three
put their file where the output pipe points and return a
FILE marker that the chat stream translates into file_result events.

No room for simulation: afterwards the files exist for real on disk.
Blocking IO runs in threads (asyncio.to_thread) — the event loop
stays responsive during SSE streaming.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path

_PERCENT_RE = re.compile(r"^([-+]?\d+(?:[.,]\d+)?)\s*%$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_RE = re.compile(
    r"^(?:(€|\$|CHF|£)\s*)?([-+]?\d[\d\s.,\u00a0]*)(?:\s*(€|\$|CHF|£))?$",
    re.IGNORECASE,
)
_CURRENCY_FORMATS = {
    "€": '#,##0.00 "€"',
    "$": '"$"#,##0.00',
    "CHF": '#,##0.00 "CHF"',
    "£": '"£"#,##0.00',
}
_FORMULA_FUNC_RE = re.compile(r"^=[A-Za-z_][A-Za-z0-9_.]*\([^;\n]*\)$")
_FORMULA_ARITH_RE = re.compile(r"^=[A-Za-z0-9_.$+\-*/:<>=(),&% ]+$")
_FORMULA_DENY_RE = re.compile(
    r"^=(?:HYPERLINK|CMD|WEBSERVICE|IMPORTXML|IMPORTDATA|IMPORTRANGE|RTD|DDE)\s*\(",
    re.IGNORECASE,
)
_INJECTION_PREFIXES = ("=", "+", "-", "@")


def _parse_numeric_cell(text: str) -> float | int | None:
    """Audit 2026-09-13: recognize cell numbers UNAMBIGUOUSLY.

    The old one-liner silently normalized English thousands ("1,234" → 1.234)
    into wrong values. Order: unambiguous patterns first (English
    thousands groups, German thousands+decimal, German short decimal), then plain
    numbers. Ambiguous ("1,234" alone) counts as thousands — in tables
    groups of 3 are more common than 3 decimal places."""
    t = (text or "").strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", t):
        return int(t.replace(",", ""))
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", t):
        return float(t.replace(".", "").replace(",", "."))
    if re.fullmatch(r"-?\d+,\d{1,2}", t):
        return float(t.replace(",", "."))
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return float(t) if "." in t else int(t)
    return None


def _parse_localized_number(text: str) -> float | int | None:
    """Currency amounts carry both separator conventions; the later one is decimal."""
    t = (text or "").strip().replace(" ", "").replace("\u00a0", "")
    if not t:
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    elif "." in t and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        number = float(t)
    except ValueError:
        return None
    return int(number) if re.fullmatch(r"-?\d+", t) else number


def _parse_percent_cell(text: str) -> float | None:
    match = _PERCENT_RE.fullmatch((text or "").strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ".")) / 100.0
    except ValueError:
        return None


def _parse_currency_cell(text: str) -> tuple[float | int, str] | None:
    match = _CURRENCY_RE.fullmatch((text or "").strip())
    if not match:
        return None
    symbol = (match.group(1) or match.group(3) or "").upper()
    if not symbol or symbol not in _CURRENCY_FORMATS:
        return None
    number = _parse_localized_number(match.group(2))
    if number is None:
        return None
    return number, _CURRENCY_FORMATS[symbol]


def _parse_iso_date(text: str):
    raw = (text or "").strip()
    if not _ISO_DATE_RE.fullmatch(raw):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_safe_formula(text: str) -> bool:
    """A real spreadsheet formula, not a CSV-injection payload."""
    if not text.startswith("=") or len(text) > 512:
        return False
    if _FORMULA_DENY_RE.match(text):
        return False
    return bool(_FORMULA_FUNC_RE.fullmatch(text) or _FORMULA_ARITH_RE.fullmatch(text))


def _neutralize_text(text: str) -> str:
    return "'" + text if text[:1] in _INJECTION_PREFIXES else text


_FORMAT_TYPES = {
    "currency": "#,##0.00",
    "percent": "0.0%",
    "integer": "#,##0",
    "decimal": "#,##0.00",
    "date": "yyyy-mm-dd",
}


def _resolve_column_formats(formats: object, header: list[str], column_count: int) -> dict[int, object]:
    """formats maps a header name or 1-based column index (dict) or position (list) to a spec."""
    resolved: dict[int, object] = {}
    if isinstance(formats, dict):
        header_index = {str(name).strip().lower(): index for index, name in enumerate(header, 1)}
        for key, spec in formats.items():
            if not spec:
                continue
            index = key if isinstance(key, int) else header_index.get(str(key).strip().lower())
            if isinstance(index, int) and 1 <= index <= column_count:
                resolved[index] = spec
    elif isinstance(formats, (list, tuple)):
        for index, spec in enumerate(formats, 1):
            if spec and index <= column_count:
                resolved[index] = spec
    return resolved


def _cell_payload(raw: str, row_index: int, column_format: object) -> tuple[object, str | None, str | None]:
    """(value, number_format, horizontal_alignment) for one cell.

    Row 1 stays a header. From row 2 a safe formula is written as a formula;
    percentages, currencies and ISO dates become typed values with their own
    number format; unsupported leading characters stay inert text.
    """
    text = (raw or "").strip()
    if row_index >= 2 and _is_safe_formula(text):
        return text, None, None

    explicit = None
    align = None
    value: object = None
    number_format: str | None = None

    if row_index >= 2:
        percent = _parse_percent_cell(text)
        currency = _parse_currency_cell(text)
        iso_date = _parse_iso_date(text)
        numeric = _parse_numeric_cell(text)
        if percent is not None:
            value, number_format, align = percent, "0.0%", "right"
        elif currency is not None:
            value, number_format, align = currency[0], currency[1], "right"
        elif iso_date is not None:
            value, number_format, align = iso_date, "yyyy-mm-dd", "center"
        elif numeric is not None:
            value, align = numeric, "right"
            number_format = "#,##0" if isinstance(numeric, int) and abs(numeric) >= 1000 else (
                "#,##0.00" if isinstance(numeric, float) else None
            )

    if isinstance(column_format, str):
        explicit = _FORMAT_TYPES.get(column_format.strip().lower(), column_format.strip() or None)
    if explicit and value is not None:
        number_format = explicit
        if explicit == "yyyy-mm-dd":
            align = "center"
        elif align is None:
            align = "right"

    if value is None:
        value = _neutralize_text(text)
    return value, number_format, align


def _is_total_row(row: list[str]) -> bool:
    first = (row[0] if row else "").strip().lower()
    if first.startswith(("total", "gesamt", "summe", "durchschnitt", "average")):
        return True
    return any(
        isinstance(cell, str) and re.match(r"^=(?:SUM|AVERAGE)\s*\(", cell.strip(), re.IGNORECASE)
        for cell in row
    )


def _downloads() -> Path:
    # R44 (P4) / R4-A1: the name comes from an earlier world. The helper is still
    # called _downloads (tests monkeypatch it), since A1 it returns the workbench.
    from core.engine_config import artifact_output_dir

    return artifact_output_dir()


def _safe_filename(filename: str, default: str, ext: str) -> str:
    safe_name = Path(filename or default).name
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "", safe_name)
    safe_name = re.sub(r"_+", "_", safe_name).strip("._-")
    if not safe_name:
        safe_name = default
    if not safe_name.lower().endswith(ext):
        safe_name += ext
    return safe_name


def _parse_rows(data: object) -> list[list[str]]:
    """Accepts list[list], a JSON-array string or a CSV string → a row matrix."""
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _parse_rows(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        rows = list(csv.reader(io.StringIO(text)))
        return [[str(cell) for cell in row] for row in rows if any(str(c).strip() for c in row)]
    if isinstance(data, list):
        rows: list[list[str]] = []
        for row in data:
            if isinstance(row, (list, tuple)):
                rows.append([str(cell) for cell in row])
            elif isinstance(row, dict):
                # dict list: the keys of the first row become the header
                rows.append([str(v) for v in row.values()])
            else:
                rows.append([str(row)])
        return rows
    return []


async def create_xlsx(
    title: str,
    data: object,
    filename: str = "ephe_tabelle.xlsx",
    path: str | None = None,
    formats: dict | list | None = None,
) -> str:
    """Creates a real Excel file (openpyxl): formatted header, column widths,
    typed cells, safe formulas, auto filter and a styled total row.

    `formats` maps a header name or 1-based column index (dict) or a column
    position (list) to a format code or one of currency, percent, integer,
    decimal, date. R38: `path` = output path named by the user in the prompt
    (directory or file); it overrides the downloads default only if it exists."""
    rows = _parse_rows(data)
    if not rows:
        return "[xlsx error: no tabular data detected — pass rows as JSON array or CSV]"

    def _build() -> str:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        safe_name = _safe_filename(filename, "ephe_tabelle.xlsx", ".xlsx")
        if path:
            base = Path(str(path)).expanduser()
            base_dir = base.parent if base.is_file() else base
            base_dir.mkdir(parents=True, exist_ok=True)
            out = base_dir / safe_name
        else:
            out = _downloads() / safe_name
        wb = Workbook()
        ws = wb.active
        # Excel sheet names forbid : \ / ? * [ ] — topic comes from free text
        safe_title = re.sub(r"[:\\/?*\[\]]", "", title or "Daten").strip()[:31]
        ws.title = safe_title or "Daten"

        header_fill = PatternFill("solid", fgColor="1F3D2B")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        zebra_fill = PatternFill("solid", fgColor="F5F8F6")
        thin = Side(style="thin", color="D9D9D9")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        total_side = Side(style="thin", color="1F3D2B")
        total_border = Border(
            left=thin,
            right=thin,
            top=total_side,
            bottom=Side(style="double", color="1F3D2B"),
        )

        column_count = max(len(row) for row in rows)
        column_formats = _resolve_column_formats(formats, rows[0], column_count)
        total_row_index = len(rows) if len(rows) > 1 and _is_total_row(rows[-1]) else 0

        for r_idx, row in enumerate(rows, start=1):
            for c_idx, cell_value in enumerate(row, start=1):
                value, number_format, horizontal = _cell_payload(
                    str(cell_value), r_idx, column_formats.get(c_idx)
                )
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                cell.border = border
                if number_format:
                    cell.number_format = number_format
                if r_idx == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(vertical="center")
                else:
                    if horizontal:
                        cell.alignment = Alignment(horizontal=horizontal, vertical="top")
                    else:
                        cell.alignment = Alignment(vertical="top", wrap_text=False)
                    if r_idx % 2 == 0:
                        cell.fill = zebra_fill
                if r_idx == total_row_index:
                    cell.font = Font(bold=True)
                    cell.border = total_border
                    if horizontal:
                        cell.alignment = Alignment(horizontal=horizontal, vertical="top")

        # Display widths: a formula must not stretch the column to its source text.
        for c_idx in range(1, column_count + 1):
            longest = 0
            for row in rows:
                text = str(row[c_idx - 1]).strip() if c_idx - 1 < len(row) else ""
                if text.startswith("="):
                    display_length = 12
                elif _ISO_DATE_RE.fullmatch(text):
                    display_length = 10
                else:
                    display_length = len(text)
                longest = max(longest, display_length)
            width = min(max(longest + 4, 12), 55)
            ws.column_dimensions[get_column_letter(c_idx)].width = width
        ws.freeze_panes = "A2"
        if len(rows) > 1:
            ws.auto_filter.ref = ws.dimensions

        wb.save(str(out))
        return f"XLSX_FILE:{out}"

    try:
        return await asyncio.to_thread(_build)
    except Exception as exc:
        return f"[xlsx-Fehler: {exc}]"


def _markdown_to_docx(content: str, doc, heading_levels: dict[str, int]) -> None:
    """Minimal markdown-subset renderer: # headings, - bullets,
    1. numbering, tables (| a | b |) and paragraphs."""
    from docx.shared import Pt

    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").replace("-", "").strip()) <= {""}:
            # Markdown table
            header = [c.strip() for c in line.strip("|").split("|")]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            table = doc.add_table(rows=1 + len(rows), cols=len(header))
            table.style = "Light Grid Accent 1"
            for c, text in enumerate(header):
                table.rows[0].cells[c].text = text
            for r, row in enumerate(rows, start=1):
                for c, text in enumerate(row):
                    if c < len(table.rows[r].cells):
                        table.rows[r].cells[c].text = text
            i = j
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            doc.add_heading(m.group(2).strip(), level=heading_levels[m.group(1)])
            i += 1
            continue
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            doc.add_paragraph(m.group(1).strip(), style="List Bullet")
            i += 1
            continue
        m = re.match(r"^\d+\.\s+(.*)$", line)
        if m:
            doc.add_paragraph(m.group(1).strip(), style="List Number")
            i += 1
            continue
        p = doc.add_paragraph(line.strip())
        p.runs and setattr(p.runs[0].font, "size", Pt(11))
        i += 1


async def create_docx(
    title: str,
    content: str,
    filename: str = "ephe_dokument.docx",
) -> str:
    """Creates a real Word file (python-docx) from a markdown subset:
    # headings, bullets, numbered lists, tables, paragraphs."""
    if not (content or "").strip():
        return "[docx error: empty content — pass text with headings/paragraphs]"

    def _build() -> str:
        from docx import Document
        from docx.shared import RGBColor

        out = _downloads() / _safe_filename(filename, "ephe_dokument.docx", ".docx")
        doc = Document()
        core = doc.core_properties
        core.title = title or "Ephe Dokument"
        core.author = "Ephe"
        core.created = datetime.now()

        if title:
            h = doc.add_heading(title, level=0)
            for run in h.runs:
                run.font.color.rgb = RGBColor(0x1F, 0x3D, 0x2B)
        _markdown_to_docx(content, doc, {"#": 1, "##": 2, "###": 3, "####": 4})
        doc.save(str(out))
        return f"DOCX_FILE:{out}"

    try:
        return await asyncio.to_thread(_build)
    except Exception as exc:
        return f"[docx-Fehler: {exc}]"


async def create_qrcode(
    data: str,
    filename: str = "ephe_qrCode.png",
    fill_color: str = "#1F3D2B",
    back_color: str = "white",
) -> str:
    """Creates a real scannable QR code (qrcode lib, PNG)."""
    import qrcode

    payload = (data or "").strip()
    if not payload:
        return "[QR error: empty content — pass text/URL]"

    def _build() -> str:
        out = _downloads() / _safe_filename(filename, "ephe_qrCode.png", ".png")
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=3)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        img.save(str(out))
        return f"PNG_FILE:{out}"

    try:
        return await asyncio.to_thread(_build)
    except Exception as exc:
        return f"[QR-Fehler: {exc}]"
