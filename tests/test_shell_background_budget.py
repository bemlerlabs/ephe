"""The timeout a command gets is the budget its caller asked for.

`run_in_background` shares the exec path with the interactive shell, and until
now it shared the thirty-second cap as well: a ten-minute render was killed at
thirty seconds and the kill was folded into `status='error'`, so the agent read
"a failed render" where the truth was "a render that needed longer".
"""
from __future__ import annotations

import asyncio
import subprocess

import pytest

from core.tools import _shell_exec, _shell_proc
from core.tools.base import SHELL_BACKGROUND_TIMEOUT_SECONDS, SHELL_TIMEOUT_SECONDS
from core.tools.base import ShellTimeoutError


class _FakePopen:
    """Records the budget `communicate` was given, which is the whole question."""

    instances: list["_FakePopen"] = []

    def __init__(self, *args, **kwargs):
        self.pid = 4242
        self.returncode = 0
        self.got_timeout = "never-called"
        _FakePopen.instances.append(self)

    def communicate(self, timeout=None):
        self.got_timeout = timeout
        return "", ""


@pytest.fixture
def popen_spy(monkeypatch):
    _FakePopen.instances = []
    monkeypatch.setattr(_shell_proc.subprocess, "Popen", _FakePopen)
    return _FakePopen.instances


class TestExecSyncBudget:
    def test_given_no_budget_then_the_interactive_cap_is_read_at_call_time(
        self, popen_spy, monkeypatch
    ):
        monkeypatch.setattr(_shell_proc, "SHELL_TIMEOUT_SECONDS", 0.25)
        _shell_proc._exec_sync("echo hi", None, True)
        assert popen_spy[0].got_timeout == 0.25

    def test_given_a_budget_then_the_caller_decides(self, popen_spy):
        _shell_proc._exec_sync("ffmpeg -render", None, True, timeout=900)
        assert popen_spy[0].got_timeout == 900

    def test_given_the_interactive_default_then_it_is_still_thirty_seconds(self):
        # The owner set this bound; a background budget must not become an excuse
        # to let an interactive command run for minutes.
        assert SHELL_TIMEOUT_SECONDS == 30


class TestBackgroundPathCarriesItsOwnBudget:
    def _record(self, monkeypatch, outcome):
        calls: list = []

        def fake_exec_sync(command, cwd, use_shell, timeout=None, on_start=None):
            calls.append(timeout)
            if isinstance(outcome, BaseException):
                raise outcome
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=outcome,
                                               stderr="")

        monkeypatch.setattr(_shell_exec, "_exec_sync", fake_exec_sync)
        return calls

    def test_given_a_synchronous_command_then_no_budget_is_imposed(self, monkeypatch):
        calls = self._record(monkeypatch, "done")
        asyncio.run(_shell_exec.execute_confirmed_shell("echo hi", confirmed=True))
        assert calls == [None]

    def test_given_a_background_command_then_it_gets_the_render_budget(self, monkeypatch):
        calls = self._record(monkeypatch, "done")
        _shell_exec._BG_TASKS["bgR"] = {"status": "running", "out": "", "handle": None,
                                        "cmd": "ffmpeg -render", "cwd": "", "started": 0}
        asyncio.run(_shell_exec._exec_bg_task("bgR", "ffmpeg -render"))
        assert calls == [SHELL_BACKGROUND_TIMEOUT_SECONDS]
        assert _shell_exec._BG_TASKS["bgR"]["status"] == "done"
        _shell_exec._BG_TASKS.pop("bgR", None)

    def test_given_a_background_command_past_its_budget_then_the_status_says_so(
        self, monkeypatch
    ):
        calls = self._record(
            monkeypatch, subprocess.TimeoutExpired(cmd="ffmpeg -render", timeout=900)
        )
        _shell_exec._BG_TASKS["bgT"] = {"status": "running", "out": "", "handle": None,
                                        "cmd": "ffmpeg -render", "cwd": "", "started": 0}
        asyncio.run(_shell_exec._exec_bg_task("bgT", "ffmpeg -render"))
        entry = _shell_exec._BG_TASKS.pop("bgT")
        assert calls == [SHELL_BACKGROUND_TIMEOUT_SECONDS]
        assert entry["status"] == "timed_out", entry
        assert "budget" in entry["out"] and "killed" in entry["out"], entry["out"]

    def test_given_a_failing_command_then_it_is_not_reported_as_a_timeout(
        self, monkeypatch
    ):
        self._record(monkeypatch, OSError("boom"))
        _shell_exec._BG_TASKS["bgF"] = {"status": "running", "out": "", "handle": None,
                                        "cmd": "ffmpeg -render", "cwd": "", "started": 0}
        asyncio.run(_shell_exec._exec_bg_task("bgF", "ffmpeg -render"))
        entry = _shell_exec._BG_TASKS.pop("bgF")
        assert entry["status"] == "error", entry
        assert "boom" in entry["out"]


