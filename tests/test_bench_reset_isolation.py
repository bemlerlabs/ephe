"""Every reset and isolation rule that lets a rep pass on state it did not produce.

The bench scores three reps per task and calls the task reliable only when all three
pass. That number is only about the rep if each rep starts from the same state — and it
did not: `k10_out.json` had no reset and no write-guard (its mere presence was the
verdict), the malformed fixtures of W9, T13 and K4 were written once outside the rep
loop (rep 1 repaired them, reps 2..3 passed on the repair), nothing purged the workspace
at cohort start, the G3/G4 artefact checks read four homes while the reset cleared only
one, and a resumed run kept a stale manifest and skipped its reset.

Each test below states the assumption it pins, so a change that reopens one is visible
by name rather than only in a rate that drifted up.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """The harness module on a private cohort: no server, no user path, no network."""
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    monkeypatch.setenv("EPHE_BENCH_BASE", "http://127.0.0.1:1")
    monkeypatch.setenv("EPHE_BENCH_DIR", str(tmp_path / "cohort"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_BENCH_PRICE_IN_PER_M", "0.05")
    monkeypatch.setenv("EPHE_BENCH_PRICE_OUT_PER_M", "0.40")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EPHE_BENCH_WORKSPACE", raising=False)
    name = f"_bench_reset_{abs(hash(str(tmp_path)))}"
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_option_b.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.WORKSPACE == tmp_path / "cohort" / "ws"
    assert module.OUTPUT_DIR == tmp_path / "cohort" / "out"
    module.WORKSPACE.mkdir(parents=True, exist_ok=True)
    return module


def _frames(calls):
    """tool_start/tool_done pairs as the stream carries them."""
    events = []
    for i, (tool, args) in enumerate(calls):
        cid = f"c{i}"
        events.append({"type": "tool_start", "tool": tool, "call_id": cid, "args": args})
        events.append({"type": "tool_done", "tool": tool, "call_id": cid, "result": "ok"})
    return events


# K10: no reset entry, and a check that read the file's presence
def test_a_k10_rep_that_inherits_k10_out_json_does_not_pass(bench):
    # Given k10_out.json already holds the right sum, planted by an earlier rep
    (bench.WORKSPACE / "k10_out.json").write_text(json.dumps({"sum": 1107}), encoding="utf-8")
    reads_only = _frames([("read_file", {"path": "kdoc_008.json"})])
    # When a rep that only read is checked against the inherited file
    ok, note = bench.k10_check(bench.Ctx("FINAL ANSWER: 1107", reads_only, 0.0))
    # Then it fails for the missing write, even though the file is present and correct
    assert ok is False
    assert note == "k10_out.json not written by this rep"
    # And a rep that wrote the file itself passes on the existing sum test
    wrote = _frames([("write_file", {"path": "k10_out.json", "content": '{"sum": 1107}'})])
    ok, note = bench.k10_check(bench.Ctx("FINAL ANSWER: 1107", wrote, 0.0))
    assert ok is True
    assert note == "sum=1107"


def _task(bench, task_id: str):
    return next(t for t in bench.TASKS if t.id == task_id)


def test_the_per_rep_reset_removes_k10_out_json(bench):
    # A rep must not inherit an earlier rep's end-state file
    inherited = bench.WORKSPACE / "k10_out.json"
    inherited.write_text(json.dumps({"sum": 1107}), encoding="utf-8")
    # When the rep is about to run
    bench.reset_task_state(_task(bench, "K10"))
    # Then the inherited file is gone
    assert not inherited.exists()


# W9 / T13 / K4: the malformed fixture was written once, outside the rep loop
@pytest.mark.parametrize(
    ("task_id", "name"),
    (("W9", "w9_broken.json"), ("T13", "t13_cfg.json"), ("K4", "kdoc_119.json")),
)
def test_the_per_rep_reset_rematerialises_the_broken_fixture(bench, task_id, name):
    # Given the fixture as rep 1 left it: repaired in place, so it parses
    repaired = bench.WORKSPACE / name
    repaired.write_text(json.dumps({"id": 119, "val": 119, "next": None}), encoding="utf-8")
    json.loads(repaired.read_text(encoding="utf-8"))
    # When the next rep's state is set
    bench.reset_task_state(_task(bench, task_id))
    # Then the broken form is back, so the repair is the rep's work again
    with pytest.raises(json.JSONDecodeError):
        json.loads(repaired.read_text(encoding="utf-8"))


def test_the_broken_fixtures_the_writer_ships_and_the_reset_restores_are_the_same():
    # The reset can only put back what the writer wrote: one source, not two literals.
    source = (REPO / "evals" / "bench_option_b.py").read_text(encoding="utf-8")
    assert '"T13": ("t13_cfg.json"' in source
    assert '"W9": ("w9_broken.json"' in source
    assert '"K4": ("kdoc_119.json"' in source
    assert 'BROKEN_FIXTURES["T13"][1]' in source
    assert 'BROKEN_FIXTURES["W9"][1]' in source
    assert 'BROKEN_FIXTURES["K4"][1]' in source


# Cohort start: nothing from a previous cohort may survive into rep 1
def test_cohort_start_purges_the_workspace_and_the_output_dir(bench):
    # Given leftovers from a previous cohort in both bench-owned homes
    (bench.WORKSPACE / "k10_out.json").write_text(json.dumps({"sum": 1107}), encoding="utf-8")
    (bench.WORKSPACE / "w9_broken.json").write_text(json.dumps({"n": 7, "m": 35}), encoding="utf-8")
    bench.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (bench.OUTPUT_DIR / "file-summary.pdf").write_text("%PDF-1.4 stale", encoding="utf-8")
    # When the cohort starts
    bench.purge_cohort_state()
    # Then neither home carries anything from the earlier run
    assert list(bench.WORKSPACE.iterdir()) == []
    assert list(bench.OUTPUT_DIR.iterdir()) == []
    assert bench.WORKSPACE.is_dir() and bench.OUTPUT_DIR.is_dir()


# G3/G4: the checks scan four homes, the reset cleared one
def test_the_artifact_reset_clears_every_home_the_check_scans(bench):
    from core.artifact_workbench import workbench_dir

    # Given an accepted artefact in each of the four homes `_artifact_homes` reads
    downloads = Path.home() / "Downloads"
    kept = {
        bench.WORKSPACE / "file-summary.pdf",
        bench.OUTPUT_DIR / "aggregate-2026.pdf",
        workbench_dir() / "sessions" / "file-summary.pdf",
        downloads / "revenue-brief.md",
    }
    for target in kept:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stale", encoding="utf-8")
    # And a file neither check would accept
    mine = downloads / "holiday-photo.pdf"
    mine.write_text("mine", encoding="utf-8")
    # When the G3 and G4 resets run
    bench.reset_task_state(_task(bench, "G3"))
    bench.reset_task_state(_task(bench, "G4"))
    # Then every accepted name is gone from every home ...
    assert not any(target.exists() for target in kept)
    # ... and a file the check would never accept is untouched
    assert mine.exists()


# Stale manifest resume
def _manifest(task_id, rep, surface, short, ts="2026-01-02T03:04:05"):
    return {
        "task_id": task_id,
        "family": "endstate",
        "rep": rep,
        "ok": True,
        "wall_ms": 1.0,
        "ts": ts,
        "code_address": {
            "commit": surface * 40,
            "commit_short": short,
            "surface_sha": surface * 40,
        },
    }


def test_scoring_a_mixed_cohort_is_refused_unless_the_reason_is_waived(bench, monkeypatch, capsys):
    # Given a runs directory whose manifests were measured on two different surfaces
    bench.RUNS.mkdir(parents=True, exist_ok=True)
    for rep, surface in ((1, "a"), (2, "b")):
        (bench.RUNS / f"w9_r{rep}.json").write_text(
            json.dumps(_manifest("W9", rep, surface, surface * 7)), encoding="utf-8"
        )
    # When --score is asked for the number
    monkeypatch.setattr(sys, "argv", ["bench_option_b.py", "--score"])
    with pytest.raises(SystemExit) as exc:
        bench.main()
    err = capsys.readouterr().err
    # Then it refuses, naming the mixing
    assert exc.value.code == 2
    assert "mixes 2 measured surfaces" in err
    # And with the recorded waiver the same directory scores
    monkeypatch.setattr(bench, "score", lambda runs: "scored")
    monkeypatch.setattr(
        sys, "argv", ["bench_option_b.py", "--score", "--allow-mixed-cohort", "two servers on purpose"]
    )
    bench.main()
    assert "two servers on purpose" in capsys.readouterr().out


def test_a_resume_beside_another_surface_is_a_conflict(bench):
    # Given manifests already on one surface
    rows = [_manifest("W9", rep, "a", "aaaaaaa") for rep in (1, 2, 3)]
    # When this run's surface matches them, the resume may keep skipping
    assert bench.resume_conflict(rows, {"surface_sha": "a" * 40}) is None
    # And when it does not, appending would mix two stands
    conflict = bench.resume_conflict(rows, {"surface_sha": "b" * 40})
    assert conflict and "resume would append" in conflict


def test_the_skip_path_names_the_manifest_own_stand(bench):
    # Given a manifest whose address is not this tree's
    bench.RUNS.mkdir(parents=True, exist_ok=True)
    target = bench.RUNS / "w9_r1.json"
    target.write_text(json.dumps(_manifest("W9", 1, "c", "ccccccc")), encoding="utf-8")
    # When it is described for the skip line
    note = bench.manifest_stand(target)
    # Then it states its own commit, surface and timestamp
    assert "ccccccc" in note
    assert "cccccccccccc" in note
    assert "2026-01-02T03:04:05" in note


def test_a_resume_of_another_cohort_is_refused_unless_waived(bench, monkeypatch, capsys):
    # Given three manifests from another surface already in the runs directory
    bench.RUNS.mkdir(parents=True, exist_ok=True)
    for rep in (1, 2, 3):
        (bench.RUNS / f"w9_r{rep}.json").write_text(
            json.dumps(_manifest("W9", rep, "d", "ddddddd")), encoding="utf-8"
        )
    monkeypatch.setattr(bench, "_preflight", lambda: "test-model")
    monkeypatch.setattr(bench, "require_isolated_surface", lambda *a, **k: str(bench.WORKSPACE))
    monkeypatch.setattr(bench, "score", lambda runs: "scored")
    # When the same task is run again in that directory
    monkeypatch.setattr(sys, "argv", ["bench_option_b.py", "--only", "W9", "--reps", "3"])
    with pytest.raises(SystemExit) as exc:
        bench.main()
    err = capsys.readouterr().err
    # Then it refuses instead of keeping the older stands beside a fresh one
    assert exc.value.code == 2
    assert "resume would append" in err
    # And when the mix is waived, each skip names the stand it kept
    monkeypatch.setattr(
        sys,
        "argv",
        ["bench_option_b.py", "--only", "W9", "--reps", "3", "--allow-mixed-cohort", "kept on purpose"],
    )
    bench.main()
    out = capsys.readouterr().out
    assert "[skip] w9_r1.json" in out
    assert "ddddddd" in out
    assert "kept on purpose" in out
