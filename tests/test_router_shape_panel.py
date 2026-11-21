"""Ephe — the shape panel's instrument holds, and an arm that cannot answer stays empty.

The panel is the only place the router's cost claim can come from, so these tests check the
instrument rather than any model: every shape's checker must accept its answer and reject the
named wrong answer, the two shapes whose expectations were wrong at first must now read the
correct path arithmetic and suffix filter, and a tier that cannot produce a turn must appear as
`unreachable` without the other arm's reply being written into its row.

No test here reads a clock, so none belongs in the timing segment.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PANEL_PATH = REPO / "scripts" / "router_shape_panel.py"


def _load_panel():
    spec = importlib.util.spec_from_file_location(
        "router_shape_panel_under_test", PANEL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


panel = _load_panel()


def test_GIVEN_the_shape_table_WHEN_the_checkers_are_audited_THEN_no_defect_is_listed():
    assert panel.checkers_hold() == []


@pytest.mark.parametrize(
    "shape", list(panel.SHAPES), ids=[s["id"] for s in panel.SHAPES]
)
def test_GIVEN_a_shape_WHEN_its_own_answer_is_checked_THEN_the_checker_accepts_it(
    shape,
):
    answer = shape.get("expected")
    if answer is None:
        answer = str(shape.get("expected_array") or shape.get("expected_object"))
    if "expected_object" in shape:
        answer = '{"total": "1107"}'
    if "expected_array" in shape:
        answer = '["2026-03-invoice-001.pdf", "invoice-archive.tar", "invoices"]'

    assert panel.check(shape, answer) is True


@pytest.mark.parametrize(
    "shape", list(panel.SHAPES), ids=[s["id"] for s in panel.SHAPES]
)
def test_GIVEN_a_shape_WHEN_the_wrong_answer_is_checked_THEN_the_checker_rejects_it(
    shape,
):
    assert panel.check(shape, shape["wrong"]) is False


def test_GIVEN_path_arithmetic_WHEN_the_instrument_was_corrected_THEN_notes_dotdot_is_cancelled():
    shape = next(s for s in panel.SHAPES if s["id"] == "path-arithmetic")

    assert shape["payload"] == "./notes/../report.md"
    assert panel.check(shape, "report.md") is True
    assert panel.check(shape, "notes/report.md") is False


def test_GIVEN_the_suffix_filter_WHEN_a_tmp_name_is_offered_THEN_it_is_not_a_json_file():
    shape = next(s for s in panel.SHAPES if s["id"] == "listing")

    assert panel.check(shape, "ledger.json\ntodos.json") is True
    assert panel.check(shape, "ledger.json\nledger.json.tmp\ntodos.json") is False


def test_GIVEN_a_tier_that_cannot_answer_WHEN_the_panel_runs_it_THEN_the_row_stays_unreachable(
    monkeypatch, capsys
):
    class _Failing:
        async def chat(self, **_kwargs):
            raise ConnectionError("Failed to connect to Ollama.")

    monkeypatch.setattr(panel.ollama, "AsyncClient", lambda **_kw: _Failing())

    rc = panel.main(["--arm", "small", "--only", "field-extract", "--reps", "1"])
    printed = capsys.readouterr().out

    assert rc == 0
    assert "unreachable" in printed
    assert '{"total":"1107"}' not in printed


def test_GIVEN_an_unreachable_arm_WHEN_its_summary_is_built_THEN_no_answer_is_counted_as_passed():
    rows = [
        {
            "shape": "listing",
            "rep": 1,
            "arm": "small",
            "model": "m",
            "status": "unreachable",
            "error": "ConnectionError",
            "wall_ms": 1.0,
        },
    ]
    summary = panel.summarise(rows)

    assert summary["answered"] == 0
    assert summary["passed"] == 0
    assert summary["unreachable"] == 1


def test_GIVEN_selftest_WHEN_the_checkers_hold_THEN_it_exits_zero(capsys):
    assert panel.main(["--selftest"]) == 0
    assert "checker defect" not in capsys.readouterr().out
