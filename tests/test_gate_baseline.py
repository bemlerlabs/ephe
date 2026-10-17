"""The frozen-baseline helper holds a wave's pre-existing reds apart from its own.

`scripts/gate_baseline.py` freezes each gate's verdict before a wave and re-reads it after, so a
red that was already there is not charged to the wave. These tests drive the helper two ways: the
status ladder and the comparison are called directly, and the two subcommands run as the real
script against stub gates whose exit codes the test controls.

A stub gate is a shell `exit`, its code read from a per-gate file, which makes `pass`, `fail` and
no-verdict reproducible with no instrument, checkout or network in the loop.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.subprocess_env import hermetic_env

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "gate_baseline.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("gate_baseline_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load_helper()


@pytest.mark.parametrize(
    ("code", "verdict"),
    [
        (0, "pass"),
        (1, "fail"),
        (2, "undecided"),
        (3, "fail"),
        (64, "fail"),
        (127, "fail"),
        (128, "undecided"),
        (130, "undecided"),
        (137, "undecided"),
    ],
)
def test_the_status_ladder_keeps_a_refusal_apart_from_no_verdict(code: int, verdict: str) -> None:
    assert helper.verdict_of(code) == verdict


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("pass", "pass", "green"),
        ("pass", "fail", "regressed"),
        ("fail", "pass", "recovered"),
        ("fail", "fail", "pre-existing"),
        ("pass", "undecided", "undecided"),
        ("fail", "undecided", "undecided"),
        ("undecided", "pass", "undecided"),
        ("undecided", "fail", "undecided"),
        ("undecided", "undecided", "undecided"),
    ],
)
def test_each_move_belongs_to_a_side(before: str, after: str, expected: str) -> None:
    assert helper.classify(before, after) == expected


def test_a_pre_existing_red_is_not_a_regression() -> None:
    classes, added, dropped = helper.compare(
        {"a": "pass", "b": "fail"}, {"a": ("pass", 0), "b": ("fail", 1)}
    )

    assert classes == {"a": "green", "b": "pre-existing"}
    assert added == [] and dropped == []


def test_a_gate_only_one_run_carried_is_uncompared_not_green() -> None:
    classes, added, dropped = helper.compare(
        {"a": "pass", "old": "fail"}, {"a": ("fail", 1), "new": ("pass", 0)}
    )

    assert classes == {"a": "regressed"}
    assert added == ["new"] and dropped == ["old"]


def test_the_builtin_registry_names_the_three_commit_gates() -> None:
    assert [gate["name"] for gate in helper.load_gates(None)] == ["architecture", "language", "prose"]


def test_a_snapshot_round_trips_through_the_frozen_shape(tmp_path: Path) -> None:
    path = tmp_path / "snap.json"
    verdicts = {"architecture": "pass", "language": "fail"}
    helper.write_snapshot(path, helper.snapshot_payload(verdicts, "abc1234", "wave-3"))

    frozen = helper.load_snapshot(path)

    assert frozen["gates"] == verdicts
    assert frozen["head"] == "abc1234"
    assert frozen["label"] == "wave-3"
    assert frozen["policy"] == helper.POLICY


def test_a_snapshot_from_a_foreign_policy_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "snap.json"
    helper.write_snapshot(path, helper.snapshot_payload({"x": "pass"}, None, None))
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["policy"] = "something-else"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(helper.GateError):
        helper.load_snapshot(path)


def test_a_missing_snapshot_is_refused(tmp_path: Path) -> None:
    with pytest.raises(helper.GateError):
        helper.load_snapshot(tmp_path / "absent.json")


def test_a_gate_without_a_command_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "gates.json"
    path.write_text(json.dumps({"gates": [{"name": "x"}]}), encoding="utf-8")

    with pytest.raises(helper.GateError):
        helper.load_gates(path)


STUB = '#!/bin/sh\nexit "$(cat "$1.code")"\n'


@pytest.fixture()
def wave(tmp_path: Path) -> dict[str, Any]:
    """A tree with one stub gate runner; a gate's code comes from `<name>.code` in that tree."""
    work = tmp_path / "tree"
    work.mkdir()
    runner = work / "gate.sh"
    runner.write_text(STUB, encoding="utf-8")
    runner.chmod(0o755)
    return {
        "work": work,
        "env": hermetic_env(HOME=str(tmp_path), PATH=os.environ.get("PATH", "")),
    }


