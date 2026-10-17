"""E0: the kernel stub must not hand out tools that the approval gate protects.

`execute_code` sits in `SAFE_TOOLS` and therefore runs without a dialog. As long as
the `ephe_tools` stub passed through every registry function, the model
wrote its own acquittal: a single auto-run call (`from ephe_tools import
run_shell`) bypassed every gate — gate escalation became decoration.

The rule this test nails down: whatever runs inside the kernel without a dialog may only
be what the CLI also auto-approves without a dialog (`SAFE_TOOLS`). Everything else
answers with an action that points back to a real tool call, instead of showing
the effect.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from core.tools import code_kernel, registry


@pytest.fixture(autouse=True)
def _isolated_kernel(monkeypatch):
    """Fresh stub + empty kernel registry per test, the real registry untouched.

    Wave E1 routes `execute_code` into the CPython cell by default — these tests
    deal with the in-process kernel and its `ephe_tools` stub, so deliberately
    the opt-out path.
    """
    monkeypatch.setenv("EPHE_CODE_EXEC", "kernel")
    monkeypatch.setattr(code_kernel, "_EPHE_TOOLS_STUB", None)
    monkeypatch.delitem(sys.modules, "ephe_tools", raising=False)
    code_kernel._KERNELS.clear()
    yield
    code_kernel._KERNELS.clear()
    monkeypatch.undo()


@pytest.fixture
def spies(monkeypatch):
    """A sham registry: one SAFE tool and two gate-required ones, all with a call log."""
    calls: list[str] = []

    def get_datetime(fmt: str = "iso") -> str:
        calls.append(f"get_datetime:{fmt}")
        return "2026-10-02T12:00:00"

    def run_shell(command: str = "") -> str:
        calls.append(f"run_shell:{command}")
        return "pwned"

    def write_file(path: str = "", content: str = "") -> str:
        calls.append(f"write_file:{path}")
        return "written"

    monkeypatch.setattr(
        registry, "TOOL_MAP", {"get_datetime": get_datetime, "run_shell": run_shell, "write_file": write_file}
    )
    return calls


def _run(code: str) -> str:
    return asyncio.run(code_kernel.execute_code(code))


class TestKeinGateUmgehung:
    def test_gated_tool_call_is_refused_and_never_executes(self, spies):
        out = _run("from ephe_tools import run_shell\nprint(run_shell(command='echo pwned'))")
        assert spies == [], "run_shell wurde ausgeführt — das Approval-Gate ist umgangen"
        assert "pwned" not in out
        # The refusal must be an action, not noise.
        assert "run_shell" in out
        assert "tool_call" in out or "directly" in out.lower()

    def test_mutating_tool_reachable_by_name_is_also_refused(self, spies):
        out = _run("from ephe_tools import write_file\nprint(write_file(path='/tmp/x', content='y'))")
        assert spies == []
        assert "written" not in out
        assert "write_file" in out

    def test_meta_router_tool_call_follows_the_same_rule(self, spies):
        out = _run("import ephe_tools\nprint(ephe_tools.tool_call('run_shell', command='echo pwned'))")
        assert spies == []
        assert "pwned" not in out
        assert "run_shell" in out


class TestComputeAffordanceBleibt:
    def test_safe_tools_stay_callable_in_one_turn(self, spies):
        out = _run("from ephe_tools import get_datetime\nprint(get_datetime(fmt='iso'))")
        assert spies == ["get_datetime:iso"]
        assert "2026-10-02T12:00:00" in out

    def test_exposed_names_are_exactly_the_auto_approved_ones(self, spies):
        out = _run("import ephe_tools\nprint(sorted(ephe_tools.TOOL_NAMES))")
        assert "get_datetime" in out
        assert "run_shell" not in out and "write_file" not in out

    def test_unknown_tool_is_still_unknown(self, spies):
        out = _run("import ephe_tools\nprint(ephe_tools.tool_call('gibt_es_nicht'))")
        assert "unbekanntes Tool" in out

    def test_unknown_attribute_raises_instead_of_returning_none(self, spies):
        # A silent None would be a phantom tool; AttributeError is the honest answer.
        out = _run("import ephe_tools\nprint(ephe_tools.gibt_es_nicht)")
        assert "AttributeError" in out
