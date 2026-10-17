"""Ephe — the coverage floor is a per-module ratchet over a committed baseline.

`docs/COVERAGE_GAPS_2026-10-11.md` measures where the suite is thin; a measurement a
human reads is a wish. `scripts/coverage_floor.py` turns it into a gate: a coverage.py
JSON report is grouped into modules, each module is compared against its floor in
`scripts/coverage-floor-baseline.json`, and a module that falls below its floor fails
the pass — the module is named, not averaged into a total.

The floors rise and never fall (`--update` refuses to lower a floor), which is the
inverse of the prose ratchet: there more is worse, here more is better. These tests
drive the gate with an injected report and a `tmp_path` baseline, so no coverage run,
no pytest-cov and no git checkout is involved — the instrument is scored on the numbers
a report carries, exactly the shape `--cov-report=json` writes.

Given / When / Then, strictly.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE_PATH = REPO / "scripts" / "coverage_floor.py"
COMMITTED = REPO / "scripts" / "coverage-floor-baseline.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("coverage_floor_under_test", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


# Fixtures


def report(files: dict[str, tuple[int, int]]) -> dict:
    """A coverage.py report body: path -> (covered_lines, num_statements)."""
    return {
        "meta": {"format": 3},
        "files": {
            rel: {"summary": {"covered_lines": c, "num_statements": n}}
            for rel, (c, n) in files.items()
        },
    }


def write_baseline(path: Path, modules: dict[str, int], total: int, **extra) -> Path:
    payload: dict = {"policy": gate.POLICY, "version": gate.VERSION, "total": total,
                     "modules": modules}
    payload.update(extra)
    path.write_text(json.dumps(payload, sort_keys=True, indent=1), encoding="utf-8")
    return path


def run(tmp_path: Path, baseline: Path, body: dict, *flags: str) -> int:
    return gate.main(
        ["--baseline", str(baseline), "--report", str(tmp_path / "coverage.json"), *flags],
        read_report_fn=lambda: body,
    )


# The instrument: grouping and rounding


def test_two_level_grouping_keeps_a_package_and_splits_a_subpackage():
    assert gate.module_of("core/chat.py") == "core"
    assert gate.module_of("core/tools/registry.py") == "core/tools"
    assert gate.module_of("ephe_cli.py") == "ephe_cli.py"


def test_coverage_is_statement_weighted_not_the_mean_of_file_rates():
    # A 3-line file at 0% with a 97-line file at 100%: the module rate is 97%, never 50%.
    body = report({"core/big.py": (97, 97), "core/small.py": (0, 3)})
    measured = gate.measure(body)
    assert measured["core"] == (97, 100)
    assert gate.percents(measured)["core"] == 97.0


def test_floor_is_the_measured_rate_floored_never_rounded_up():
    measured = {"core": (829, 1000)}
    assert gate.floors(gate.percents(measured)) == {"core": 82}


def test_a_module_with_no_statements_counts_as_full():
    body = report({"core/__init__.py": (0, 0)})
    assert gate.percents(gate.measure(body))["core"] == 100.0


# The gate


def test_a_module_that_falls_below_its_floor_fails_and_is_named(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core/tools": 83}, total=83)
    body = report({"core/tools/registry.py": (810, 1000)})  # 81%
    assert run(tmp_path, path, body) == 1
    out = capsys.readouterr().out
    assert "core/tools" in out
    assert "--update only ever raises" in out


def test_a_module_at_or_above_its_floor_passes(tmp_path):
    path = write_baseline(tmp_path / "b.json", {"core/tools": 83}, total=83)
    body = report({"core/tools/registry.py": (835, 1000)})  # 83.5% -> 83
    assert run(tmp_path, path, body) == 0


def test_the_floor_slack_absorbs_sub_point_noise(tmp_path):
    # Measured 82.9% against a floor of 82 is not a regression: the floor rounds down.
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    body = report({"core/chat.py": (829, 1000)})
    assert run(tmp_path, path, body) == 0


def test_a_new_module_absent_from_the_baseline_is_not_a_regression(tmp_path):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    body = report({"core/chat.py": (82, 100), "core/new/thing.py": (0, 50)})
    assert run(tmp_path, path, body) == 0


def test_a_total_that_rose_does_not_mask_a_module_that_fell(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82, "server": 80}, total=81)
    body = report({"core/chat.py": (95, 100), "server/app.py": (75, 100)})
    assert run(tmp_path, path, body) == 1
    assert "server" in capsys.readouterr().out


# The ratchet: --update only ever raises


def test_update_creates_the_baseline_from_the_report(tmp_path):
    path = tmp_path / "b.json"
    body = report({"core/chat.py": (83, 100), "server/app.py": (61, 100)})
    assert run(tmp_path, path, body, "--update") == 0
    written = json.loads(path.read_text())
    assert written["modules"] == {"core": 83, "server": 61}


def test_update_refuses_to_lower_a_floor_and_leaves_the_baseline_untouched(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core/tools": 83}, total=83)
    before = path.read_text()
    body = report({"core/tools/registry.py": (700, 1000)})  # 70%, a real drop
    assert run(tmp_path, path, body, "--update") == 1
    assert path.read_text() == before
    assert "only raises" in capsys.readouterr().err


def test_update_raises_a_floor_when_coverage_improved(tmp_path):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body, "--update") == 0
    assert json.loads(path.read_text())["modules"] == {"core": 90}


def test_update_prunes_a_module_the_report_no_longer_holds(tmp_path):
    path = write_baseline(tmp_path / "b.json", {"core": 82, "core/gone": 50}, total=66)
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body, "--update") == 0
    assert json.loads(path.read_text())["modules"] == {"core": 90}


# Refusals: the gate cannot be trusted


def test_an_entry_for_a_module_the_report_does_not_hold_is_refused(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82, "core/ghost": 50}, total=66)
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body) == 2
    assert "core/ghost" in capsys.readouterr().err


def test_a_baseline_floor_outside_zero_to_hundred_is_refused(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 120}, total=120)
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body) == 2
    assert "between 0 and 100" in capsys.readouterr().err


def test_a_baseline_with_an_unknown_key_is_refused(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82, exempt=["core"])
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body) == 2
    assert "no exemption list" in capsys.readouterr().err


def test_a_baseline_for_another_policy_is_refused(tmp_path, capsys):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"policy": "language-ratchet", "version": 1,
                                "total": 82, "modules": {"core": 82}}), encoding="utf-8")
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body) == 2
    assert "policy" in capsys.readouterr().err


def test_a_report_without_a_files_mapping_is_refused(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    assert run(tmp_path, path, {"meta": {"format": 3}}) == 2
    assert "files" in capsys.readouterr().err


def test_a_report_entry_missing_its_summary_is_refused(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    body = {"files": {"core/chat.py": {"executed_lines": [1, 2]}}}
    assert run(tmp_path, path, body) == 2
    assert "summary" in capsys.readouterr().err


def test_a_report_entry_covering_more_than_it_holds_is_refused(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    body = report({"core/chat.py": (200, 100)})
    assert run(tmp_path, path, body) == 2
    assert "more lines than it holds" in capsys.readouterr().err


# The committed baseline the CI leg reads


def test_the_committed_baseline_loads_and_is_shaped_like_what_the_instrument_writes():
    modules, total = gate.load_baseline(COMMITTED)
    assert modules, "the committed baseline must carry at least one module"
    assert all(isinstance(name, str) and 0 <= floor <= 100 for name, floor in modules.items())
    assert 0 <= total <= 100
    raw = json.loads(COMMITTED.read_text())
    assert raw["instrument"] == gate.INSTRUMENT
    assert raw["policy"] == gate.POLICY and raw["version"] == gate.VERSION


def test_the_committed_baseline_passes_against_a_report_built_from_its_own_floors(tmp_path):
    # A report whose every module measures exactly its committed floor must pass, and
    # must report no room to raise: the instrument and the file agree at their fixed point.
    modules, _ = gate.load_baseline(COMMITTED)
    body = report({f"{name}/mod.py": (floor, 100) for name, floor in modules.items()})
    assert run(tmp_path, COMMITTED, body) == 0


# The operator's two paths: room to raise, and a missing report


def test_a_module_above_its_floor_passes_and_offers_to_raise_the_baseline(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    body = report({"core/chat.py": (90, 100)})
    assert run(tmp_path, path, body) == 0
    assert "can be raised" in capsys.readouterr().out


def test_a_missing_report_file_is_refused_with_the_command_that_makes_one(tmp_path, capsys):
    path = write_baseline(tmp_path / "b.json", {"core": 82}, total=82)
    code = gate.main(["--baseline", str(path), "--report", str(tmp_path / "coverage.json")])
    assert code == 2
    assert "no coverage report" in capsys.readouterr().err

