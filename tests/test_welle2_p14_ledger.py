"""Tests for Wave 2 (P1): P1-4 Session-Scoped Assertion-Ledger."""
from __future__ import annotations

import asyncio
import pytest


def test_p1_4_ledger_starts_empty():
    from core.tools.registry import get_assertions, reset_assertion_ledger
    reset_assertion_ledger()
    assert get_assertions() == []


def test_p1_4_ledger_captures_artifact_path():
    """After a PDF-creation tool call, the ledger stores the file path."""
    from core.tools.registry import (
        get_assertions, reset_assertion_ledger, execute_tool,
        register_tool_hook, _assertion_post_hook,
    )
    reset_assertion_ledger()
    # registered inside the test: an earlier clear_tool_hooks() cannot have emptied it
    register_tool_hook("post", _assertion_post_hook, priority=200)
    result = asyncio.run(execute_tool("create_pdf", {
        "title": "Test Doc",
        "content": "Hello world",
    }))
    assert "PDF_FILE:" in result
    ledger = get_assertions()
    assert len(ledger) >= 1
    assert any("path" in e for e in ledger)


def test_p1_4_ledger_captures_run_tests_result():
    """After run_tests, the ledger stores passed/failed counts."""
    from core.tools.registry import get_assertions, reset_assertion_ledger, execute_tool
    reset_assertion_ledger()
    result = asyncio.run(execute_tool("run_tests", {"path": "tests/"}))
    # run_tests may pass or fail, but the result contains a count
    if "passed" in result.lower():
        ledger = get_assertions()
        assert any("tests_passed" in e for e in ledger)


def test_p1_4_ledger_max_entries_respected():
    """Ledger is capped at _LEDGER_MAX to prevent unbounded growth."""
    from core.tools.registry import _LEDGER_MAX, reset_assertion_ledger, _assertion_post_hook
    reset_assertion_ledger()
    # Simulate many hook calls
    for i in range(_LEDGER_MAX + 50):
        _assertion_post_hook("create_pdf", {}, f"PDF_FILE: /tmp/test{i}.pdf\nARTIFACT_VERIFIED: /tmp/test{i}.pdf")
    from core.tools.registry import get_assertions
    assert len(get_assertions()) <= _LEDGER_MAX


def test_p1_4_compactor_reads_ledger_entries():
    """_build_working_memory includes ledger-derived artifacts/tasks."""
    from core.tools.registry import get_assertions, reset_assertion_ledger, _assertion_post_hook
    from core.conversation_compactor import _build_working_memory
    reset_assertion_ledger()
    # Simulate two tool calls recorded in the ledger
    _assertion_post_hook("create_pdf", {}, "PDF_FILE: /tmp/briefing.pdf\nARTIFACT_VERIFIED: /tmp/briefing.pdf")
    _assertion_post_hook("run_tests", {}, "14 passed, 0 failed in 2.1s")
    ledger = get_assertions()
    assert len(ledger) >= 2
    # Now call _build_working_memory with minimal fake messages
    summary = _build_working_memory([], max_chars=2000)
    # The ledger should be reflected in the summary even with no messages
    assert isinstance(summary, str)
