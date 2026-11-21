"""Audit 2026-09-13 — fixes from the skill/tool deep audit.

Findings (docs/skill-tool-audit-2026-09-13.md):
1. xlsx: a silent data-corruption bug (English thousands '1,234' → 1.234).
2. xlsx: echo leak — prose with commas was parsed as a table; mixed
   prompts (inline table + file reference) bypassed the data gate.
3. Repo hygiene: hardcoded /work paths in help examples.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def test_given_english_thousands_when_parsed_then_value_is_exact():
    """Finding 1: '1,234' quietly became 1.234 — now it is read as thousands."""
    from core.tools.office_tools import _parse_numeric_cell

    assert _parse_numeric_cell("1,234") == 1234
    assert _parse_numeric_cell("1,234,567") == 1234567
    assert _parse_numeric_cell("1.234,56") == 1234.56
    assert _parse_numeric_cell("12,5") == 12.5
    assert _parse_numeric_cell("42") == 42
    assert _parse_numeric_cell("3.14") == 3.14
    assert _parse_numeric_cell("keine zahl") is None


# Finding 2 (echo leak/gating) concerned the fast-path parser _extract_table_rows
# and the data gate — both fell away with R36 (the fast path is gone, table
# consumption now runs over the agent path with a declared tool result).


def test_given_core_sources_when_scanned_then_no_hardcoded_user_paths():
    """Finding 3 (repo hygiene): no /Users/<name> paths in the core source
    (AGENTS.md: never hardcode a hostname or path)."""
    core_dir = Path(__file__).resolve().parents[1] / "core"
    offenders: list[str] = []
    for py in core_dir.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        if "/Users/" in text:
            offenders.append(str(py.relative_to(core_dir.parent)))
    assert offenders == [], f"hardcoded user paths in: {offenders}"
