"""The pass^3 release gate reads a cohort's rep manifests and decides whether a release may go out.

The hook is `evals/pass3_release_gate.py`; these tests pin its exit codes against synthetic
cohorts under tmp_path, so no engine is contacted and no clock is read. They live outside
`tests/test_bench_gates.py` on purpose: that file is a serial timing segment, and
`tests/conftest.py` stands every item of the segment down under load, which would quietly
drop these arithmetic checks and move the four-gate skip count
`tests/test_bench_gate_switch.py` asserts.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "evals" / "pass3_release_gate.py"

# A provider API engine (the release bar) and a loopback runtime (refused by the gate).
API_ENGINE = {"provider": "openai_compatible", "model": "deepseek-v4",
              "api_url": "https://api.deepseek.com/v1"}
LOCAL_ENGINE = {"provider": "ollama", "model": "qwen3:8b",
                "api_url": "http://127.0.0.1:11434/v1"}


def _release_gate():
    """evals/pass3_release_gate.py loaded under a private name, so the import cannot collide."""
    spec = importlib.util.spec_from_file_location("_pass3_release_gate_under_test", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_cohort(runs_dir, outcome, *, engine_rep=()):
    """Write one manifest per rep, named the way evals/bench_option_b.py names them.

    `outcome` maps a task id to its per-rep `ok` flags. A (task, rep) in `engine_rep` is
    written with `error_class: "engine"`, the plumbing state the harness drops from a task's
    rep set, so it may not be read as an agent loss or as a flipped verdict.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    for task_id, oks in outcome.items():
        for rep, ok in enumerate(oks, start=1):
            run = {"task_id": task_id, "family": "tau", "rep": rep, "ok": bool(ok),
                   "error_class": "engine" if (task_id, rep) in engine_rep else None}
            (runs_dir / f"{task_id.lower()}_r{rep}.json").write_text(
                json.dumps(run), encoding="utf-8")


