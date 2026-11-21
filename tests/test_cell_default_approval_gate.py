"""W3-15: cell-by-default for model code, the approval gate in front of the rest.

The decision (docs/SANDBOX_EXECUTION.md) in one sentence: the cell is the default
execution for LLM-written Python, and the cell is what earns ``execute_code`` its
auto-run — where a pinned cell cannot carry the run (``EPHE_CODE_EXEC=kernel`` or
a machine with no guest), the same code executes on the host, so it passes the
same approval gate as ``run_shell``.

Before this, ``execute_code`` sat unconditionally in ``SAFE_TOOLS``; a fresh
install (no guest) therefore ran model Python with full host access and no
dialog, and flipping one byte in ``python.wasm`` silently made execution
unsandboxed *and* auto-approved (the coupling the E1 doc named and left open).
"""
from __future__ import annotations

import asyncio

import pytest

from core import cpython_cell
from core.tools import approval
from core.tools.approval import ApprovalPolicy, classify_tool, request_approval


# containment probe == the runtime decision

@pytest.mark.parametrize("choice", [None, "", "kernel", "cell", "banana"])
def test_uncontained_equals_kernel_runtime(monkeypatch, choice):
    """``code_runs_uncontained()`` must be exactly ``exec_runtime() == KERNEL``.

    If the two disagree the gate guards a path the runner does not take (or the
    other way round) — the report-vs-enforced split the cell policy forbids.
    """
    monkeypatch.setattr(cpython_cell, "guest_installed", lambda: True)
    monkeypatch.delenv(cpython_cell.ENV_EXEC, raising=False)
    if choice is not None:
        monkeypatch.setenv(cpython_cell.ENV_EXEC, choice)
    assert cpython_cell.code_runs_uncontained() == (
        cpython_cell.exec_runtime() == cpython_cell.RUNTIME_KERNEL
    )


@pytest.mark.parametrize("choice", [None, "kernel", "cell"])
def test_uncontained_without_a_guest(monkeypatch, choice):
    # A machine without a guest: both the ready probe and the install probe are off
    # (in reality cell_ready() implies guest_installed(); patch both so the simulated
    # state is the real one, not an impossible mix).
    monkeypatch.setattr(cpython_cell, "guest_installed", lambda: False)
    monkeypatch.setattr(cpython_cell, "cell_ready", lambda: False)
    monkeypatch.delenv(cpython_cell.ENV_EXEC, raising=False)
    if choice is not None:
        monkeypatch.setenv(cpython_cell.ENV_EXEC, choice)
    assert cpython_cell.code_runs_uncontained() == (
        cpython_cell.exec_runtime() == cpython_cell.RUNTIME_KERNEL
    )


# classification follows the runtime

def test_contained_execute_code_is_safe(monkeypatch):
    monkeypatch.setattr(cpython_cell, "guest_installed", lambda: True)
    monkeypatch.delenv(cpython_cell.ENV_EXEC, raising=False)
    cls = classify_tool("execute_code")
    assert cls.category == "SAFE"
    assert cls.is_mutating is False and cls.auto_approve_by_default is True
    assert approval.chat_tool_requires_confirm("execute_code") is False


def test_kernel_execute_code_is_mutating(monkeypatch):
    monkeypatch.setenv(cpython_cell.ENV_EXEC, cpython_cell.RUNTIME_KERNEL)
    cls = classify_tool("execute_code")
    assert cls.category == "MUTATING"
    assert cls.is_mutating is True and cls.auto_approve_by_default is False
    assert approval.chat_tool_requires_confirm("execute_code") is True


def test_other_tools_are_classified_by_name(monkeypatch):
    """The runtime probe must not leak into any other tool's class."""
    monkeypatch.setenv(cpython_cell.ENV_EXEC, cpython_cell.RUNTIME_KERNEL)
    assert classify_tool("get_datetime").category == "SAFE"
    assert classify_tool("run_shell").category == "DANGEROUS"


def test_unreadable_runtime_is_fail_closed(monkeypatch):
    """A broken runtime read must not silently grant the auto-run."""
    def _boom():
        raise RuntimeError("runtime unreadable")

    monkeypatch.setattr(cpython_cell, "code_runs_uncontained", _boom)
    assert classify_tool("execute_code").is_mutating is True
    assert approval.chat_tool_requires_confirm("execute_code") is True


# the gate really stands in front

def test_cli_gate_denies_uncontained_without_yes(monkeypatch):
    monkeypatch.setenv(cpython_cell.ENV_EXEC, cpython_cell.RUNTIME_KERNEL)
    policy = ApprovalPolicy(auto_approve=False, interactive=False)
    decision = asyncio.run(request_approval("execute_code", {"code": "1+1"}, policy))
    assert decision.approved is False


def test_cli_gate_auto_approves_contained(monkeypatch):
    monkeypatch.setattr(cpython_cell, "guest_installed", lambda: True)
    monkeypatch.delenv(cpython_cell.ENV_EXEC, raising=False)
    policy = ApprovalPolicy(auto_approve=False, interactive=False)
    decision = asyncio.run(request_approval("execute_code", {"code": "1+1"}, policy))
    assert decision.approved is True


def test_chat_gate_denies_uncontained_without_a_channel(monkeypatch):
    from core.tools.chat_gate import confirm_for_chat

    monkeypatch.setenv(cpython_cell.ENV_EXEC, cpython_cell.RUNTIME_KERNEL)
    approved, denial = asyncio.run(confirm_for_chat("execute_code", {"code": "1+1"}))
    assert approved is False
    assert str(denial)


def test_chat_gate_runs_contained_without_a_channel(monkeypatch):
    from core.tools.chat_gate import confirm_for_chat

    monkeypatch.setattr(cpython_cell, "guest_installed", lambda: True)
    monkeypatch.delenv(cpython_cell.ENV_EXEC, raising=False)
    approved, denial = asyncio.run(confirm_for_chat("execute_code", {"code": "1+1"}))
    assert approved is True and denial == ""
