"""Tests for Wave 2 (P1): P1-2 Typed Repair Automata.
"""
from __future__ import annotations

import asyncio
import pytest


def test_p1_2_classify_missing_param():
    from core.tools.registry import _classify_tool_error
    err = "[TOOL-ERROR] generate_chart: fehlende Pflicht-Parameter: chart_type, title, labels, values"
    assert _classify_tool_error(err) == "missing-param"


def test_p1_2_classify_enum_mismatch():
    from core.tools.registry import _classify_tool_error
    err = "[TOOL-ERROR] create_pitch_deck: Parameter 'design_theme'='blue' nicht in ['evergreen', 'executive', 'studio']"
    assert _classify_tool_error(err) == "enum-mismatch"


def test_p1_2_classify_unknown_param():
    from core.tools.registry import _classify_tool_error
    err = "[TOOL-ERROR] read_file: unbekannte Parameter: extra_field"
    assert _classify_tool_error(err) == "unknown-param"


def test_p1_2_classify_returns_none_for_unclassified():
    from core.tools.registry import _classify_tool_error
    assert _classify_tool_error("[TOOL-ERROR] x: some other error") is None


def test_p1_2_missing_param_repair_fills_defaults():
    from core.tools.registry import _typed_repair
    err = "[TOOL-ERROR] generate_chart: fehlende Pflicht-Parameter: chart_type, title, labels, values"
    repaired = _typed_repair("generate_chart", {}, err)
    assert repaired is not None
    for key in ("chart_type", "title", "labels", "values"):
        assert key in repaired


def test_p1_2_enum_mismatch_repair_uses_first_enum_value():
    from core.tools.registry import _typed_repair
    err = "[TOOL-ERROR] create_pitch_deck: Parameter 'design_theme'='blue' nicht in ['evergreen', 'executive', 'studio']"
    repaired = _typed_repair("create_pitch_deck", {"design_theme": "blue", "topic": "Test"}, err)
    assert repaired is not None
    assert repaired["design_theme"] == "evergreen"


def test_p1_2_unknown_param_repair_removes_it():
    from core.tools.registry import _typed_repair
    err = "[TOOL-ERROR] read_file: unbekannte Parameter: extra_field"
    repaired = _typed_repair("read_file", {"path": "/tmp/a", "extra_field": "x"}, err)
    assert repaired is not None
    assert "extra_field" not in repaired
    assert repaired["path"] == "/tmp/a"


def test_p1_2_no_repair_for_unclassifiable_error():
    from core.tools.registry import _typed_repair
    assert _typed_repair("read_file", {}, "[TOOL-ERROR] x: some other error") is None


def test_p1_2_execute_tool_topic_only_repairs_missing_required():
    """create_pitch_deck needs only topic. With just topic it should work."""
    from core.tools.registry import execute_tool
    result = asyncio.run(execute_tool("create_pitch_deck", {"topic": "Test"}))
    assert not result.startswith("[TOOL-ERROR]")


def test_p1_2_execute_tool_repair_enum_mismatch():
    """Wrong design_theme should be repaired to first valid value."""
    from core.tools.registry import execute_tool
    result = asyncio.run(execute_tool("create_pitch_deck", {
        "topic": "Test",
        "design_theme": "blue",
    }))
    # Should not be a TOOL-ERROR (repair injected "evergreen")
    assert not result.startswith("[TOOL-ERROR]")