class TestPass3ReleaseGate:
    def test_given_every_rep_agrees_when_gated_then_the_release_is_allowed(self, tmp_path):
        """GIVEN a cohort where both tasks repeat one verdict across their three reps
        THEN the gate returns 0 and the pass^3 total counts every task."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1), "G2": (1, 1, 1)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        assert result["exit"] == gate.RELEASE_OK, result["reasons"]
        assert result["pass3"] == "2/2", result["pass3"]

    def test_given_a_task_that_flips_between_reps_when_gated_then_the_release_is_blocked(self, tmp_path):
        """GIVEN one task that passes two reps and fails the third
        THEN the gate returns 1 and names it, which is the block this hook exists for."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 0), "T2": (1, 1, 1)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        assert result["exit"] == gate.BLOCKED, result["reasons"]
        assert result["facts"]["flaky"] == ["T1"], result["facts"]
        assert any("T1" in reason for reason in result["reasons"]), result["reasons"]

    def test_given_a_task_that_fails_every_rep_when_gated_then_it_is_not_a_flake(self, tmp_path):
        """GIVEN a task that fails all three reps beside a clean one
        THEN the gate returns 0: a consistent fail is a capability fact, and only a flip is a flake."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (0, 0, 0), "T2": (1, 1, 1)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        assert result["exit"] == gate.RELEASE_OK, result["reasons"]
        assert result["facts"]["fail"] == ["T1"] and result["facts"]["flaky"] == [], result["facts"]
        assert result["pass3"] == "1/2", result["pass3"]

    def test_given_a_task_missing_a_rep_when_gated_then_the_gate_is_untrusted(self, tmp_path):
        """GIVEN a task with two of its three reps on disk
        THEN the gate returns 2, because pass^3 cannot be stated from a short rep set."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        assert result["exit"] == gate.UNTRUSTED, result["reasons"]
        assert result["facts"]["incomplete"] == ["T1"], result["facts"]

    def test_given_an_engine_blocked_rep_when_gated_then_it_is_not_read_as_a_flake(self, tmp_path):
        """GIVEN a task whose third rep the engine never answered
        THEN it is blocked and excluded, so the gate returns 0 rather than calling it a flip."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)}, engine_rep={("T1", 3)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        assert result["exit"] == gate.RELEASE_OK, result["reasons"]
        assert result["facts"]["blocked"] == ["T1"] and result["facts"]["flaky"] == [], result["facts"]

    def test_given_no_manifests_when_gated_then_the_gate_cannot_see(self, tmp_path):
        """GIVEN an empty runs directory
        THEN the gate returns 2 and names where to point it, the house rule for a blind gate."""
        gate = _release_gate()
        result = gate.gate(tmp_path / "empty", engine_cfg=API_ENGINE)
        assert result["exit"] == gate.UNTRUSTED, result
        assert "no rep manifests" in result["reasons"][0], result["reasons"]

    def test_given_a_local_engine_when_gated_then_the_release_number_is_refused(self, tmp_path):
        """GIVEN a clean cohort scored on a loopback runtime
        THEN the gate returns 2: a local engine describes one machine, so it cannot carry the number."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        result = gate.gate(runs, engine_cfg=LOCAL_ENGINE)
        assert result["exit"] == gate.UNTRUSTED, result["reasons"]
        assert any("local engine" in reason for reason in result["reasons"]), result["reasons"]

    def test_given_the_api_engine_when_the_receipt_is_built_then_the_engine_is_named(self, tmp_path):
        """GIVEN a clean cohort and the persisted API engine
        THEN the receipt carries provider, model and host, its decision is release-ok, and no key lands in it."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        receipt = gate.build_receipt(result, API_ENGINE, "~/.ephe/engine.json", task="W3-59")
        assert receipt["decision"] == "release-ok" and receipt["exit"] == 0, receipt
        assert receipt["engine"]["model"] == "deepseek-v4", receipt["engine"]
        assert receipt["engine"]["host"] == "api.deepseek.com", receipt["engine"]
        assert "api_key" not in json.dumps(receipt).lower(), "the receipt carries no key"


def _write_stamp(runs_dir, *, engine_seen=None, engine_expected=None):
    """The bless stamp the way evals/bench_preflight.py writes it into a cohort's runs dir."""
    stamp = {}
    if engine_seen:
        stamp["engine_seen"] = engine_seen
        stamp["engine_series"] = engine_seen
        stamp["health"] = {"active_provider": engine_seen.split("/")[0],
                           "active_model": engine_seen.split("/", 1)[1]}
    if engine_expected:
        stamp["engine_expected"] = engine_expected
    (runs_dir / "preflight.json").write_text(json.dumps(stamp), encoding="utf-8")


def _write_point(runs_dir, engine, model):
    """The point evals/bench_trend.py --out scores a cohort into."""
    (runs_dir / "point.json").write_text(
        json.dumps([{"ts": "2026-10-12T01:51:56", "engine": engine, "model": model}]),
        encoding="utf-8")


