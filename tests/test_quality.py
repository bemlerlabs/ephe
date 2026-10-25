"""The error axis and the blockade axis stay separate.

A fetch that failed (HTTP 404, timeout) is an error the user can retry; a target
the guard refused is a blockade the audit must keep calling blocked. The new
marker joins the first table only.
"""
from __future__ import annotations

from core.quality import ERROR_RESULT_PREFIXES, is_error_result, result_decision
from core.tool_markers import FETCH_FAILED_MARKER, FETCH_REFUSED_MARKER


def test_fetch_failure_is_an_error_not_a_blockade():
    raw = f"{FETCH_FAILED_MARKER} HTTP 404 for https://example.test/missing"

    assert FETCH_FAILED_MARKER in ERROR_RESULT_PREFIXES
    assert is_error_result(raw) is True
    assert result_decision(raw) == ""


def test_fetch_failure_with_a_status_line_is_still_only_an_error():
    raw = f"{FETCH_FAILED_MARKER} example.test: TimeoutException"

    assert is_error_result(raw) is True
    assert result_decision(raw) == ""


def test_guard_refusal_keeps_the_blocked_decision():
    raw = f"{FETCH_REFUSED_MARKER} 169.254.169.254 is the metadata endpoint"

    assert result_decision(raw) == "blocked"
    assert is_error_result(raw) is False
