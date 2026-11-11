"""The context-ablation harness, driven offline: arms, verifier, JSON and the paired read.

Everything here runs without an engine. The dry run is the mode under test, so a green
suite proves the two arms are built from one fixture tree, that the verdict comes from a
real verifier on restored tests, that the JSON carries both arms and the task count, and
that no fixture repository is written to. The statistics in ``--compare`` are pinned to
numbers that can be checked on paper.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "evals" / "context_ablation" / "harness.py"


def _load():
    name = "_context_ablation_under_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load()
FIXTURES = REPO / "evals" / "context_ablation" / "fixtures"


def _digest(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _task(fixture: str, tmp_path: Path, stub: dict[str, str]) -> harness.Task:
    copy = tmp_path / "fixture" / fixture
    shutil.copytree(FIXTURES / fixture, copy)
    return harness.Task(
        id=fixture, prompt="take the failing tests to green", fixture=copy,
        verify=("{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"),
        guard=("tests",), stub=dict(stub))


def _result(path: Path, passed: dict[str, bool]) -> Path:
    document = {
        "schema": harness.SCHEMA, "mode": "real", "evidence": "engine",
        "arms": list(harness.ARMS),
        "tasks": [{"id": task_id,
                   "arms": {arm: {"passed": passed[task_id]} for arm in harness.ARMS}}
                  for task_id in passed],
        "summary": {},
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_dry_run_covers_both_arms_and_counts_the_tasks(tmp_path, monkeypatch):
    def no_engine(*_args, **_kwargs):
        raise AssertionError("a dry run must not resolve an engine")

    monkeypatch.setattr(harness, "preflight", no_engine)
    out = tmp_path / "result.json"
    code = harness.main(["--dry-run", "--out", str(out), "--workdir", str(tmp_path / "work")])
    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema"] == harness.SCHEMA
    assert document["mode"] == "dry-run"
    assert document["evidence"] == "stub"
    assert document["arms"] == ["with_agents", "no_agents"]
    assert document["counter"] == harness.tokenizer_backend()
    assert [row["id"] for row in document["tasks"]] == ["slugify", "pricing"]
    assert document["summary"]["n_tasks"] == 2
    for row in document["tasks"]:
        assert set(row["arms"]) == set(harness.ARMS)
        carried = row["arms"]["with_agents"]
        bare = row["arms"]["no_agents"]
        assert carried["context"]["files"] == [harness.RULES_NAME]
        assert carried["context"]["tokens"] > 0
        assert bare["context"] == {"files": [], "chars": 0, "tokens": 0}
        assert carried["tokens"]["source"] == "estimated"
        assert carried["tokens"]["tokenizer"] == harness.tokenizer_backend()
    summary = document["summary"]
    assert (summary["delta"]["tokens_total"]
            == summary["arms"]["with_agents"]["tokens_total"]
            - summary["arms"]["no_agents"]["tokens_total"])


def test_the_two_arms_differ_only_by_the_rule_file(tmp_path):
    task = harness.load_tasks(harness.DEFAULT_TASKS)[0]
    carried = harness.prepare_arm(task, "with_agents", tmp_path / "work")
    bare = harness.prepare_arm(task, "no_agents", tmp_path / "work")
    files_carried = {path.relative_to(carried) for path in carried.rglob("*") if path.is_file()}
    files_bare = {path.relative_to(bare) for path in bare.rglob("*") if path.is_file()}
    assert files_carried - files_bare == {Path(harness.RULES_NAME)}
    assert not files_bare - files_carried
    assert harness.context_text(bare) == ""
    assert harness.context_text(carried).strip() != ""


def test_the_stub_plays_the_arm_but_the_verifier_decides(tmp_path):
    task = _task("slugify", tmp_path, {"with_agents": "pass", "no_agents": "fail"})
    carried = harness.prepare_arm(task, "with_agents", tmp_path / "work")
    bare = harness.prepare_arm(task, "no_agents", tmp_path / "work")
    passing = harness.stub_arm(task, "with_agents", carried, 120, harness.context_block(carried))
    failing = harness.stub_arm(task, "no_agents", bare, 120, harness.context_block(bare))
    assert passing["passed"] is True and passing["exit_code"] == 0
    assert failing["passed"] is False and failing["exit_code"] != 0
    assert "solution" in passing["notes"][0]
    assert failing["verify_tail"].strip() != ""


def test_restoring_the_tests_beats_a_rewritten_check(tmp_path):
    task = _task("slugify", tmp_path, {"with_agents": "pass", "no_agents": "pass"})
    workspace = harness.prepare_arm(task, "with_agents", tmp_path / "work")
    (workspace / "tests" / "test_textkit.py").write_text(
        "def test_nothing():\n    assert True\n", encoding="utf-8")
    assert harness.run_verify(task, workspace, 120)["passed"] is True
    assert harness.restore_guards(task, workspace) == ["tests"]
    assert harness.run_verify(task, workspace, 120)["passed"] is False


def test_a_dry_run_does_not_touch_the_fixture_repositories(tmp_path):
    before = _digest(FIXTURES)
    out = tmp_path / "result.json"
    assert harness.main(["--out", str(out), "--workdir", str(tmp_path / "work")]) == 0
    assert _digest(FIXTURES) == before


def test_a_real_run_stops_before_a_turn_without_an_engine(tmp_path, monkeypatch):
    for name in ("EPHE_MODEL_PROVIDER", "EPHE_MODEL_ENDPOINT", "EPHE_MODEL",
                 "EPHE_LOCAL_OLLAMA_BASE_URL", "EPHE_CUSTOM_OLLAMA_BASE_URL",
                 "EPHE_OPENAI_COMPAT_BASE_URL", "EPHE_CONFIG_DIR", "EPHE_WORKSPACE",
                 "EPHE_WORKSPACES_DIR"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    out = tmp_path / "result.json"
    with pytest.raises(SystemExit) as stopped:
        harness.main(["--real", "--out", str(out), "--workdir", str(tmp_path / "work")])
    assert "configure" in str(stopped.value)
    assert not out.exists()


def test_tost_is_hand_checkable():
    # four pairs that agree bound the difference by 1-0.05**(1/4) = 0.527, not by zero
    flat = harness.tost([0, 0, 0, 0], 0.10)
    assert abs(flat["bound"] - 0.5271291954984121) < 1e-12
    assert flat["p"] == 1.0
    assert abs(flat["ci90"][0] + flat["bound"]) < 1e-12
    # sixty pairs that agree are inside the margin: 1-0.05**(1/60) = 0.0487
    tight = harness.tost([0] * 60, 0.10)
    assert abs(tight["bound"] - 0.04870291331009746) < 1e-12
    assert tight["p"] == 0.0
    # five pairs each way: mean 0, se = sqrt((10/9)/10) = 1/3, one tail 1-Phi(0.3)
    noise = harness.tost([1, -1] * 5, 0.10)
    assert abs(noise["se"] - 1 / 3) < 1e-12
    assert abs(noise["p"] - 0.38209) < 5e-5
    assert noise["ci90"][1] > 0.10
    # a shift the margin cannot cover is never called equivalent
    assert harness.tost([1] * 8, 0.10)["p"] == 1.0


def test_compare_calls_equivalence_and_detects_a_shift(tmp_path):
    same = {f"t{i}": True for i in range(60)}
    another = dict(same)
    identical = harness.compare(_result(tmp_path / "a.json", same),
                                _result(tmp_path / "b.json", another), "with_agents", 0.10)
    assert "equivalent within +/-10.0 pp" in identical
    assert "exact sign test: p=1.0000" in identical

    flipped = dict(same)
    for task_id in list(same)[:6]:
        flipped[task_id] = False
    shifted = harness.compare(_result(tmp_path / "c.json", same),
                              _result(tmp_path / "d.json", flipped), "with_agents", 0.10)
    assert "a difference is detectable" in shifted
    assert "6 passing only in A" in shifted
    assert "exact sign test: p=0.0312" in shifted


def test_compare_refuses_a_pair_it_cannot_pair(tmp_path):
    one = _result(tmp_path / "a.json", {"t0": True})
    two = _result(tmp_path / "b.json", {"t0": True})
    with pytest.raises(SystemExit) as stopped:
        harness.compare(one, two, "with_agents", 0.10)
    assert "paired test needs 2" in str(stopped.value)
