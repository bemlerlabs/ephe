"""tests/test_bench_gate_switch.py — the EPHE_BENCH_GATE=0 switch actually skips.

Pinned OUTSIDE tests/test_bench_gates.py on purpose: that file's `pytestmark` is derived
from the very constant under test, so a test living inside it would be skipped in exactly
the case it has to prove. Nothing here measures performance, so nothing here is gated.

The defect: `get(X) or get(X, "1") != "0"` returned the raw STRING "0" from the first
operand whenever the variable was set — and "0" is truthy. So the documented debugging
switch (docs/CLI_ROADMAP.md: "EPHE_BENCH_GATE=0 to skip while debugging") never skipped
anything: measured before the fix, `EPHE_BENCH_GATE=0` gave `3 passed`.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from tests.subprocess_env import hermetic_env, python_path_for

REPO = Path(__file__).resolve().parents[1]
GATED_FILE = REPO / "tests" / "test_bench_gates.py"


def _gate_state(monkeypatch, value):
    """Re-import the gated module with EPHE_BENCH_GATE under `value` and report its switch.

    A fresh module name per call: the real suite already holds `tests.test_bench_gates`
    in sys.modules, and reusing that name would hand back the first import's answer.
    """
    if value is None:
        monkeypatch.delenv("EPHE_BENCH_GATE", raising=False)
    else:
        monkeypatch.setenv("EPHE_BENCH_GATE", value)
    name = f"_bench_gates_under_test_{abs(hash(str(value)))}"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, GATED_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBenchGateSwitch:
    @pytest.mark.parametrize("value", [None, "1", "", "banana", "0 "])
    def test_given_any_value_but_zero_when_switch_read_then_gates_stay_on(self, monkeypatch, value):
        """GIVEN anything except exactly "0" — including no variable at all
        THEN the gates are enabled: a perf gate that defaults to off is no gate."""
        module = _gate_state(monkeypatch, value)
        assert module.BENCH_GATE_ENABLED is True

    @pytest.mark.parametrize("value", ["0"])
    def test_given_zero_when_switch_read_then_gates_are_off(self, monkeypatch, value):
        """GIVEN the documented debugging value
        THEN the switch is a bool and it says off — today it said the string "0",
        which is truthy, so `not BENCH_GATE_ENABLED` never skipped."""
        module = _gate_state(monkeypatch, value)
        assert module.BENCH_GATE_ENABLED is False

    def test_given_zero_when_pytest_runs_the_gated_file_then_it_skips(self):
        """GIVEN EPHE_BENCH_GATE=0 for a real pytest run
        THEN the four tolerance gates skip instead of measuring.

        A subprocess, because the skip decision is made by pytest from the module-level
        marker at collection time — the only end-to-end proof that the switch works."""
        run = subprocess.run(
            [sys.executable, "-m", "pytest", str(GATED_FILE), "-q", "-rs", "-p", "no:cacheprovider"],
            capture_output=True,
            text=True,
            timeout=180,
            env=hermetic_env(
                PATH="/usr/bin:/bin:/usr/local/bin",
                HOME=str(Path.home()),
                # The scrubbed env may not change what the interpreter can already import:
                # without the parent's own pytest root the child answers `No module named
                # pytest` and this test measures the machine, not the switch.
                PYTHONPATH=python_path_for("pytest"),
                EPHE_BENCH_GATE="0",
            ),
        )
        assert run.returncode == 0, run.stdout + run.stderr
        assert "4 skipped" in run.stdout, run.stdout[-800:]
        assert "EPHE_BENCH_GATE=0" in run.stdout, "the skip has to name the switch"
