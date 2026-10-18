"""Cell typing and number formats for create_xlsx.

A spreadsheet cell is a value plus the format that makes it readable. This module
decides both before openpyxl ever sees the row: unambiguous number parsing, percent
and currency detection, ISO dates, safe formulas, and the explicit formats a caller
can pin per column. The writing half lives in core.tools.office_tools.

CSV-injection safety is part of the typing decision, not a later pass: text that a
spreadsheet would evaluate keeps a leading apostrophe so it stays inert.
"""
from __future__ import annotations

import re
from datetime import datetime

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
    """Whether the text is a spreadsheet formula with an allowed function or arithmetic."""
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
