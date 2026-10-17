"""The bench must refuse to record engine plumbing as an agent loss.

Measured 2026-10-09, from a killed run under /tmp/bench-option-b/runs: the engine was
switched away while the run was in flight, 18 reps answered nothing, and every one of
them was recorded as `ok: false`. The trend point scored `7/15` next to the `58/60`
points — six tasks had lost their pass^3 to a provider that never received a prompt.
`_active_model`'s own docstring already said such a loss "says nothing about Ephe".
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from tests.subprocess_env import hermetic_env

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str, monkeypatch) -> object:
    """Load a script module from its path with the bench pointed at no server.

    EPHE_BENCH_MODEL short-circuits `_active_model()`: importing the bench would
    otherwise open a socket to whatever product surface happens to be listening.
    """
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _rep(task_id: str, rep: int, ok: bool, error_class: str | None = None,
         family: str = "tau", wall_ms: float = 1000.0, note: str = "") -> dict:
    return {
        "task_id": task_id, "family": family, "level": "L2", "rep": rep, "ok": ok,
        "error_class": error_class, "note": note, "wall_ms": wall_ms,
        "tool_calls": [], "answer_chars": 40, "tokens_out_proxy": 10.0,
    }


ENGINE_NOTE = "engine: Local Ollama is not reachable right now. Start Ephe with `ephe start`"


def test_engine_note_keeps_its_class(monkeypatch):
    bench = _load("_bench_under_test_class", "evals/bench_option_b.py", monkeypatch)
    assert bench._error_class(ENGINE_NOTE) == "engine"
    assert bench._error_class("final-answer==60") == "assertion"


def test_registry_and_docstring_agree_on_the_matrix_size(monkeypatch):
    # The docstring said "10 tasks x 3 reps" while the registry held 60: anyone
    # planning a run from it budgeted a sixth of the time and thought they were done.
    bench = _load("_bench_under_test_matrix", "evals/bench_option_b.py", monkeypatch)
    assert len(bench.TASKS) == 60
    doc = bench.__doc__ or ""
    assert "60 tasks" in doc and "180 reps" in doc


def test_transport_failure_is_classed_engine(monkeypatch, tmp_path):
    # Given a surface that never answers the request
    bench = _load("_bench_under_test_transport", "evals/bench_option_b.py", monkeypatch)
    bench.RUNS = tmp_path / "runs"
    bench.WORKSPACE = tmp_path / "ws"

    def refuse(*args, **kwargs):
        raise urllib.error.URLError("[Errno 61] Connection refused")

    bench.stream_turn_retry = refuse
    # When a rep runs against it
    manifest = bench.run_task(bench.Task("T1", "tau", ["ping"], lambda ctx: (True, "never")), 1)
    # Then the failure names the engine, so no scorer can read it as Ephe failing a task
    assert manifest["ok"] is False
    assert manifest["error_class"] == "engine"
    assert manifest["note"].startswith("engine: transport URLError")


def test_silent_after_tools_is_an_agent_result_not_plumbing(monkeypatch, tmp_path):
    # Given a rep that reached the model, ran tools, and then said nothing at the end
    bench = _load("_bench_under_test_silent", "evals/bench_option_b.py", monkeypatch)
    bench.RUNS = tmp_path / "runs"
    bench.WORKSPACE = tmp_path / "ws"
    events = [
        {"type": "tool_done", "tool": "write_file", "duration_ms": 420.0},
        {"type": "error", "msg": "Die Werkzeuge sind durchgelaufen, aber zum Schluss …"},
    ]
    bench.stream_turn_retry = lambda *a, **k: ("", events, 900.0,
                                              {"prompt_tokens": 24823, "completion_tokens": 1399})
    # When the rep is classified
    rep = bench.run_task(bench.Task("W4", "endstate", ["go"],
                                   lambda ctx: (False, "a_gone=False b_gone=False")), 1)
    # Then it stays a result: the engine spoke, the task was not completed
    assert rep["error_class"] == "assertion"
    assert rep["note"] == "a_gone=False b_gone=False"


def test_provider_that_never_spoke_stays_engine(monkeypatch, tmp_path):
    # Given an error event with no tool run and no completion tokens (measured shape
    # of the 2026-10-09 switch: prompt tokens only, completion None)
    bench = _load("_bench_under_test_silent2", "evals/bench_option_b.py", monkeypatch)
    bench.RUNS = tmp_path / "runs"
    bench.WORKSPACE = tmp_path / "ws"
    events = [{"type": "error", "msg": "Local Ollama is not reachable right now"}]
    bench.stream_turn_retry = lambda *a, **k: ("", events, 9700.0, {"prompt_tokens": 162})
    rep = bench.run_task(bench.Task("G3", "gaia", ["go"], lambda ctx: (True, "never")), 1)
    assert rep["error_class"] == "engine"


def test_scorecard_excludes_a_task_the_engine_ended(monkeypatch, tmp_path):
    # Given three clean tasks and one task whose third rep never reached a model
    bench = _load("_bench_under_test_score", "evals/bench_option_b.py", monkeypatch)
    bench.RUNS = tmp_path / "runs"
    (tmp_path / "runs").mkdir()
    runs = [
        _rep("T1", 1, True), _rep("T1", 2, True), _rep("T1", 3, True),
        _rep("T2", 1, True), _rep("T2", 2, True), _rep("T2", 3, True),
        _rep("T3", 1, True), _rep("T3", 2, True), _rep("T3", 3, True),
        _rep("T4", 1, True), _rep("T4", 2, True),
        _rep("T5", 1, True), _rep("T5", 2, True),
        _rep("T5", 3, False, "engine", note=ENGINE_NOTE),
    ]
    # When the scorecard is built
    text = bench.score(runs)
    # Then T5 is BLOCKED and out of the denominator, and a rep that did reach the
    # model still fails normally (T4: incomplete, counted as before)
    assert "T5 (tau): pass^3=BLOCKED (1/3 reps never reached the engine: " in text
    assert "**pass^3 total**: 3/4" in text
    assert "**engine-blocked, not scored**: 1 task(s) — T5" in text


def test_exclusion_does_not_hide_a_real_failure_in_the_same_task(monkeypatch, tmp_path):
    # Given one rep the engine never answered and one rep Ephe genuinely lost
    bench = _load("_bench_under_test_hide", "evals/bench_option_b.py", monkeypatch)
    bench.RUNS = tmp_path / "runs"
    (tmp_path / "runs").mkdir()
    text = bench.score([
        _rep("T9", 1, False, "assertion", note="c=False a_gone=False"),
        _rep("T9", 2, True),
        _rep("T9", 3, False, "engine", note=ENGINE_NOTE),
    ])
    # Then the task leaves the denominator and its real failure is still printed
    assert "pass^3 total" not in text
    assert "other failed reps: ['c=False a_gone=False']" in text


def test_trend_point_loses_the_task_instead_of_blaming_ephe(monkeypatch):
    trend = _load("_trend_under_test", "evals/bench_trend.py", monkeypatch)
    runs = (
        [_rep("T1", i, True) for i in (1, 2, 3)]
        + [_rep("T2", 1, True), _rep("T2", 2, True),
           _rep("T2", 3, False, "engine", wall_ms=30_000.0, note=ENGINE_NOTE)]
    )
    point = trend.compute_point(runs, ts="2026-10-09T00:00:00", commit="deadbeef",
                                engine="ollama", model="gemma4:12b")
    assert point["pass3_total"] == "1/1"
    assert point["n_tasks_effective"] == 1
    assert point["blocked_task_ids"] == ["T2"]
    assert point["n_reps_blocked"] == 1
    assert point["reps_total"] == 5
    assert "not comparable with full-matrix points" in point["comparability"]
    # The engine keeps its entry in the taxonomy: what happened stays readable
    assert point["error_histogram"] == {"engine": 1}
    # and the 30 s plumbing rep does not enter the timing axis of a scored matrix
    assert point["wall_median_s"] == 1.0


def test_preflight_refuses_a_dead_base_url(monkeypatch):
    # Given a bench pointed at a port nothing listens on, with a model pinned so the
    # refusal cannot be an artifact of the missing model
    monkeypatch.setenv("EPHE_BENCH_BASE", "http://127.0.0.1:1")
    bench = _load("_bench_under_test_preflight", "evals/bench_option_b.py", monkeypatch)
    # When the run asks whether it may start
    with pytest.raises(bench.EngineUnavailable) as excinfo:
        bench._preflight()
    # Then it stops and names the surface the tasks would have needed
    assert "127.0.0.1:1" in str(excinfo.value)


def test_run_against_dead_base_url_records_nothing(tmp_path):
    # The same refusal through the CLI, in its own scratch tree: exit 2, the reason
    # on stderr, and no manifest directory left behind.
    scratch = tmp_path / "scratch"
    done = subprocess.run(
        [sys.executable, str(REPO / "evals" / "bench_option_b.py"),
         "--only", "W1", "--reps", "1"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env=hermetic_env(
            EPHE_BENCH_BASE="http://127.0.0.1:1", EPHE_BENCH_DIR=str(scratch),
            PATH="/usr/bin:/bin", HOME=str(tmp_path), PYTHONPATH=str(REPO),
        ),
    )
    assert done.returncode == 2
    assert "[precondition]" in done.stderr and "nothing recorded" in done.stderr
    assert "W1" in done.stderr
    assert not (scratch / "runs").exists() or not list((scratch / "runs").glob("*.json"))