class TestTimeoutErrorStillNamesTheInteractiveCap:
    def test_given_a_sync_timeout_then_the_refusal_names_the_budget(self, monkeypatch):
        def explode(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="sleep 99", timeout=SHELL_TIMEOUT_SECONDS)

        monkeypatch.setattr(_shell_proc.subprocess, "Popen", explode)
        with pytest.raises(ShellTimeoutError) as raised:
            asyncio.run(_shell_exec.execute_confirmed_shell("echo hi", confirmed=True))
        assert raised.value.timeout == SHELL_TIMEOUT_SECONDS


def _alive(pid: int) -> bool:
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class TestStopActuallyStops:
    """A wider budget made the abandoned thread the only thing keeping a stopped job alive.

    Cancelling the asyncio task cannot interrupt a thread blocked in `communicate()`, so
    before the pid reached the register a `stopped` render kept burning CPU until its own
    budget ran out — fifteen minutes of a render nobody asked for anymore."""

    def test_given_a_stopped_background_job_then_its_process_is_gone(self):
        """GIVEN a background job that would run until the sun burns out and one stop call
        THEN the child is dead within the second, not merely marked stopped."""
        async def scenario() -> int:
            task_id = await _shell_exec.run_shell("tail -f /dev/null", run_in_background=True)
            entry = _shell_exec._BG_TASKS[task_id]
            for _ in range(200):
                if entry.get("pid") is not None:
                    break
                await asyncio.sleep(0.02)
            pid = entry.get("pid")
            assert pid is not None, "the register never learned the child's pid"
            assert await _shell_exec.task_stop(task_id) == f"Task {task_id} stopped."
            for _ in range(100):
                if not _alive(pid):
                    break
                await asyncio.sleep(0.05)
            _shell_exec._BG_TASKS.pop(task_id, None)
            return pid

        assert not _alive(asyncio.run(scenario()))

    def test_given_a_job_that_never_started_then_stop_says_what_it_finds(self, monkeypatch):
        """GIVEN an entry with no process behind it
        THEN stop names the state it sees instead of killing an unknown pid."""
        killed: list[int] = []
        monkeypatch.setattr(_shell_exec, "_kill_group", killed.append)
        _shell_exec._BG_TASKS["bgNoPid"] = {
            "status": "running", "out": "", "handle": None, "pid": None,
            "cmd": "true", "cwd": "", "started": 0.0,
        }
        try:
            assert "already running" in asyncio.run(_shell_exec.task_stop("bgNoPid"))
        finally:
            _shell_exec._BG_TASKS.pop("bgNoPid", None)
        assert killed == []

    def test_given_the_worker_thread_starts_the_child_then_the_register_holds_its_pid(self):
        """GIVEN the thread reports a pid
        THEN it lands in the register entry that `task_stop` reads."""
        _shell_exec._BG_TASKS["bgPid"] = {"pid": None}
        try:
            _shell_exec._record_pid("bgPid", 4243)
            assert _shell_exec._BG_TASKS["bgPid"]["pid"] == 4243
            _shell_exec._record_pid("bgAbsent", 1)
        finally:
            _shell_exec._BG_TASKS.pop("bgPid", None)
