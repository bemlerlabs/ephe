"""G6 (workbench) — the agent reads its own run: transcript and cell journal.

The transparency half of the workbench gap: an agent can enumerate what it
started, stop it, read the trajectory it was shown, and fetch the cell output a
capped result left behind. These tests drive the tools through the registry (the
same path the agent takes) and pin the honest refusals beside the happy path.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from core.tools import TOOL_MAP, execute_tool, get_tool_schemas
from core.tools.approval import classify_tool

READERS = ("read_transcript", "read_cell_journal")


@pytest.fixture(autouse=True)
def isolated_trajectory(tmp_path, monkeypatch):
    """The trajectory registry is process-global and persists to the config dir."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    from core import trajectory

    trajectory.reset_for_test()
    yield trajectory
    trajectory.reset_for_test()


@pytest.fixture()
def work_root(tmp_path, monkeypatch):
    """The cell's /work root, pointed at the test's tmp so no home is touched."""
    root = tmp_path / "cell-work"
    monkeypatch.setenv("EPHE_CELL_WORK_ROOT", str(root))
    return root


@pytest.fixture()
def bg_register():
    """The shared background register, emptied around the test."""
    from core.tools.shell_tools import _BG_TASKS

    _BG_TASKS.clear()
    yield _BG_TASKS
    _BG_TASKS.clear()


def _schema(name: str) -> dict:
    for entry in get_tool_schemas():
        if entry["function"]["name"] == name:
            return entry["function"]
    raise AssertionError(f"{name} is not in the schema array")


def _run(name: str, arguments: dict) -> str:
    return asyncio.run(execute_tool(name, arguments))


# registry contract


def test_readers_are_registered_safe_and_visible():
    names = {entry["function"]["name"] for entry in get_tool_schemas()}
    from core.tools.discovery import CORE_TOOLS

    for name in READERS:
        assert name in TOOL_MAP, f"{name} has no handler"
        assert name in names, f"{name} is missing from the schema array"
        assert name in CORE_TOOLS, f"{name} is not in the always-visible base array"
        cls = classify_tool(name)
        assert cls.category == "SAFE", name
        assert cls.is_mutating is False, name


def test_process_manage_list_needs_no_task_id():
    """The listing is the way to FIND an id, so task_id cannot be required."""
    params = _schema("process_manage")["parameters"]
    assert params["required"] == ["action"]
    assert "list" in params["properties"]["action"]["enum"]
    # enum[0] stays 'poll': the enum-repair path fills enum[0] for a bad action.
    assert params["properties"]["action"]["enum"][0] == "poll"


# read_transcript


def test_read_transcript_renders_the_recorded_turn(isolated_trajectory):
    traj = isolated_trajectory
    traj.begin_turn("s-work", model="m", turn_id="t1")
    traj.record("s-work", {"type": "tool_start", "name": "read_file"})
    traj.record(
        "s-work",
        {"type": "usage", "usage": {"prompt_tokens": 11, "completion_tokens": 3}},
    )
    traj.end_turn("s-work")

    out = _run("read_transcript", {"session_id": "s-work"})
    assert "session=s-work" in out
    assert "turn 1" in out
    assert "read_file" in out
    assert "in=11 out=3" in out


def test_read_transcript_shows_text_bodies_only_on_request(isolated_trajectory):
    traj = isolated_trajectory
    traj.begin_turn("s-text")
    traj.record("s-text", {"type": "tool_done", "name": "run_shell", "result": "BODY-MARKER"})
    traj.end_turn("s-text")

    plain = _run("read_transcript", {"session_id": "s-text"})
    assert "BODY-MARKER" not in plain
    with_text = _run("read_transcript", {"session_id": "s-text", "include_text": True})
    assert "BODY-MARKER" in with_text


def test_read_transcript_caps_the_answer(isolated_trajectory):
    traj = isolated_trajectory
    traj.begin_turn("s-cap")
    for i in range(40):
        traj.record("s-cap", {"type": "tool_done", "name": f"tool_{i}", "result": "x" * 200})
    traj.end_turn("s-cap")

    out = _run("read_transcript", {"session_id": "s-cap", "include_text": True, "max_chars": 900})
    assert "cut at 900 chars" in out
    assert len(out) < 1200


def test_read_transcript_defaults_to_the_active_session(isolated_trajectory):
    """An empty ``session_id`` resolves through the active session, not a literal.

    The active-session ContextVar is process-global; another test's leaked value
    (``mutter-3`` under xdist) would otherwise decide this answer. The test pins
    it and uses a name that is not the fallback, so it proves the resolution.
    """
    from core.tools import session_ctx

    traj = isolated_trajectory
    traj.begin_turn("s-active")
    traj.record("s-active", {"type": "tool_start", "name": "web_search"})
    traj.end_turn("s-active")

    token = session_ctx.set_current_session("s-active")
    try:
        out = _run("read_transcript", {})
    finally:
        token.var.reset(token)
    assert "session=s-active" in out
    assert "web_search" in out


