"""The trend line's gates: what may be appended, and what a reader sees first.

A 26-task endstate run and a 60-task matrix run are both "the bench". Only one of them
can carry a before/after, and the file used to accept both with nothing but a smaller
denominator to say which was which. These tests run in-process on purpose: a spawned
interpreter is the class of failure `tests/test_port_squatter_guard.py` documents on the
shared CI runners, and a gate test must not depend on one.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FULL_IDS = ([f"T{i}" for i in range(1, 18)] + [f"G{i}" for i in range(1, 18)]
            + [f"W{i}" for i in range(1, 17)] + [f"K{i}" for i in range(1, 11)])


def _trend():
    name = "_bench_trend_under_gate_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_trend.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: A manifest as the harness writes it now. The values are fixed because the gate under
#: test compares them against each other, not against this repository.
ADDRESS = {"commit": "c" * 40, "commit_short": "ccccccc",
           "surface": {"core": "a" * 40, "server": "b" * 40},
           "surface_sha": "s" * 40, "dirty": []}


def _reps(task_ids, ok=True, address=ADDRESS):
    rows = []
    for t in task_ids:
        for r in (1, 2, 3):
            row = {"task_id": t,
                   "family": "tau" if t.startswith("T") else "gaia" if t.startswith("G") else "endstate",
                   "level": "L2", "rep": r, "ok": ok, "error_class": None if ok else "assertion",
                   "note": "", "wall_ms": 1000.0, "tool_calls": []}
            if address is not None:
                row["code_address"] = dict(address)
            rows.append(row)
    return rows


def _write_runs(runs_dir: Path, task_ids, address=ADDRESS) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    for record in _reps(task_ids, address=address):
        name = f"{record['task_id'].lower()}_r{record['rep']}.json"
        (runs_dir / name).write_text(json.dumps(record), encoding="utf-8")


def _append_only(monkeypatch, trend, tmp_path, extra=()):
    out = tmp_path / "trend.json"
    monkeypatch.setattr(sys, "argv", ["bench_trend", "--runs", str(tmp_path / "runs"),
                                      "--out", str(out), "--ts", "2026-10-10T12:00:00", *extra])
    return out


def test_the_registry_count_is_parsed_and_is_sixty():
    assert _trend()._matrix_size() == len(FULL_IDS) == 60


def test_a_family_only_point_is_not_appended(monkeypatch, tmp_path, capsys):
    trend = _trend()
    _write_runs(tmp_path / "runs", ["W1", "W2", "W3"])
    out = tmp_path / "trend.json"
    monkeypatch.setattr(sys, "argv", ["bench_trend", "--runs", str(tmp_path / "runs"),
                                      "--out", str(out), "--ts", "2026-10-10T12:00:00"])
    with pytest.raises(SystemExit) as exc:
        trend.main()
    assert exc.value.code == 2
    assert not out.exists(), "a blocked point must not reach the file at all"
    seen = capsys.readouterr()
    assert "not appended: partial matrix: 3 of 60 tasks" in seen.err
    assert "--allow-partial" in seen.err


def test_an_allowed_submatrix_carries_the_reason_it_was_given(monkeypatch, tmp_path):
    trend = _trend()
    _write_runs(tmp_path / "runs", ["W1", "W2", "W3"])
    out = tmp_path / "trend.json"
    monkeypatch.setattr(sys, "argv", ["bench_trend", "--runs", str(tmp_path / "runs"),
                                      "--out", str(out), "--ts", "2026-10-10T12:00:00",
                                      "--allow-partial", "R38 A/B over the endstate family"])
    trend.main()
    point = json.loads(out.read_text(encoding="utf-8"))[-1]
    assert point["submatrix_reason"] == "R38 A/B over the endstate family"
    assert "appended under --allow-partial" in point["comparability"]
    assert point["matrix_tasks"] == 60


def test_a_full_matrix_passes_the_gate():
    trend = _trend()
    point = trend.compute_point(_reps(FULL_IDS), ts="t", commit="c", engine="e", model="m")
    assert point["n_tasks_effective"] == 60
    assert trend.partial_block(point) == ""


def test_the_number_and_its_interval_arrive_as_one_string():
    trend = _trend()
    point = trend.compute_point(_reps([f"T{i}" for i in range(1, 18)]),
                                ts="t", commit="c", engine="e", model="m")
    # a clean sweep of 17 tasks is 100% and still ±9 points wide — the display is the point
    assert point["pass3_display"] == "17/17 = 100.0% ± 9.2"
    assert point["pass1_display"] == "51/51 = 100.0% ± 3.5"
    assert point["by_family_display"] == {"tau": "17/17 = 100.0% ± 9.2"}


def test_a_lost_task_shows_in_the_display_too():
    trend = _trend()
    reps = _reps([f"T{i}" for i in range(1, 18)])
    for r in reps:
        if r["task_id"] == "T2":
            r["ok"], r["error_class"], r["note"] = False, "assertion", "final-answer==OF-B"
    point = trend.compute_point(reps, ts="t", commit="c", engine="e", model="m")
    assert point["pass3_display"] == "16/17 = 94.1% ± 13.0"
    assert point["pass1_display"] == "48/51 = 94.1% ± 7.0"


def test_the_gate_reports_its_own_blind_spot():
    # If the registry cannot be read, the check says so instead of waving the point in
    trend = _trend()
    point = {"n_tasks_effective": 3, "matrix_tasks": None, "pass3_display": "3/3 = 100.0% ± 0.0"}
    assert "could not be read" in trend.partial_block(point)


def test_an_old_point_without_a_display_still_names_its_count():
    trend = _trend()
    point = {"n_tasks_effective": 55, "matrix_tasks": 60, "pass3_total": "53/55"}
    msg = trend.partial_block(point)
    assert "partial matrix: 55 of 60 tasks" in msg and "(53/55)" in msg


# the code address on the append rule
def test_a_cohort_that_names_no_code_is_not_appended(monkeypatch, tmp_path, capsys):
    # Given the old manifests: nine reps, no commit, no measured surface
    trend = _trend()
    _write_runs(tmp_path / "runs", ["T1", "T2", "T3"], address=None)
    out = _append_only(monkeypatch, trend, tmp_path)
    with pytest.raises(SystemExit) as exc:
        trend.main()
    err = capsys.readouterr().err
    assert exc.value.code == 2 and not out.exists()
    assert "no code address: 9 of 9 manifest(s)" in err and "--allow-legacy" in err


def test_an_old_cohort_joins_only_with_a_recorded_reason(monkeypatch, tmp_path):
    trend = _trend()
    _write_runs(tmp_path / "runs", FULL_IDS, address=None)
    out = _append_only(monkeypatch, trend, tmp_path,
                       ("--allow-legacy", "carrying the 2026-09 cohort over"))
    trend.main()
    point = json.loads(out.read_text(encoding="utf-8"))[-1]
    assert point["legacy_reason"] == "carrying the 2026-09 cohort over"
    assert "--allow-legacy" in point["comparability"]


def test_two_stands_in_one_cohort_are_refused_and_cannot_be_waived(monkeypatch, tmp_path, capsys):
    # Given reps whose measured surface moved halfway through the run
    trend = _trend()
    _write_runs(tmp_path / "runs", FULL_IDS)
    moved = tmp_path / "runs" / "t1_r3.json"
    row = json.loads(moved.read_text(encoding="utf-8"))
    row["code_address"] = {**row["code_address"], "surface_sha": "d" * 40,
                           "commit": "d" * 40, "commit_short": "ddddddd"}
    moved.write_text(json.dumps(row), encoding="utf-8")
    for waiver in (("--allow-legacy", "waive it"), ("--allow-partial", "waive it"), ()):
        out = tmp_path / f"trend{len(waiver)}.json"
        monkeypatch.setattr(sys, "argv", ["bench_trend", "--runs", str(tmp_path / "runs"),
                                         "--out", str(out), *waiver])
        with pytest.raises(SystemExit) as exc:
            trend.main()
        err = capsys.readouterr().err
        assert exc.value.code == 2 and not out.exists()
        assert "the tree moved mid-run: 2 measured stands" in err
        assert "no flag waives this" in err, "a mixed cohort is not a permission problem"


def test_two_commits_of_one_measured_surface_are_still_one_point(monkeypatch, tmp_path):
    # Given the tree moved but core/ and server/ did not: the same server answered both halves
    trend = _trend()
    _write_runs(tmp_path / "runs", FULL_IDS)
    later = tmp_path / "runs" / "t1_r3.json"
    row = json.loads(later.read_text(encoding="utf-8"))
    row["code_address"] = {**row["code_address"], "commit": "e" * 40, "commit_short": "eeeeeee"}
    later.write_text(json.dumps(row), encoding="utf-8")
    out = _append_only(monkeypatch, trend, tmp_path)
    trend.main()
    point = json.loads(out.read_text(encoding="utf-8"))[-1]
    assert point["code_address"]["stands"] == 1 and point["code_address"]["commits"] == 2
    assert point["code_address"]["status"] == "single-stand"
