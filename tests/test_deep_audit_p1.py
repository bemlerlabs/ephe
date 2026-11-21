"""tests/test_deep_audit_p1.py — regression for the deep-audit P1 fixes (2026-09-16).

P1a: tool_call passes the active approval policy along (no gate bypass).
P1b: the run_tests whitelist is in sync with TEST_RUNNERS (pytest/npx/vitest), and the
     Python-side heads run on the interpreter that runs Ephe rather than the one PATH picks.
P1c: _friendly_model_error never returns an empty message.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest

from core.tools import session_ctx
from core.tools.approval import ApprovalPolicy
from core.tools.base import ALLOWED_COMMANDS
from core.tools.test_tools import TEST_RUNNERS, TEST_TIMEOUT_SECONDS, run_tests


def test_p1b_test_runners_are_in_allowed_commands():
    """GIVEN TEST_RUNNERS, WHEN checked against ALLOWED_COMMANDS, THEN every
    runner class is also shell-whitelist-capable (validate runs before the runner check)."""
    # python/python3/node/npm are already listed; the three new ones have to be in.
    for runner in ("pytest", "npx", "vitest"):
        assert runner in TEST_RUNNERS
        assert runner in ALLOWED_COMMANDS, f"{runner} fehlt in ALLOWED_COMMANDS"


def test_p1b_run_tests_default_pytest_passes_whitelist(tmp_path, monkeypatch):
    """GIVEN a workspace, WHEN run_tests runs with the default 'pytest -q',
    THEN no 'not in the whitelist' (before: validate refused before the runner check)."""
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_workspace_dir", lambda: str(tmp_path))
    (tmp_path / "test_tiny.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    result = asyncio.run(run_tests())
    assert "not in the whitelist" not in result
    assert "[exit 0]" in result


def test_p1b_run_tests_npx_vitest_passes_whitelist(tmp_path, monkeypatch):
    """GIVEN 'npx vitest run', WHEN checked, THEN no whitelist abort on the first token."""
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_workspace_dir", lambda: str(tmp_path))
    result = asyncio.run(run_tests("npx vitest run"))
    assert "not in the whitelist" not in result


def _runner_commands(monkeypatch, tmp_path) -> list:
    """Records the command the tool hands to the shell, without running anything.

    `subprocess.run` is the binding the call site looks up (test_tools imports the module,
    not the function), so this patches what actually executes.
    """
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_workspace_dir", lambda: str(tmp_path))
    calls: list = []

    class _RunnerResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return _RunnerResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_p1b_pytest_head_uses_the_running_interpreter_not_a_path_script(tmp_path, monkeypatch):
    """GIVEN a machine whose PATH owns a `pytest` of its own, WHEN run_tests('pytest -q')
    THEN the command is this interpreter's `-m pytest` and no bare head survives.

    The defect measured on the self-hosted arm64 runner was exactly that: PATH resolved
    `pytest` to a stale ~/.local/bin/pytest of another Python, whose missing
    `typing_extensions` answered `[exit 1]` for a suite that was fine.
    """
    calls = _runner_commands(monkeypatch, tmp_path)
    result = asyncio.run(run_tests("pytest -q"))

    command, kwargs = calls[0]
    assert command.split()[0] == sys.executable, command
    assert command == f"{sys.executable} -m pytest -q"
    assert "[exit 0]" in result, result
    # The rest of the contract is untouched by the rewrite.
    assert kwargs["shell"] is True
    assert kwargs["timeout"] == TEST_TIMEOUT_SECONDS
    assert kwargs["cwd"] == str(tmp_path)


def test_p1b_pytest_arguments_survive_the_rewrite(tmp_path, monkeypatch):
    """GIVEN a targeted pytest call, WHEN the head is mapped, THEN every other token stands."""
    calls = _runner_commands(monkeypatch, tmp_path)
    asyncio.run(run_tests("pytest -q tests/test_x.py::test_y --tb=short"))
    assert calls[0][0] == f"{sys.executable} -m pytest -q tests/test_x.py::test_y --tb=short"


def test_p1b_python_head_still_maps_to_the_running_interpreter(tmp_path, monkeypatch):
    """GIVEN 'python -m pytest', WHEN the head is mapped, THEN the same interpreter answers."""
    calls = _runner_commands(monkeypatch, tmp_path)
    asyncio.run(run_tests("python -m pytest -q"))
    assert calls[0][0] == f"{sys.executable} -m pytest -q"


def test_p1b_bare_pytest_head_maps_and_bare_python_stays_refused(tmp_path, monkeypatch):
    """GIVEN a runner head with no arguments, WHEN mapped, THEN `pytest` runs on the
    interpreter and the bare REPL heads keep their existing refusal.

    The two halves belong together: `python` alone is not a test run, and the guard that
    says so must not be traded for the interpreter mapping.
    """
    calls = _runner_commands(monkeypatch, tmp_path)
    asyncio.run(run_tests("pytest"))
    assert calls[0][0] == f"{sys.executable} -m pytest"

    for head in ("python", "python3"):
        asyncio.run(run_tests(head))
    assert "REPL" in asyncio.run(run_tests("python")), "bare python must stay refused"


@pytest.mark.parametrize("command", ["npx vitest run", "vitest run", "npm test", "node --test"])
def test_p1b_javascript_heads_are_left_path_resolved(command, tmp_path, monkeypatch):
    """GIVEN a JS runner head, WHEN run_tests runs it, THEN the command is exactly what was
    written: there is no running interpreter to map it onto, and inventing one is out of scope."""
    calls = _runner_commands(monkeypatch, tmp_path)
    asyncio.run(run_tests(command))
    assert calls[0][0] == command


def test_p1c_friendly_model_error_never_empty():
    """GIVEN an exception whose str() rendering is empty, WHEN _friendly_model_error,
    THEN not empty (falls back to the class name)."""
    from server.routes.chat import _friendly_model_error

    msg = _friendly_model_error(RuntimeError(), None)
    assert msg != ""
    assert "RuntimeError" in msg


def test_p1a_current_policy_roundtrip():
    """GIVEN a policy, WHEN session_ctx set/get, THEN the same instance is
    returned (the basis of the tool_call pass-along mechanism)."""
    policy = ApprovalPolicy(auto_approve=True)
    session_ctx.set_current_policy(policy)
    assert session_ctx.get_current_policy() is policy


def test_p1a_tool_call_threads_active_policy(tmp_path, monkeypatch):
    """GIVEN an active policy with an on_confirm counter, WHEN tool_call calls a
    mutating tool, THEN the approval gate was hit (no bypass)."""
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_workspace_dir", lambda: str(tmp_path))

    prompts: list[str] = []

    async def _on_confirm(name: str, args: dict) -> bool:
        prompts.append(name)
        return True

    policy = ApprovalPolicy(auto_approve=False, interactive=True, on_confirm=_on_confirm)
    session_ctx.set_current_policy(policy)

    from core.tools.discovery import tool_call

    result = asyncio.run(tool_call("write_file", {"path": "p1a.txt", "content": "x = 1\n"}))
    assert "WRITE_FILE:" in result
    assert "write_file" in prompts, "Approval-Gate wurde vom tool_call-Pfad umgangen"
