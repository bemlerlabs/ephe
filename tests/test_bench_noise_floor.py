"""The noise floor is arithmetic, so the arithmetic is pinned to hand-checkable values.

Every expectation below is a number that can be verified on paper: exact binomial
tails, a z-score worked out from the pooled standard error, and the monotonicity that
a sample-size table must have. Nothing here asserts a value the script invented.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    name = "_noise_floor_under_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "noise_floor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


floor = _load()


def test_normal_quantiles_are_the_standard_ones():
    assert floor.Z_ALPHA == round(1.959963984549679, 12) or abs(floor.Z_ALPHA - 1.959963984549679) < 1e-9
    assert abs(floor.Z_BETA - 0.8416212335729143) < 1e-9


def test_mcnemar_exact_tails():
    # b=6, c=0: n=6, P(X>=6) = 1/64, two-sided 2/64
    assert floor.mcnemar_exact(6, 0) == 2 / 64
    # b=8, c=2: n=10, P(X>=8) = (45+10+1)/1024, two-sided 112/1024
    assert floor.mcnemar_exact(8, 2) == 112 / 1024
    # b=7, c=1: n=8, (8+1)/256 doubled
    assert floor.mcnemar_exact(7, 1) == 18 / 256
    assert floor.mcnemar_exact(0, 0) == 1.0
    # a symmetric split is no evidence at all
    assert floor.mcnemar_exact(4, 4) == 1.0


def test_two_proportion_z_on_the_recorded_change():
    # 58/60 vs 52/60: pooled p = 0.91666.., se = sqrt(2*pq/60) = 0.050462, z = 1.9817
    z, p = floor.two_prop_z(0.9667, 0.8667, 60)
    assert abs(z - 1.9817) < 1e-3
    assert abs(p - 0.0476) < 1e-3


def test_power_increases_with_sample_and_delta():
    assert floor.power_at(0.9, 0.15, 150) > floor.power_at(0.9, 0.15, 60)
    assert floor.power_at(0.9, 0.20, 60) > floor.power_at(0.9, 0.10, 60)
    # required_n is the smallest n that reaches 80%, so the neighbour must miss it
    n = floor.required_n(0.9, 0.10)
    assert floor.power_at(0.9, 0.10, n) >= floor.POWER
    assert floor.power_at(0.9, 0.10, n - 1) < floor.POWER
    assert floor.required_n(0.9, 0.05) > floor.required_n(0.9, 0.10) > floor.required_n(0.9, 0.15)


def test_mdd_and_required_n_agree_in_both_directions():
    n = floor.required_n(0.87, 0.10)
    assert floor.mdd(0.87, n) <= 0.10 + 0.01
    assert floor.mdd(0.87, n - 20) > 0.10


def test_pass_k_is_the_metric_that_reps_actually_change():
    assert abs(floor.pass_k(0.95, 3) - 0.857375) < 1e-9
    assert floor.pass_k(1.0, 3) == 1.0
    assert floor.pass_k(0.5, 10) < floor.pass_k(0.5, 3)


def test_paired_range_over_the_unrecorded_overlap():
    # 58/60 -> 52/60: 2 then 8 tasks failing, so the overlap runs 0..2
    rows = floor.paired_range(58, 52, 60)
    assert [r[1:3] for r in rows] == [(8, 2), (7, 1), (6, 0)]
    assert min(r[3] for r in rows) == 2 / 64
    assert max(r[3] for r in rows) == 112 / 1024


def test_table_recomputes_the_stale_recorded_intervals():
    points = [
        {"ts": "t1", "commit": "a", "pass3_total": "46/50", "pass3_rate": 0.92,
         "pass3_wilson95": {"width": 0.3717}},
        {"ts": "t2", "commit": "b", "pass3_total": "52/60", "pass3_rate": 0.8667,
         "pass3_wilson95": {"width": 0.1725}},
        # a point from before `n_tasks_effective` was recorded still has its counts
        {"ts": "t3", "commit": "c", "pass3_total": "7/10", "pass3_rate": 0.7},
        {"ts": "t4", "commit": "d", "pass3_rate": 0.0},
    ]
    text = floor.table(points)
    assert "0.3717" in text and "0.1568 *(stale)*" in text
    assert "0.1725" in text and "0.1725 *(stale)*" not in text
    assert "| t3 | c | 10 | 7/10 | 0.7000 | - |" in text
    assert "| t4 | d | - |" in text


def test_verdict_text_names_the_gate_it_fails():
    text = floor.verdict(0.9667, 0.8667, 60)
    assert "significant at alpha=0.05" in text
    assert "so it fails" in text
    assert "the record cannot settle it" in text


def _trend():
    name = "_bench_trend_under_noise_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_trend.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _rep(task_id, rep, ok, error_class=None, family="tau"):
    return {"task_id": task_id, "family": family, "level": "L2", "rep": rep, "ok": ok,
            "error_class": error_class, "note": "", "wall_ms": 1000.0, "tool_calls": []}


def test_a_point_records_which_tasks_passed():
    # Without this the file stores only a count, and the paired test of the same matrix
    # measured twice degrades into a range over possible overlaps.
    point = _trend().compute_point(
        [_rep("T1", i, True) for i in (1, 2, 3)]
        + [_rep("T2", 1, True), _rep("T2", 2, True),
           _rep("T2", 3, False, "engine")]
        + [_rep("T3", 1, True), _rep("T3", 2, False), _rep("T3", 3, False)]
        + [_rep("G1", 1, True)],
        ts="2026-10-10T00:00:00", commit="abc", engine="openai_compatible", model="m",
    )
    assert point["task_verdicts"] == {"T1": "pass", "T2": "blocked", "T3": "fail",
                                      "G1": "incomplete"}


def test_compare_names_the_flips_and_returns_one_p():
    points = [
        {"commit": "a", "pass3_total": "2/3", "task_verdicts": {"T1": "pass", "T2": "pass", "T3": "fail"}},
        {"commit": "b", "pass3_total": "1/3", "task_verdicts": {"T1": "pass", "T2": "fail", "T3": "fail"}},
    ]
    out = floor.compare(points, "a", "b")
    assert "pairable tasks: 3 of 3" in out
    assert "newly failing (1): T2" in out
    assert "newly passing (0): -" in out
    # b=1, c=0 over one discordant pair is no evidence: 2 * P(X>=1 | n=1) = 1.0
    assert "p=1.0000" in out
    assert "not significant" in out


def test_compare_falls_back_to_the_range_without_verdicts():
    points = [
        {"commit": "a", "pass3_total": "58/60", "pass3_rate": 0.9667},
        {"commit": "b", "pass3_total": "52/60", "pass3_rate": 0.8667},
    ]
    out = floor.compare(points, "a", "b")
    assert "paired test stays a range" in out
    assert "overlap=0 b=8 c=2" in out and "overlap=2 b=6 c=0" in out


def _bench(monkeypatch):
    name = "_bench_option_under_public_test"
    sys.modules.pop(name, None)
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    monkeypatch.setenv("EPHE_BENCH_BASE", "http://127.0.0.1:1")
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_option_b.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run(task_id, rep, ok, cost=0.002, family="tau"):
    return {"task_id": task_id, "family": family, "level": "L2", "rep": rep, "ok": ok,
            "error_class": None if ok else "assertion", "note": "", "wall_ms": 1200.0,
            "tool_calls": [], "cost_usd": cost, "pricing_source": "engine.json"}


def test_a_point_carries_the_public_table_format():
    trend = _trend()
    runs = ([_run("T1", i, True) for i in (1, 2, 3)]
            + [_run("T2", 1, False), _run("T2", 2, True), _run("T2", 3, True)]
            + [_run("W1", i, True, family="endstate") for i in (1, 2, 3)])
    point = trend.compute_point(runs, ts="2026-10-10T00:00:00", commit="abc",
                                engine="openai_compatible", model="m")
    # 8 of 9 reps passed, but T2 loses at pass^3: the two axes measure different things
    assert point["pass1_rate"] == round(8 / 9, 4)
    assert point["pass3_rate"] == round(2 / 3, 4)
    assert point["trials"] == 3
    assert point["pass1_wilson95"]["n"] == 9
    # 9 reps at $0.002 = $0.018 over 3 counted tasks, 2 of them solved
    assert point["cost_usd"]["sum_total"] == 0.018
    assert point["cost_usd"]["per_task_attempted"] == 0.006
    assert point["cost_usd"]["per_task_solved"] == 0.009
    assert point["pricing_source"] == "engine.json"


def test_public_render_puts_the_interval_next_to_the_rate():
    trend = _trend()
    text = trend._render_public([
        {"engine": "openai_compatible", "model": "qwen3.8-flash-next", "trials": 3,
         "n_tasks_effective": 60, "pass1_rate": 0.9111,
         "pass1_wilson95": {"width": 0.0408}, "cost_usd": {"per_task_solved": 0.0034}},
        {"engine": "openai_compatible", "model": "old"},
    ])
    # their convention: a percentage with a half-width, not a bare fraction
    assert "91.1% ± 2.0" in text
    assert "0.0034" in text
    assert "| openai_compatible | old | - | - | - | - |" in text


def test_a_point_from_before_the_field_derives_its_single_trial_rate():
    trend = _trend()
    historic = {"engine": "openai_compatible", "model": "qwen3.8-flash-next",
                "reps_total": 180, "n_tasks_effective": 60,
                "error_histogram": {"assertion": 16}}
    assert trend._pass1_from_point(historic)[0] == round(164 / 180, 4)
    # blocked reps are not in reps_total, so they must not be counted as failures twice
    with_blocked = dict(historic, n_reps_blocked=18, error_histogram={"assertion": 16, "engine": 18})
    assert trend._pass1_from_point(with_blocked)[0] == round(164 / 180, 4)


def test_pricing_precedence_names_its_source(monkeypatch):
    bench = _bench(monkeypatch)
    monkeypatch.setenv("EPHE_BENCH_PRICE_IN_PER_M", "0.1")
    monkeypatch.setenv("EPHE_BENCH_PRICE_OUT_PER_M", "0.6")
    assert bench._resolve_pricing() == (0.1, 0.6, "env")
    # no env and no engine config under test: the fallback table is named in the source
    monkeypatch.delenv("EPHE_BENCH_PRICE_IN_PER_M")
    monkeypatch.delenv("EPHE_BENCH_PRICE_OUT_PER_M")
    p_in, p_out, source = bench._resolve_pricing()
    assert source in ("engine.json", "default", "openrouter-published")
    assert bench._published_openrouter_price("") is None


def test_the_matrix_size_is_parsed_and_not_imported():
    # Importing bench_option_b would probe the product server for its model
    assert _trend()._matrix_size() == 60


def test_a_partial_run_labels_its_own_denominator():
    # A 26-task endstate run is a legitimate measurement and an illegitimate trend row:
    # without this note it sits beside the 60-task points and reads like a fall.
    trend = _trend()
    point = trend.compute_point(
        [_rep(f"T{i}", r, True) for i in (1, 2) for r in (1, 2, 3)],
        ts="2026-10-10T00:00:00", commit="abc", engine="openai_compatible", model="m")
    assert point["n_tasks_effective"] == 2
    assert ("partial matrix: 2 of 60 tasks scored, 58 absent from these manifests"
            in point["comparability"])
