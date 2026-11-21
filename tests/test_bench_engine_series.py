"""The trend's engine series: one series per engine, and a DeepSeek run starts its own.

The 2026-10-12 decision moves the measurement off the Spark to DeepSeek over the API. The
persisted ``~/.ephe/engine.json`` stays the owner's chat engine, so the engine that measures
is named by the override env — and a point measured on another engine is a *different
series*, not the next row of the same one. These tests run in-process (a spawned interpreter
is the failure class ``tests/test_port_squatter_guard.py`` documents on shared runners).
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

#: A manifest as the harness writes it now. Fixed values: the gate compares them against
#: each other rather than against this repository.
ADDRESS = {"commit": "c" * 40, "commit_short": "ccccccc",
           "surface": {"core": "a" * 40, "server": "b" * 40},
           "surface_sha": "s" * 40, "dirty": []}

SPARK = {"provider": "openai_compatible", "model": "qwen3.8-flash-next"}
DEEPSEEK = {"provider": "openai_compatible", "model": "deepseek-v4-pro"}


def _trend():
    name = "_bench_trend_under_series_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_trend.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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


def _deepseek_env(monkeypatch):
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", DEEPSEEK["provider"])
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", DEEPSEEK["model"])
    return f"{DEEPSEEK['provider']}/{DEEPSEEK['model']}"


def _seed(out: Path, engine: dict) -> None:
    """A file already carrying one point of an earlier engine's series."""
    out.write_text(json.dumps([{"ts": "2026-10-11T01:05:46", "commit": "9d6efcd1",
                                "engine": engine["provider"], "model": engine["model"],
                                "series": f"{engine['provider']}/{engine['model']}",
                                "by_family": {}, "n_tasks_effective": 60,
                                "matrix_tasks": 60, "reps_total": 180}]), encoding="utf-8")


def _main(monkeypatch, tmp_path, out, extra=()):
    monkeypatch.setattr(sys, "argv", ["bench_trend", "--runs", str(tmp_path / "runs"),
                                      "--out", str(out), "--ts", "2026-10-12T06:00:00",
                                      *extra])
    return _trend().main()


def test_the_env_override_names_the_measurement_engine(monkeypatch):
    trend = _trend()
    engine = _deepseek_env(monkeypatch)
    assert trend._engine_meta() == (DEEPSEEK["provider"], DEEPSEEK["model"], "env")
    assert engine == "openai_compatible/deepseek-v4-pro"


def test_the_persisted_config_is_only_the_fallback(monkeypatch):
    # No override env: the label falls back to ~/.ephe/engine.json, never to the override
    trend = _trend()
    assert trend._engine_meta()[2] != "env"


def test_a_point_declares_the_series_it_belongs_to():
    trend = _trend()
    point = trend.compute_point([], ts="t", commit="c",
                                engine=DEEPSEEK["provider"], model=DEEPSEEK["model"])
    assert point["series"] == "openai_compatible/deepseek-v4-pro"
    # A point written before the field existed still derives its series from engine/model
    assert trend._series_of({"engine": "openai_compatible", "model": "qwen3.8-flash-next"}) \
        == "openai_compatible/qwen3.8-flash-next"


def test_a_second_engine_may_not_join_the_same_file(tmp_path, monkeypatch, capsys):
    # Given a file holding the Spark series, a DeepSeek point arrives
    trend = _trend()
    _deepseek_env(monkeypatch)
    _write_runs(tmp_path / "runs", FULL_IDS)
    out = tmp_path / "trend.json"
    _seed(out, SPARK)
    before = out.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, tmp_path, out)
    err = capsys.readouterr().err
    # Then mixing is refused and both series are named
    assert exc.value.code == 2
    assert out.read_text(encoding="utf-8") == before, "a refused point must not reach the file"
    assert "openai_compatible/deepseek-v4-pro" in err
    assert "openai_compatible/qwen3.8-flash-next" in err
    assert "--allow-engine-series" in err


def test_a_first_point_of_a_new_engine_appends_to_its_own_file(tmp_path, monkeypatch):
    # Given a fresh file (the DeepSeek run's own series) and the override env
    trend = _trend()
    engine = _deepseek_env(monkeypatch)
    _write_runs(tmp_path / "runs", FULL_IDS)
    out = tmp_path / "trend-deepseek.json"
    _main(monkeypatch, tmp_path, out)
    point = json.loads(out.read_text(encoding="utf-8"))[-1]
    # Then the point is appended and it says which series it is
    assert point["series"] == engine
    assert point["engine_source"] == "env"
    assert point["n_tasks_effective"] == 60


def test_two_engines_in_one_file_need_a_recorded_reason(tmp_path, monkeypatch, capsys):
    trend = _trend()
    _deepseek_env(monkeypatch)
    _write_runs(tmp_path / "runs", FULL_IDS)
    out = tmp_path / "trend.json"
    _seed(out, SPARK)
    _main(monkeypatch, tmp_path, out, ("--allow-engine-series", "carrying both on purpose"))
    point = json.loads(out.read_text(encoding="utf-8"))[-1]
    assert point["engine_series_reason"] == "carrying both on purpose"
    assert "--allow-engine-series" in point["comparability"]


def test_the_render_marks_where_the_series_breaks():
    trend = _trend()
    spark = trend.compute_point([], ts="1", commit="a", engine=SPARK["provider"],
                                model=SPARK["model"])
    deepseek = trend.compute_point([], ts="2", commit="b", engine=DEEPSEEK["provider"],
                                   model=DEEPSEEK["model"])
    table = trend._render([spark, deepseek])
    assert table.count("new series") == 1
    assert "new series (openai_compatible/deepseek-v4-pro)" in table
