"""
Ephe — R37: agent hardening.

Pins:
  1. Tool budget per task class: casual 5, coding class (/ephe) 25, hard cap 40.
  2. Cap end = an honest "unfinished" note carrying the number, never pseudo-complete.
  3. Follow-up LLM call after tool rounds: 2x retry with backoff, then an honest fail.
  4. Error events never empty — fallback to the exception class name.
  5. TEST_RUNNERS includes node (besides npm); run_tests forwards cwd (in-workspace).
  6. run_shell forwards cwd to the confirmed-exec path.
  7. The autonomous flag is respected (False => strict, True => opt-in auto-approve).

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# 1 + 2: budget per task class + cap note

def test_clamp_tool_budget_by_task_class():
    """GIVEN budgets per task class (casual 10, /ephe 25)
    WHEN clamp_tool_budget()
    THEN None->10, 25->25 (past the old cap of 20), 100->40, 0->10."""
    from core.chat import clamp_tool_budget

    assert clamp_tool_budget(None) == 25  # R46: coding default in the normal chat
    assert clamp_tool_budget(25) == 25
    assert clamp_tool_budget(100) == 40
    # or-fallback: 0 is falsy and drops back to the casual default of 10.
    assert clamp_tool_budget(0) == 25


def test_budget_note_is_unfinished_and_carries_cap():
    """GIVEN an exhausted tool budget
    WHEN the cap note is produced
    THEN it carries the round count, 'budget exhausted' and 'unfinished';
    a normal answer text is not unfinished."""
    from core.chat import _budget_exhausted_note
    from core.quality import budget_note_is_unfinished

    note = _budget_exhausted_note(25)
    assert "25" in note
    assert "budget exhausted" in note
    assert "unfinished" in note
    assert budget_note_is_unfinished(note) is True
    assert budget_note_is_unfinished("42") is False
    assert budget_note_is_unfinished("") is False


def test_ephe_budget_constant_is_40_and_clamps_to_hard_cap():
    """GIVEN /ephe as the coding class
    WHEN the wiring budget is read and clamped
    THEN it is 40 (= the hard cap, P2b consolidation) and clamps to the hard cap 40."""
    from server.routes.chat import EPHE_TOOL_BUDGET

    from core.chat import clamp_tool_budget

    assert EPHE_TOOL_BUDGET == 40
    assert clamp_tool_budget(EPHE_TOOL_BUDGET) == 40


# 3: follow-up retry with backoff

@pytest.mark.asyncio
async def test_follow_up_retry_recovers_after_two_failures():
    """GIVEN a follow-up call that fails twice and then succeeds
    WHEN _follow_up_with_retry()
    THEN the value is delivered after exactly 3 attempts (2 retries)."""
    from core.chat import _follow_up_with_retry

    state = {"n": 0}

    async def call():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await _follow_up_with_retry(call)
    assert result == "ok"
    assert state["n"] == 3


@pytest.mark.asyncio
async def test_follow_up_retry_gives_up_after_two_retries():
    """GIVEN a call that fails throughout
    WHEN _follow_up_with_retry()
    THEN exactly 3 attempts (1 + 2 backoff retries), then the last error."""
    from core.chat import _follow_up_with_retry

    state = {"n": 0}

    async def call():
        state["n"] += 1
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await _follow_up_with_retry(call)
    assert state["n"] == 3


# 4: error events never empty

def test_error_msg_falls_back_to_exception_class_name():
    """GIVEN exceptions with and without text
    WHEN _error_msg()
    THEN never empty — otherwise the class name as the fallback."""
    from server.routes.chat import _error_msg

    assert _error_msg(ValueError("boom")) == "boom"
    assert _error_msg(ValueError("")) == "ValueError"
    assert _error_msg(SimpleNamespace()) in ("SimpleNamespace", "namespace()")


# 5 + 6: runner whitelist + cwd hand-over

def test_test_runners_include_node_and_npm():
    """GIVEN the runner whitelist
    WHEN TEST_RUNNERS is read
    THEN node and npm are in it (test runner names, not a general shell)."""
    from core.tools.test_tools import TEST_RUNNERS

    assert "node" in TEST_RUNNERS
    assert "npm" in TEST_RUNNERS


@pytest.mark.asyncio
async def test_run_tests_accepts_node_runner_and_forwards_cwd(tmp_path, monkeypatch):
    """GIVEN a workspace with the subfolder 'sub'
    WHEN run_tests('node --test x.js', cwd='sub')
    THEN the runner is accepted and subprocess.run receives the
    cwd path resolved inside the workspace."""
    import os

    import core.engine_config as ec
    import core.tools.test_tools as tt

    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    monkeypatch.setattr(ec, "get_workspace_dir", lambda: str(ws.resolve()))

    captured: dict = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured.update(kw)
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(tt, "subprocess", SimpleNamespace(run=fake_run))

    out = await tt.run_tests("node --test x.js", cwd="sub")
    assert "[exit 0]" in out
    assert captured["cmd"] == "node --test x.js"
    assert os.path.basename(str(captured.get("cwd", ""))) == "sub"


@pytest.mark.asyncio
async def test_run_tests_cwd_outside_workspace_falls_back(tmp_path, monkeypatch):
    """GIVEN a cwd path outside the workspace
    WHEN run_tests(..., cwd='/nonexistent-xyz')
    THEN the resolution falls back to the workspace root (no crash)."""
    import core.engine_config as ec
    import core.tools.test_tools as tt

    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(ec, "get_workspace_dir", lambda: str(ws.resolve()))

    captured: dict = {}

    def fake_run(cmd, **kw):
        captured.update(kw)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tt, "subprocess", SimpleNamespace(run=fake_run))

    await tt.run_tests("node --test x.js", cwd="/nonexistent-xyz")
    assert str(captured.get("cwd", "")) == str(ws.resolve())


@pytest.mark.asyncio
async def test_run_shell_forwards_cwd_to_confirmed_exec(monkeypatch):
    """GIVEN run_shell with a cwd parameter
    WHEN the hand-over is checked
    THEN the cwd reaches the confirmed-exec path (resolution there)."""
    import core.tools.shell_tools as st
    import core.tools._shell_exec as _shell_exec

    captured: dict = {}

    async def fake_exec(command, confirmed, cwd=None):
        captured["command"] = command
        captured["cwd"] = cwd
        return "ok"

    monkeypatch.setattr(_shell_exec, "execute_confirmed_shell", fake_exec)

    out = await st.run_shell("ls", cwd="sub")
    assert out == "ok"
    assert captured["cwd"] == "sub"


# 7: the autonomous flag is respected

def test_autonomous_flag_is_respected():
    """GIVEN the opt-in autonomous mode per request
    WHEN sandbox_auto_approval_allowed()
    THEN the decision hangs on the flag: False => strict (manual path),
    True => one confirmation is enough for auto-approve."""
    from server.routes.chat import sandbox_auto_approval_allowed

    assert sandbox_auto_approval_allowed(autonomous=False) is False
    assert sandbox_auto_approval_allowed(autonomous=True) is True