def registry(work: Path, *names: str) -> Path:
    path = work / "gates.json"
    path.write_text(
        json.dumps({"gates": [{"name": n, "command": ["sh", "gate.sh", n]} for n in names]}),
        encoding="utf-8",
    )
    return path


def set_code(work: Path, name: str, code: int) -> None:
    (work / f"{name}.code").write_text(f"{code}\n", encoding="utf-8")


def run(wave: dict[str, Any], *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        cwd=str(wave["work"]),
        env=wave["env"],
        capture_output=True,
        text=True,
        check=False,
    )


def freeze(wave: dict[str, Any], gates: Path, snap: Path) -> subprocess.CompletedProcess[str]:
    return run(wave, "freeze", "--out", str(snap), "--gates-file", str(gates), "--root", str(wave["work"]))


def attribute(wave: dict[str, Any], gates: Path, snap: Path) -> subprocess.CompletedProcess[str]:
    return run(wave, "attribute", "--baseline", str(snap), "--gates-file", str(gates), "--root", str(wave["work"]))


def test_a_pre_existing_red_does_not_refuse_the_wave(wave: dict[str, Any]) -> None:
    gates = registry(wave["work"], "alpha", "beta")
    snap = wave["work"] / "snap.json"
    set_code(wave["work"], "alpha", 0)
    set_code(wave["work"], "beta", 1)
    assert freeze(wave, gates, snap).returncode == 0

    result = attribute(wave, gates, snap)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pre-existing beta: fail -> fail" in result.stdout
    assert "the baseline's red, not this wave" in result.stdout
    assert "0 regressed" in result.stdout
    assert "REGRESSED" not in result.stdout


def test_a_gate_that_flips_from_green_to_red_is_charged_to_the_wave(wave: dict[str, Any]) -> None:
    gates = registry(wave["work"], "alpha", "beta")
    snap = wave["work"] / "snap.json"
    set_code(wave["work"], "alpha", 0)
    set_code(wave["work"], "beta", 1)
    assert freeze(wave, gates, snap).returncode == 0
    set_code(wave["work"], "alpha", 1)
    set_code(wave["work"], "beta", 0)

    result = attribute(wave, gates, snap)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "REGRESSED alpha: pass -> fail" in result.stdout
    assert "recovered beta: fail -> pass" in result.stdout
    assert "REGRESSED beta" not in result.stdout


def test_a_gate_that_reaches_no_verdict_wins_over_a_red(wave: dict[str, Any]) -> None:
    gates = registry(wave["work"], "alpha", "gamma")
    snap = wave["work"] / "snap.json"
    set_code(wave["work"], "alpha", 0)
    set_code(wave["work"], "gamma", 0)
    assert freeze(wave, gates, snap).returncode == 0
    set_code(wave["work"], "alpha", 1)
    set_code(wave["work"], "gamma", 2)

    result = attribute(wave, gates, snap)

    assert result.returncode == 3, result.stdout + result.stderr
    assert "NO VERDICT gamma: pass -> undecided" in result.stdout
    assert "REGRESSED alpha: pass -> fail" in result.stdout


def test_a_snapshot_is_required_before_attribution(wave: dict[str, Any]) -> None:
    gates = registry(wave["work"], "alpha")
    set_code(wave["work"], "alpha", 0)

    result = attribute(wave, gates, wave["work"] / "never-frozen.json")

    assert result.returncode == 2
    assert "no snapshot at" in result.stderr


def test_a_gate_that_never_ran_freezes_as_undecided_not_pass(wave: dict[str, Any]) -> None:
    gates = wave["work"] / "gates.json"
    gates.write_text(
        json.dumps({"gates": [{"name": "ghost", "command": ["definitely-not-on-path-xyz"]}]}),
        encoding="utf-8",
    )
    snap = wave["work"] / "snap.json"

    frozen = freeze(wave, gates, snap)

    assert frozen.returncode == 0
    assert "ghost undecided (no exit)" in frozen.stdout
    assert "WARNING" in frozen.stdout
    assert attribute(wave, gates, snap).returncode == 3


def test_show_reads_the_snapshot_without_running_a_gate(wave: dict[str, Any]) -> None:
    gates = registry(wave["work"], "alpha")
    snap = wave["work"] / "snap.json"
    set_code(wave["work"], "alpha", 0)
    assert freeze(wave, gates, snap).returncode == 0
    set_code(wave["work"], "alpha", 1)

    result = run(wave, "show", "--baseline", str(snap))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "alpha" in result.stdout
    assert "pass" in result.stdout
