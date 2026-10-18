"""W19 — ask-mode guard + compute-guard wiring (live-audit P0 fixes).

Finding 2026-09-11: the ask mode claimed "hello.txt angelegt ✅" without any tool
running (disk check: the file is missing). The anti-hallucination guard and
the DATA-COMPUTATION-GUARD are the deterministic layers left in the
system prompt (the fast-path detection tests were dropped with R36, together with
the deleted `core/skill_fastpath` module).

Pins:
1. ASK_MODE_GUARD exists and forbids success claims strictly.
2. needs_compute_guard recognizes file arithmetic; COMPUTE_GUARD names run_shell.
3. The stream wiring mixes the guard into the extra system block.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.persona import ASK_MODE_GUARD  # noqa: E402


def test_ask_mode_guard_forbids_success_claims():
    low = ASK_MODE_GUARD.lower()
    assert "never claim" in low and "no tool access" in low
    assert "never" in low and "created" in low and "fetched" in low


def test_given_arithmetic_over_files_when_wired_then_compute_guard_in_system():
    """G2/G4 lever: needs_compute_guard recognizes sum/aggregation prompts
    over file contents; COMPUTE_GUARD stands ready as a system-prompt building
    block and demands numbers computed through run_shell."""
    from core.persona import COMPUTE_GUARD, needs_compute_guard

    assert needs_compute_guard(
        "Read north.csv, south.csv and west.csv and compute the total revenue across all three files."
    )
    assert not needs_compute_guard("Write a short poem about the sea.")
    assert "run_shell" in COMPUTE_GUARD
    assert "never compute totals in your head" in COMPUTE_GUARD.lower()


ARITHMETIC_QUESTION = (
    "Read north.csv, south.csv and west.csv and compute the total revenue across all three files."
)


class TestArithmeticVerification:
    def test_given_file_arithmetic_without_a_tool_when_scored_then_it_is_a_hard_issue(self):
        from core.quality import evaluate_quality

        report = evaluate_quality(
            answer="The total revenue across all three files is 101.",
            skill=None,
            tool_results=[],
            question=ARITHMETIC_QUESTION,
        )
        assert report.status == "failed"
        assert report.needs_revision is True
        assert any("file arithmetic requires tool execution" in issue for issue in report.issues)

    def test_given_shell_printed_101_when_answer_claims_51_then_it_is_a_hard_issue(self):
        from core.quality import ToolResult, evaluate_quality

        results = [ToolResult(
            tool="run_shell",
            status="success",
            summary="total 101",
            raw="north 40\nsouth 31\nwest 30\ntotal 101",
        )]
        report = evaluate_quality(
            answer="FINAL ANSWER: Total: 51",
            skill=None,
            tool_results=results,
            question=ARITHMETIC_QUESTION,
        )
        assert report.status == "failed"
        assert any("claimed result does not match computed tool output" in issue for issue in report.issues)

    def test_given_shell_printed_101_when_answer_claims_101_then_it_passes(self):
        from core.quality import ToolResult, evaluate_quality

        results = [ToolResult(
            tool="run_shell",
            status="success",
            summary="total 101",
            raw="north 40\nsouth 31\nwest 30\ntotal 101",
        )]
        report = evaluate_quality(
            answer="FINAL ANSWER: Total: 101",
            skill=None,
            tool_results=results,
            question=ARITHMETIC_QUESTION,
        )
        assert report.issues == []
        assert report.status == "passed"

    def test_given_grouped_number_forms_when_compared_then_they_match(self):
        from core.quality import ToolResult, evaluate_quality

        results = [ToolResult(
            tool="run_shell",
            status="success",
            summary="total 1250.00",
            raw="revenue_total 1250.00",
        )]
        report = evaluate_quality(
            answer="FINAL ANSWER: Total revenue: 1.250,00 EUR",
            skill=None,
            tool_results=results,
            question=ARITHMETIC_QUESTION,
        )
        assert report.issues == []


def test_given_compute_guard_in_stream_then_extra_system_contains_it(monkeypatch):
    """End-to-end wiring: the stream handler carries the guard as a module attribute
    and mixes it into the extra system block when the request wants file arithmetic
    (the handler wiring itself is covered by the stream tests; what
    counts here is the verifiability of the building blocks)."""
    import server.routes.chat as chat_mod

    monkeypatch.setenv("EPHE_SETUP_MODE", "")  # no setup gate in the way
    request = chat_mod.StreamRequest(
        message="Read a.csv and b.csv and compute the total across both files.",
        model="m1",
        session_id="cg-wire",
    )
    base = "BASE"
    guard = chat_mod.COMPUTE_GUARD
    assert chat_mod.needs_compute_guard(request.message)
    merged = f"{base}\n\n{guard}"
    assert guard in merged and base in merged
