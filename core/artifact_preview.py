"""Ephe – artifact_preview: preview for the kinds a browser does not know (R4/A5).

A browser renders PDF, image, text and audio itself. It renders **no**
table from a .xlsx and no Word document — for exactly these two kinds
this path exists: the bytes are read here and delivered as data the
surface can show as a table or as running text. Everything else goes
through `GET /artifacts/{id}/file` directly.

The limits are deliberately hard (rows, columns, characters): the preview is a
glance, not an export, and it must not hold up the request.
"""
from __future__ import annotations

from pathlib import Path

MAX_ROWS = 60
MAX_COLS = 24
MAX_TEXT_CHARS = 20_000

# Enough to tell them apart — and keeps the surface honest.
TABLE_KINDS = {"xlsx", "xls", "csv"}
TEXT_KINDS = {"docx", "md", "markdown", "txt", "log", "json", "yaml", "yml", "toml", "ini", "conf"}


def _table(path: Path) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    sheet = wb[wb.sheetnames[0]] if wb.sheetnames else None
    rows: list[list[str]] = []
    if sheet is not None:
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= MAX_ROWS:
                break
            cells = ["" if c is None else str(c) for c in row[:MAX_COLS]]
            rows.append(cells)
    sheets = list(wb.sheetnames)
    wb.close()
    header = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []
    return {
        "mode": "table",
        "sheets": sheets,
        "header": header,
        "rows": body,
        "truncated": len(rows) >= MAX_ROWS,
    }


def _docx_text(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    out: list[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading"):
            depth = 1 + (int(style.split()[-1]) - 1 if style.split()[-1].isdigit() else 0)
            out.append(f"{'#' * min(depth, 6)} {text}")
        elif "list" in style:
            out.append(f"- {text}")
        else:
            out.append(text)
    for table in doc.tables[:4]:
        out.append("")
        for row in table.rows[:MAX_ROWS]:
            out.append("| " + " | ".join(c.text.strip() for c in row.cells[:MAX_COLS]) + " |")
    return "\n\n".join(out)[:MAX_TEXT_CHARS]


def _plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_CHARS]


def preview_payload(path: str | Path, kind: str = "") -> dict:
    """{mode: table|text|none, …} — `none` is a statement, not an error.

    `none` means: this surface cannot show that as content (image, PDF,
    audio, deck). The card then shows exactly that, not an empty preview.
    """
    p = Path(path)
    if not p.is_file():
        return {"mode": "none", "reason": "missing"}
    ext = (kind or p.suffix.lstrip(".") or "").lower()
    try:
        if ext in ("xlsx", "xls"):
            return _table(p)
        if ext == "csv":
            rows = [line.split(",") for line in _plain_text(p).splitlines()[:MAX_ROWS]]
            return {"mode": "table", "sheets": [], "header": rows[0] if rows else [],
                    "rows": rows[1:], "truncated": len(rows) >= MAX_ROWS}
        if ext == "docx":
            return {"mode": "text", "format": "markdown", "text": _docx_text(p)}
        if ext in TEXT_KINDS:
            return {"mode": "text", "format": "markdown" if ext in ("md", "markdown", "docx") else "text",
                    "text": _plain_text(p)}
    except Exception as exc:  # noqa: BLE001 — a broken preview must still return 200
        return {"mode": "none", "reason": f"unreadable: {type(exc).__name__}"}
    return {"mode": "none", "reason": "no-text-preview"}
