"""run_shell: real execution instead of the two-step throw (option-1 fix).

Root cause (live TUI): the model believed "tools were denied/blocked",
because (a) run_shell() only ever raised ShellConfirmationRequired (dead code in
the chat flow, since run_shell is handled inline in chat.py there) and
(b) the tool description told the model the command would "NOT be executed
automatically" — both wrong once the confirm prompt lives in the TUI.

Contract after the fix:
    - run_shell(command) executes the command (whitelist +
      blocked patterns as the second gate stay in
      execute_confirmed_shell).
    - approval stays OUTSIDE: execute_tool(policy=...) /
      chat_with_tools (inline path) decide before the execution.
    - commands off the whitelist → security message, no crash, no execution.
"""
from __future__ import annotations

import asyncio

import pytest

from core.tools.approval import ApprovalPolicy
from core.tools.registry import execute_tool


@pytest.mark.asyncio
async def test_run_shell_executes_whitelisted_command():
    """GIVEN run_shell is called with a whitelisted command
    THEN the command is EXECUTED and the output is returned
    (no more ShellConfirmationRequired)."""
    from core.tools.shell_tools import run_shell

    result = await run_shell("echo ok")
    assert "ok" in result


@pytest.mark.asyncio
async def test_run_shell_rejects_non_whitelisted_command():
    """GIVEN run_shell is called with a command off the whitelist
    THEN security message, NOT executed (the second gate stays)."""
    from core.tools.shell_tools import run_shell

    result = await run_shell("frobnicate --all")
    assert "whitelist" in result or "Security" in result


@pytest.mark.asyncio
async def test_run_shell_rejects_blocked_pattern():
    """GIVEN the run_shell command contains a blocked pattern (> /dev/)
    THEN the security message, and the tool never runs.

    'echo' is on the whitelist → the command first runs past the
    blocked-pattern gate and is stopped THERE (layer 2)."""
    from core.tools.shell_tools import run_shell

    result = await run_shell("echo hello > /dev/null")
    assert "Security" in result or "blocked" in result.lower()
    assert "hello" not in result  # the output must not get through


@pytest.mark.asyncio
async def test_execute_tool_run_shell_with_approval_gate_denied():
    """GIVEN execute_tool(run_shell) with a policy whose callback refuses
    THEN the approval report is returned and the tool never runs.

    (the approval gate stays intact — option 1 only changes the execution
    AFTER the approval; the gate itself is untouched.)"""
    from unittest.mock import AsyncMock

    policy = ApprovalPolicy(on_confirm=AsyncMock(return_value=False))
    result = await execute_tool(
        "run_shell", {"command": "echo SHOULD_NOT_RUN"}, policy=policy
    )
    assert "Denied" in result
    assert "SHOULD_NOT_RUN" not in result or "denied" in result.lower()


@pytest.mark.asyncio
async def test_execute_tool_run_shell_with_approval_gate_approved():
    """GIVEN execute_tool(run_shell) with a policy whose callback approves
    THEN the command is executed and the output is returned."""
    from unittest.mock import AsyncMock

    policy = ApprovalPolicy(on_confirm=AsyncMock(return_value=True))
    result = await execute_tool(
        "run_shell", {"command": "echo approved_ok"}, policy=policy
    )
    assert "approved_ok" in result


# I6 P1-5: cwd injection — the server-cwd/$HOME class pinned down
# The depth test (2026-09-08) observed run_shell running in $HOME. The cause was an
# unset workspace_dir (fallback to the server process cwd). These pins
# secure both branches for good: the configured workspace wins; only without
# it does the documented server-cwd fallback apply.

@pytest.mark.asyncio
async def test_confirmed_shell_runs_in_configured_workspace(tmp_path, monkeypatch):
    """GIVEN get_workspace_dir returns a configured project folder
    WHEN  execute_confirmed_shell('pwd', confirmed=True)
    THEN  subprocess.run receives exactly that path as cwd (not the server cwd)."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import core.engine_config as ec
    import core.security_config as sc
    from core.tools.shell_tools import execute_confirmed_shell

    ws = tmp_path / "projekt"
    ws.mkdir()
    monkeypatch.setattr(ec, "get_workspace_dir", lambda: str(ws.resolve()))
    monkeypatch.setattr(sc, "load_security_config", lambda: SimpleNamespace(sandbox_enabled=False))

    captured: dict = {}

    class _FakeProc:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.pid = 4242
            self.returncode = 0

        def communicate(self, input=None, timeout=None):
            return "ok\n", ""

    def fake_popen(*args, **kwargs):
        return _FakeProc(*args, **kwargs)

    import subprocess as subprocess_module
    import core.tools._shell_proc as shell_tools_module
    monkeypatch.setattr(shell_tools_module, "subprocess",
                        SimpleNamespace(Popen=fake_popen, PIPE=-1,
                                        CompletedProcess=subprocess_module.CompletedProcess,
                                        TimeoutExpired=subprocess_module.TimeoutExpired))

    out = await execute_confirmed_shell("pwd", confirmed=True)

    assert captured.get("cwd") == str(ws.resolve())
    assert "ok" in out


def test_workspace_dir_fallback_is_documented_server_cwd(monkeypatch, tmp_path):
    """GIVEN engine.json without a valid workspace_dir and a server started
    outside the Ephe tree
    WHEN  get_workspace_dir()
    THEN  the return value is the server process cwd, never an empty path."""
    import os

    import core.engine_config as ec

    outside = tmp_path.resolve()
    monkeypatch.chdir(outside)
    monkeypatch.setattr(ec, "load_engine_config",
                        lambda: ec.EngineChoice(provider="local_ollama", model="m", workspace_dir=""))
    assert ec.get_workspace_dir() == str(outside)

    # A valid path wins over the fallback.
    monkeypatch.setattr(ec, "load_engine_config",
                        lambda: ec.EngineChoice(provider="local_ollama", model="m",
                                                 workspace_dir=str(ec.os.getcwd())))
    assert ec.get_workspace_dir() == os.getcwd()


def test_workspace_dir_never_defaults_to_the_ephe_checkout(monkeypatch, tmp_path):
    """GIVEN no user choice and a server started inside the Ephe source tree
    WHEN  get_workspace_dir()
    THEN  the neutral per-device workspace answers, not the checkout — the
    checkout's branches and file names are ours, never the user's project."""
    from pathlib import Path

    import core.engine_config as ec

    repo = Path(ec.__file__).resolve().parent.parent
    monkeypatch.chdir(repo / "core")
    monkeypatch.delenv("EPHE_WORKSPACE", raising=False)
    monkeypatch.setattr(ec, "load_engine_config",
                        lambda: ec.EngineChoice(provider="local_ollama", model="m", workspace_dir=""))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))

    ws = Path(ec.get_workspace_dir())
    assert ws == tmp_path / "workspace"
    assert ws.is_dir()
    assert repo not in ws.parents and ws != repo
