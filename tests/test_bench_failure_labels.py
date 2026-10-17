"""The two failing traces in the W3 matrix, pinned as labels a test can re-check.

Measured 2026-10-11 from `~/.ephe/bench`. The clean cohort `20261010T2317-60x3-clean`
(trend point 11, 180 manifests at one code address) loses exactly one task: T14 rep 3,
note `final-answer==50 (5-file join)`. The aborted cohort `aborted-2-stands-20261010T2249`
loses W1 in all three reps, note `endstate=False remaining=1`. Both are premature
terminations: the run ends on a prospective statement — a question to the user, or
"I'll ... next" — and never emits the required `FINAL ANSWER:` line, so the answer that
reaches the assertion carries the plan instead of the result. `_error_class` files both
under `assertion`; these assertions hold that label and the end state that
produced it, so a later re-classification is a visible change.

The full label table and trace citations are in `docs/ERROR_ANALYSIS_W3_2026-10-11.md`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The notes exactly as the two failing manifest sets carry them, verbatim from the
# JSON. T14 from `20261010T2317-60x3-clean/runs/t14_r3.json`; W1 from
# `aborted-2-stands-20261010T2249/runs/w1_r{1,2,3}.json`.
T14_R3_NOTE = "final-answer==50 (5-file join)"
W1_NOTE = "endstate=False remaining=1"

# The answer tails that ended each run. T14 rep 3 produced no `FINAL ANSWER:` line at all
# (`final_answer_line` is the empty string); W1 stopped after it announced the second step.
T14_R3_TAIL = (
    "Got the tool evidence — `run_shell` ran fine (status: success, total 1608), but "
    "there's no actual question or task attached to it. What do you want me to do with this?"
)
W1_TAIL = 'I\'ll create the file first, then edit it down to just the "keep me" item.'


def _load(name: str, monkeypatch) -> object:
    """Load the bench with the model pinned so importing it opens no socket."""
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_option_b.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _no_events(bench, answer, tmp_path):
    """A responder that reaches the model, runs nothing, and returns `answer`."""
    bench.RUNS = tmp_path / "runs"
    bench.WORKSPACE = tmp_path / "ws"
    (tmp_path / "runs").mkdir()
    (tmp_path / "ws").mkdir()
    bench.stream_turn_retry = lambda *a, **k: (
        answer,
        [],
        12.0,
        {"prompt_tokens": 18895, "completion_tokens": 120},
    )


def test_error_class_pins_both_measured_failure_labels(monkeypatch):
    bench = _load("_bench_fail_labels", monkeypatch)
    # Both measured failures file under "assertion": a run that reached the model and stopped short is, to the assertion, an ordinary miss.
    assert bench._error_class(T14_R3_NOTE) == "assertion"
    assert bench._error_class(W1_NOTE) == "assertion"
    # "no_final_answer" stays reachable, but the observed runs never take it — the gap the analysis records.
    assert bench._error_class("final=False brief=False") == "no_final_answer"


def test_a_clarifying_question_is_not_a_final_answer(monkeypatch):
    bench = _load("_bench_fail_nofinal", monkeypatch)
    # T14 rep 3's whole answer is a question; `exact_final` must not read one out of it.
    assert bench.exact_final(T14_R3_TAIL, "50") is False
    # The same predicate still reads the line the task asked for.
    assert bench.exact_final(f"`{bench.FINAL} 50`", "50") is True


def test_t14_rep3_replays_to_the_assertion_class(monkeypatch, tmp_path):
    bench = _load("_bench_fail_t14", monkeypatch)
    _no_events(bench, T14_R3_TAIL, tmp_path)
    # When the measured rep-3 answer is scored through the real task check
    task = next(t for t in bench.TASKS if t.id == "T14")
    rep = bench.run_task(task, 3)
    # Then it fails the task, records no final answer, and is not excused as engine loss
    assert rep["ok"] is False
    assert rep["error_class"] == "assertion"
    assert rep["note"] == T14_R3_NOTE
    assert rep["final_answer_line"] == ""


def test_w1_announced_but_unrun_edit_is_caught(monkeypatch, tmp_path):
    bench = _load("_bench_fail_w1", monkeypatch)
    _no_events(bench, W1_TAIL, tmp_path)
    # End state of the measured rep: the file was created with both items, the edit that
    # was announced ("then edit it down") never ran.
    (tmp_path / "ws" / "todos.json").write_text(
        '{"items": [{"title": "draft item", "done": false}, '
        '{"title": "keep me", "done": false}]}',
        encoding="utf-8",
    )
    task = next(t for t in bench.TASKS if t.id == "W1")
    # When the rep is scored
    rep = bench.run_task(task, 2)
    # Then the half-done end state is the failure, named item by item
    assert rep["ok"] is False
    assert rep["error_class"] == "assertion"
    assert rep["note"] == W1_NOTE
    assert rep["final_answer_line"] == ""
