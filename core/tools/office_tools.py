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
) -> str:
    """Creates a real Excel file (openpyxl): formatted header,
    column widths, number cells where parseable.

    R38: `path` = output path named by the user in the prompt (directory or
    file); it overrides the downloads default only if it exists."""
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
        thin = Side(style="thin", color="D9D9D9")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for r_idx, row in enumerate(rows, start=1):
            for c_idx, cell_value in enumerate(row, start=1):
                text = str(cell_value).strip()
                numeric = _parse_numeric_cell(text)
                cell = ws.cell(row=r_idx, column=c_idx, value=numeric if numeric is not None else text)
                cell.border = border
                if r_idx == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(vertical="center")
                else:
                    cell.alignment = Alignment(vertical="top", wrap_text=False)

        # column widths from the largest cell content
        for c_idx in range(1, len(rows[0]) + 1):
            width = max(len(str(rows[r][c_idx - 1])) for r in range(len(rows))) + 3
            ws.column_dimensions[get_column_letter(c_idx)].width = min(max(width, 10), 60)
        ws.freeze_panes = "A2"

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