class TestPass3ReleaseGateEngineProvenance:
    """The number names the engine that measured it, read from the cohort, never from this box."""

    def test_given_a_cohort_whose_engine_matches_when_gated_then_the_release_is_allowed(self, tmp_path):
        """GIVEN a clean cohort whose stamp and point.json name the configured engine
        THEN the gate returns 0 and records the cohort's engine as a match."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1), "T2": (1, 1, 1)})
        _write_stamp(runs, engine_seen="openai_compatible/deepseek-v4",
                     engine_expected="openai_compatible/deepseek-v4")
        _write_point(runs, "openai_compatible", "deepseek-v4")
        result = gate.gate(runs, engine_cfg=API_ENGINE, engine_source="~/.ephe/engine.json")
        assert result["exit"] == gate.RELEASE_OK, result["reasons"]
        assert result["engine_agreement"] == "match", result["engine_agreement"]
        assert result["cohort_engine"] == "openai_compatible/deepseek-v4", result["cohort_engine"]
        receipt = gate.build_receipt(result, API_ENGINE, "~/.ephe/engine.json", task="W3-59")
        assert receipt["engine"]["cohort"]["agreement"] == "match", receipt["engine"]

    def test_given_a_cohort_measured_on_another_engine_when_gated_then_the_number_is_refused(self, tmp_path):
        """GIVEN a clean cohort the Spark measured while this machine's engine.json names the
        DeepSeek API THEN the gate returns 2 and refuses to stamp deepseek-v4 onto that cohort."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1), "T2": (1, 1, 1)})
        _write_stamp(runs, engine_seen="openai_compatible/qwen3.8-flash-next",
                     engine_expected="openai_compatible/qwen3.8-flash-next")
        _write_point(runs, "openai_compatible", "qwen3.8-flash-next")
        result = gate.gate(runs, engine_cfg=API_ENGINE, engine_source="~/.ephe/engine.json")
        assert result["exit"] == gate.UNTRUSTED, result["reasons"]
        assert result["facts"]["flaky"] == [], result["facts"]  # the cohort itself is clean
        assert any("engine mismatch" in reason for reason in result["reasons"]), result["reasons"]
        assert "qwen3.8-flash-next" in result["reasons"][0], result["reasons"]
        receipt = gate.build_receipt(result, API_ENGINE, "~/.ephe/engine.json", task="W3-59")
        assert receipt["engine"]["cohort"]["engine"] == "openai_compatible/qwen3.8-flash-next", receipt
        assert receipt["engine"]["cohort"]["agreement"] == "mismatch", receipt["engine"]

    def test_given_a_mismatch_and_a_recorded_reason_when_gated_then_it_is_carried_on_purpose(self, tmp_path):
        """GIVEN the same mismatched cohort and an explicit waiver reason
        THEN the gate returns 0, the receipt records the waiver, and both engines stay named."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        _write_point(runs, "openai_compatible", "qwen3.8-flash-next")
        reason = "kept on the Spark series; the DeepSeek config only names the chat engine"
        result = gate.gate(runs, engine_cfg=API_ENGINE, engine_source="~/.ephe/engine.json",
                           allow_engine_mismatch=reason)
        assert result["exit"] == gate.RELEASE_OK, result["reasons"]
        assert "engine mismatch" in result["engine_refusal"], result["engine_refusal"]
        assert result["engine_mismatch_waived"] == reason, result["engine_mismatch_waived"]
        receipt = gate.build_receipt(result, API_ENGINE, "~/.ephe/engine.json", task="W3-59")
        assert receipt["engine"]["cohort"]["waived"] == reason, receipt["engine"]
        assert receipt["engine"]["model"] == "deepseek-v4", receipt["engine"]

    def test_given_a_cohort_with_no_engine_record_when_gated_then_the_receipt_says_so(self, tmp_path):
        """GIVEN a clean cohort whose directory records no engine at all
        THEN the gate returns 0 and the receipt says the cohort carries no provenance."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        result = gate.gate(runs, engine_cfg=API_ENGINE)
        assert result["exit"] == gate.RELEASE_OK, result["reasons"]
        assert result["engine_agreement"] == "absent", result["engine_agreement"]
        assert result["cohort_engine"] == "", result["cohort_engine"]
        receipt = gate.build_receipt(result, API_ENGINE, "~/.ephe/engine.json", task="W3-59")
        assert receipt["engine"]["cohort"]["agreement"] == "absent", receipt["engine"]
        assert receipt["engine"]["cohort"]["engine"] == "", receipt["engine"]

    def test_given_one_cohort_naming_two_engines_when_gated_then_no_flag_waives_it(self, tmp_path):
        """GIVEN a stamp whose backend answered on one engine while its point.json names another
        THEN the gate returns 2 with the two-engines refusal, and a waiver does not lift it."""
        gate = _release_gate()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        _write_stamp(runs, engine_seen="openai_compatible/qwen3.8-flash-next")
        _write_point(runs, "openai_compatible", "deepseek-v4")
        result = gate.gate(runs, engine_cfg=API_ENGINE, allow_engine_mismatch="please")
        assert result["exit"] == gate.UNTRUSTED, result["reasons"]
        assert result["engine_agreement"] == "two-engines", result["engine_agreement"]
        assert result["engine_mismatch_waived"] is None, result["engine_mismatch_waived"]
        assert any("two runs wearing one label" in r for r in result["reasons"]), result["reasons"]
