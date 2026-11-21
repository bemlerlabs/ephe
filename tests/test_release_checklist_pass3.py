"""The checklist's `pass3-gate` line must read the gate's exit codes with the gate's own words.

`scripts/release_checklist.py` is the only caller that runs the pass^3 gate *with* its engine
check (`.github/workflows/release.yml` runs the gate with `--no-engine-check`, the flake arm
only). This pins that line's two jobs against the real gate: carry a deliberate engine mismatch
with a recorded reason, and report an instrument refusal (exit 2, untrusted) so a reader cannot
mistake it for a product failure (exit 1, blocked-flaky). The gate runs as a subprocess over
synthetic cohorts, so no engine is contacted and no clock is read.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_PATH = REPO_ROOT / "scripts" / "release_checklist.py"

# The release bar (a provider API engine) and the engine another cohort was measured on.
API_ENGINE = {"provider": "openai_compatible", "model": "deepseek-v4",
              "api_url": "https://api.deepseek.com/v1"}
OTHER_ENGINE = "openai_compatible/qwen3.8-flash-next"


def _checklist():
    """`scripts/release_checklist.py` loaded under a private name, so the import cannot collide."""
    spec = importlib.util.spec_from_file_location("_release_checklist_under_test", CHECKLIST_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_cohort(runs_dir: Path, outcome: dict) -> None:
    """One rep manifest per rep, named the way `evals/bench_option_b.py` names them."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    for task_id, oks in outcome.items():
        for rep, ok in enumerate(oks, start=1):
            run = {"task_id": task_id, "family": "tau", "rep": rep, "ok": bool(ok)}
            (runs_dir / f"{task_id.lower()}_r{rep}.json").write_text(
                json.dumps(run), encoding="utf-8")


def _write_point(runs_dir: Path, engine: str, model: str) -> None:
    """The point `evals/bench_trend.py --out` scores a cohort into — its engine record."""
    (runs_dir / "point.json").write_text(
        json.dumps([{"ts": "2026-10-12T01:51:56", "engine": engine, "model": model}]),
        encoding="utf-8")


def _write_engine(path: Path, cfg: dict) -> None:
    """The persisted engine this machine would stamp (`~/.ephe/engine.json`)."""
    path.write_text(json.dumps(cfg), encoding="utf-8")


class TestReleaseChecklistPass3Gate:
    def test_a_flip_reads_as_a_product_failure(self, tmp_path):
        """GIVEN a cohort whose task flips between its reps and an engine that matches this box
        THEN the line is FAIL and says blocked-flaky (exit 1) — a product flake, not a refusal."""
        module = _checklist()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 0)})
        _write_point(runs, "openai_compatible", "deepseek-v4")
        engine = tmp_path / "engine.json"
        _write_engine(engine, API_ENGINE)
        item = module.check_pass3_gate(REPO_ROOT, runs=str(runs), engine=str(engine))
        assert item.status == "FAIL", item.detail
        assert "blocked-flaky (exit 1)" in item.detail, item.detail
        assert "flipped" in item.detail, item.detail
        assert "refused the engine" not in item.detail, item.detail

    def test_a_deliberate_mismatch_carries_its_recorded_reason(self, tmp_path):
        """GIVEN a cohort measured on another engine and a recorded reason
        THEN the line is PASS, release-ok (exit 0), and the reason is in what the checklist writes."""
        module = _checklist()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        _write_point(runs, "openai_compatible", "qwen3.8-flash-next")
        engine = tmp_path / "engine.json"
        _write_engine(engine, API_ENGINE)
        reason = "kept on the Spark series; the DeepSeek config only names the chat engine"
        item = module.check_pass3_gate(REPO_ROOT, runs=str(runs), engine=str(engine),
                                       mismatch_reason=reason)
        assert item.status == "PASS", item.detail
        assert "release-ok (exit 0)" in item.detail, item.detail
        assert reason in item.detail, item.detail

    def test_a_mismatch_without_a_reason_reads_as_an_instrument_refusal(self, tmp_path):
        """GIVEN the same mismatched cohort and no reason
        THEN the line is FAIL, untrusted (exit 2), carrying the gate's own refusal: the engine
        that produced the number is not this machine's, which is not a flake."""
        module = _checklist()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        _write_point(runs, "openai_compatible", "qwen3.8-flash-next")
        engine = tmp_path / "engine.json"
        _write_engine(engine, API_ENGINE)
        item = module.check_pass3_gate(REPO_ROOT, runs=str(runs), engine=str(engine))
        assert item.status == "FAIL", item.detail
        assert "untrusted (exit 2)" in item.detail, item.detail
        assert "engine mismatch" in item.detail, item.detail
        assert "flipped" not in item.detail, item.detail

    def test_a_two_engine_cohort_cannot_be_waived(self, tmp_path):
        """GIVEN a cohort whose stamp and point name two engines, and a reason offered anyway
        THEN the reason is not carried and the line stays an untrusted refusal — no silent bypass."""
        module = _checklist()
        runs = tmp_path / "runs"
        _write_cohort(runs, {"T1": (1, 1, 1)})
        _write_point(runs, "openai_compatible", "deepseek-v4")
        (runs / "preflight.json").write_text(
            json.dumps({"engine_seen": OTHER_ENGINE, "engine_series": OTHER_ENGINE}),
            encoding="utf-8")
        engine = tmp_path / "engine.json"
        _write_engine(engine, API_ENGINE)
        reason = "zqz-carried-on-purpose-marker"
        item = module.check_pass3_gate(REPO_ROOT, runs=str(runs), engine=str(engine),
                                       mismatch_reason=reason)
        assert item.status == "FAIL", item.detail
        assert "untrusted (exit 2)" in item.detail, item.detail
        assert "two runs wearing one label" in item.detail, item.detail
        assert reason not in item.detail, item.detail