def test_read_transcript_without_a_turn_is_honest():
    out = _run("read_transcript", {"session_id": "nobody-here"})
    assert "no recorded turn" in out


# read_cell_journal


def test_read_cell_journal_fetches_a_byte_range(work_root):
    from core.cpython_guest import session_slug

    work = work_root / session_slug("s-journal")
    work.mkdir(parents=True)
    (work / "stdout.log").write_bytes(b"0123456789ABCDEF")

    out = _run("read_cell_journal", {"session_id": "s-journal", "start": 4, "length": 6})
    assert "bytes 4..10 of 16" in out
    assert "456789" in out


def test_read_cell_journal_names_the_remaining_bytes(work_root):
    from core.cpython_guest import session_slug

    work = work_root / session_slug("s-tail")
    work.mkdir(parents=True)
    (work / "stdout.log").write_bytes(bytes(range(100)))

    out = _run("read_cell_journal", {"session_id": "s-tail", "start": 0, "length": 10})
    assert "bytes 0..10 of 100" in out
    assert "90 byte remain" in out
    assert "start=10" in out


def test_read_cell_journal_reads_stderr_too(work_root):
    from core.cpython_guest import session_slug

    work = work_root / session_slug("s-err")
    work.mkdir(parents=True)
    (work / "stderr.log").write_bytes(b"traceback-body")

    out = _run("read_cell_journal", {"session_id": "s-err", "stream": "stderr"})
    assert "traceback-body" in out


def test_read_cell_journal_without_a_journal_is_honest(work_root):
    out = _run("read_cell_journal", {"session_id": "s-absent"})
    assert "has no stdout.log yet" in out


def test_read_cell_journal_rejects_an_unknown_stream():
    """The guard is direct: through execute_tool the schema enum repairs first."""
    from core.tools.workbench_tools import read_cell_journal

    out = asyncio.run(read_cell_journal(stream="sideways"))
    assert "unknown stream" in out


def test_read_cell_journal_enum_repair_stays_a_valid_call(work_root):
    """A bad enum value is repaired to enum[0], so the call does not crash."""
    out = _run("read_cell_journal", {"session_id": "s-repair", "stream": "sideways"})
    assert "read_cell_journal" in out and "has no stdout.log yet" in out


# process_manage(action='list')


def test_list_shows_id_status_age_and_command(bg_register):
    bg_register["bg7"] = {
        "status": "running",
        "out": "",
        "handle": None,
        "cmd": "tail -f /dev/null",
        "started": time.time() - 1.5,
    }
    out = _run("process_manage", {"action": "list"})
    assert "bg7" in out
    assert "running" in out
    assert "tail -f /dev/null" in out
    assert "age=" in out
    assert "out=0B" in out


def test_list_tolerates_an_entry_without_a_command(bg_register):
    """A register entry a test builds has no cmd — the listing must not invent one."""
    bg_register["bg9"] = {"status": "done", "out": "ok", "handle": None}
    out = _run("process_manage", {"action": "list"})
    assert "bg9" in out
    assert "command not recorded" in out


def test_list_of_an_empty_register_is_honest(bg_register):
    out = _run("process_manage", {"action": "list"})
    assert "no background process" in out


def test_list_then_kill_a_real_background_job(bg_register):
    """The whole point: start it, see it, stop it — without a remembered id."""

    async def run() -> None:
        tid = await execute_tool(
            "run_shell", {"command": "tail -f /dev/null", "run_in_background": True}
        )
        assert tid.startswith("bg"), tid

        listed = await execute_tool("process_manage", {"action": "list"})
        assert tid in listed, listed
        assert "tail -f /dev/null" in listed

        stopped = await execute_tool("process_manage", {"action": "kill", "task_id": tid})
        assert "stopped" in stopped.lower()

        after = await execute_tool("process_manage", {"action": "list"})
        assert "stopped" in after

    asyncio.run(run())


def test_poll_on_a_listed_done_job_returns_its_output(bg_register):
    async def run() -> None:
        tid = await execute_tool(
            "run_shell", {"command": "echo workbench-live", "run_in_background": True}
        )
        waited = await execute_tool(
            "process_manage", {"action": "wait", "task_id": tid, "timeout_s": 5}
        )
        assert "workbench-live" in waited
        listed = await execute_tool("process_manage", {"action": "list"})
        assert tid in listed and "echo workbench-live" in listed

    asyncio.run(run())
