"""tests/test_fleet_view.py — the fleet: which runs exist, what each is doing, who needs you.

`GET /api/workspaces` used to answer with the register and nothing else: a snapshot of the
checkouts, with no state a reader could act on and no way to tell a run that is thinking from
one that is stuck, or from one that has stopped and will not move until a person answers.

Every case drives the real path — a real git worktree per
run, a real register row whose owning process is gone, the real approval gate
(`server/routes/chat.py:_sandbox_confirm`) registering a wait a person has to answer — and
reads the result off the one route a page polls.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROVENANCE = {
    "session_id": "s-1",
    "agent_id": "agent-a",
    "why": "the wave asked for a described publish",
}
#: The session a run waits in. The approval gate records it, and it is the only way a wait
#: can be attributed back to the run that stopped on it.
WAITING_SESSION = "sess-fleet-7"


def _git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture(autouse=True)
def _fresh_helper_registry():
    """The helper registry is a process-wide dict; no case here reads another one's rows."""
    from core import subagent_history

    subagent_history.reset_for_test()
    yield
    subagent_history.reset_for_test()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A repository on ``main`` with one commit, and the managed directory beside it."""
    from core import workspace_lifecycle as life

    root = tmp_path / "checkout"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    (root / "README.md").write_text("the checkout\n", encoding="utf-8")
    _git(["add", "README.md"], root)
    _git(["-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "init"], root)
    monkeypatch.setattr(life, "REPO_ROOT", root)
    monkeypatch.setattr(life, "WORKSPACES_DIR", tmp_path / "managed")
    return root


@pytest.fixture
def client(checkout, tmp_path, monkeypatch):
    """The app under test, with the register, the change-set store and the home in tmp."""
    from core import change_set, review_gate
    from core.review_gate import ReviewLedger

    changesets = tmp_path / "changesets"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "ephe-home"))
    monkeypatch.setenv("EPHE_WORKSPACES_DIR", str(tmp_path / "managed"))
    monkeypatch.setenv("EPHE_CHANGESETS_DIR", str(changesets))
    monkeypatch.setattr(change_set, "CHANGESETS_DIR", changesets)
    monkeypatch.setattr(review_gate, "_default_ledger", ReviewLedger(tmp_path / "reviews.jsonl"))
    from server.main import create_app

    return TestClient(create_app())


def _board(client: TestClient) -> list[dict]:
    """The fleet rows of one poll, as the page reads them."""
    res = client.get("/api/workspaces")
    assert res.status_code == 200, res.text
    return res.json()["runs"]


def _row(client: TestClient, run_id: str) -> dict:
    """One run's row, or a failure naming what the board carried instead."""
    rows = {str(row["run_id"]): row for row in _board(client)}
    assert run_id in rows, f"{run_id} missing from {sorted(rows)}"
    return rows[run_id]


def _create(client: TestClient, owner: str = "agent-a") -> dict:
    res = client.post("/api/workspaces", json={"owner": owner, "base": "main"})
    assert res.status_code == 200, res.text
    return res.json()["workspace"]


def _edit(path: str) -> None:
    (Path(path) / "README.md").write_text("the checkout\nedited\n", encoding="utf-8")


def _build(client: TestClient, workspace_id: str) -> dict:
    res = client.post(
        "/api/change-sets",
        json={"workspace_id": workspace_id, "summary": "one edit", "provenance": PROVENANCE},
    )
    assert res.status_code == 200, res.text
    return res.json()["change_set"]


def _approve(client: TestClient, change_set: dict):
    """The verdict a second agent files, kept because a publish refuses without one."""
    return client.post(
        f"/api/change-sets/{change_set['id']}/review",
        json={
            "verdict": "approve",
            "reviewer": "agent-b",
            "reasons": [{"path": change_set["files"][0]["path"], "line": 1, "why": "reads right"}],
        },
    )


# The vocabulary


def test_run_state_reads_the_marks_the_registries_carry():
    """Given each mark; Then the state it means, and a status that ended decides alone."""
    from core import fleet

    assert fleet.run_state(status="running") == "running"
    assert fleet.run_state(tree_state="dirty", owner_alive=True) == "running"
    assert fleet.run_state(tree_state="published", owner_alive=True) == "done"
    assert fleet.run_state(status="done") == "done"
    # A tree whose owning process is gone is not working, and never will on its own.
    assert fleet.run_state(tree_state="dirty", owner_alive=False) == "blocked"
    assert fleet.run_state(status="error") == "blocked"
    assert fleet.run_state(status="step_limit") == "blocked"
    assert fleet.needs_you("waiting_on_human") and fleet.needs_you("blocked")
    assert not fleet.needs_you("running") and not fleet.needs_you("done")


def test_owner_alive_reads_a_pid_that_is_gone_as_gone():
    """Given our own pid, a reaped one and a value that is no pid; Then True, False, None."""
    from core import fleet

    assert fleet.owner_alive(os.getpid()) is True
    assert fleet.owner_alive(_free_pid()) is False
    assert fleet.owner_alive(None) is None
    assert fleet.owner_alive("not a pid") is None


def _free_pid() -> int:
    """A pid that does not exist: one this process spawned and then reaped."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


# The board the route serves


def test_the_board_lists_a_live_run_with_the_workspace_it_owns(client):
    """Given one run with a checkout; Then the board carries it, running, with its path."""
    created = _create(client, owner="agent-a")
    row = _row(client, f"workspace:{created['id']}")

    assert row["kind"] == "workspace"
    assert row["agent"] == "agent-a"
    assert row["state"] == "running"
    assert row["needs_you"] is False
    assert row["workspace_id"] == created["id"]
    assert row["path"] == created["path"]
    assert isinstance(row["running_for_seconds"], int)
    assert row["last_event"]["kind"] == "none", "nothing was changed yet"


def test_the_register_row_answers_the_same_state_as_the_board(client):
    """Given one live run; Then the list column and the board say the same thing."""
    created = _create(client, owner="agent-a")
    listed = client.get("/api/workspaces").json()["workspaces"]
    row = next(item for item in listed if item["id"] == created["id"])

    assert row["run_state"] == "running"
    assert row["needs_you"] is False
    assert row["owner_alive"] is True
    assert isinstance(row["running_for_seconds"], int)
    assert row["last_event"]["kind"] == "none"
    assert row["path"] == created["path"], "the six fields the register always carried stay"


def test_a_run_whose_owning_process_is_gone_shows_as_blocked(client, checkout, tmp_path):
    """Given a tree created by a process that has exited; Then it is blocked and needs you.

    This is the row a crash leaves behind — the register writes a row before git runs for
    exactly this reason — and it is the one nobody can see today.
    """
    script = (
        "from core import workspace_lifecycle as life;"
        "print(life.create('crashed-runner', 'main').id)"
    )
    env = {
        **os.environ,
        "EPHE_REPO_ROOT": str(checkout),
        "EPHE_WORKSPACES_DIR": str(tmp_path / "managed"),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, cwd=str(checkout)
    )
    assert done.returncode == 0, done.stderr
    tree_id = done.stdout.strip().splitlines()[-1]

    row = _row(client, f"workspace:{tree_id}")
    assert row["agent"] == "crashed-runner"
    assert row["state"] == "blocked"
    assert row["needs_you"] is True


def test_a_finished_helper_run_shows_as_done(client):
    """Given a helper run that finished; Then its row is done and asks nothing of anyone."""
    from core import subagent_history

    subagent_history.begin(
        "subagent-9",
        role="general-purpose",
        task="check the tree",
        description="the tree check",
        model="test",
        chat_session_id="helper-subagent-9",
    )
    subagent_history.finish(
        "subagent-9", status="done", report="the tree is clean", duration_ms=1500, transcript=[]
    )

    row = _row(client, "agent:subagent-9")
    assert row["kind"] == "agent"
    assert row["agent"] == "subagent-9"
    assert row["task"] == "the tree check"
    assert row["state"] == "done"
    assert row["needs_you"] is False
    assert row["workspace_id"] == "", "a helper owns no checkout"


def test_a_run_that_failed_is_blocked_and_sorts_above_the_busy_ones(client):
    """Given a failed helper and a live checkout; Then the failed one is listed first."""
    from core import subagent_history

    _create(client, owner="agent-a")
    subagent_history.begin(
        "subagent-8",
        role="general-purpose",
        task="check the tree",
        description="the tree check",
        model="test",
        chat_session_id="helper-subagent-8",
    )
    subagent_history.finish(
        "subagent-8", status="error", report="the tree was not there", duration_ms=90, transcript=[]
    )

    board = _board(client)
    assert board[0]["run_id"] == "agent:subagent-8", board
    assert board[0]["state"] == "blocked"
    assert board[0]["needs_you"] is True
    assert board[1]["state"] == "running", board


def test_a_just_interrupted_helper_asks_for_a_restart(client):
    """Given a helper that stopped without finishing; Then the board reads it as blocked."""
    from core import subagent_history

    subagent_history.begin(
        "subagent-cancelled",
        role="general-purpose",
        task="check the tree",
        description="the tree check",
        model="test",
        chat_session_id="helper-subagent-cancelled",
    )
    subagent_history.get("subagent-cancelled")["status"] = "interrupted"

    row = _row(client, "agent:subagent-cancelled")
    assert row["state"] == "blocked"
    assert row["needs_you"] is True


def test_an_interrupted_helper_ages_off_the_board(client):
    """Given a run that stopped a day ago; Then the fleet does not present it as work.

    The ledger keeps it (the subagent directory is a history); the board is not.
    """
    from core import subagent_history

    subagent_history.begin(
        "subagent-yesterday",
        role="general-purpose",
        task="check the tree",
        description="the tree check",
        model="test",
        chat_session_id="helper-subagent-yesterday",
    )
    record = subagent_history.get("subagent-yesterday")
    record["status"] = "interrupted"
    record["started_ts"] = time.time() - 86400

    assert all(run["run_id"] != "agent:subagent-yesterday" for run in _board(client))


def test_the_last_change_set_is_what_the_run_touched(client):
    """Given one described edit; Then the row names the file, the operation and its age."""
    created = _create(client, owner="agent-a")
    _edit(created["path"])
    _build(client, created["id"])

    event = _row(client, f"workspace:{created['id']}")["last_event"]
    assert event["kind"] == "file"
    assert event["text"] == "README.md"
    assert event["op"] == "modify"
    assert isinstance(event["age_seconds"], int)


def test_a_tree_the_register_calls_published_reads_as_done(client):
    """Given the register's own word for landed work; Then the row is done, not busy.

    `published` is one of the five states `core.workspace_lifecycle.STATES` declares, so the
    board honours it. Nothing in the HTTP path writes that word today — a publish moves the
    files and does not tell the register — which is why a helper run is the everyday `done`
    on this board and this case pins the vocabulary rather than a route.
    """
    landed = _create(client, owner="agent-b")
    register_path = Path(os.environ["EPHE_WORKSPACES_DIR"]) / "register.json"
    raw = json.loads(register_path.read_text(encoding="utf-8"))
    for row in raw["workspaces"]:
        if row["id"] == landed["id"]:
            row["state"] = "published"
    register_path.write_text(json.dumps(raw), encoding="utf-8")

    row = _row(client, f"workspace:{landed['id']}")
    assert row["state"] == "done"
    assert row["needs_you"] is False


def test_the_loop_from_edit_to_publish_leaves_the_board_unchanged(client):
    """Given the whole isolation loop; Then no state on the board is invented by a publish.

    A publish moves files onto a branch. It does not tell the register, so the run that
    published is still a live tree and still reads as running — the board says what the
    stores say and nothing more.
    """
    created = _create(client, owner="agent-a")
    _edit(created["path"])
    built = _build(client, created["id"])
    assert _approve(client, built).status_code == 200
    assert client.post(f"/api/change-sets/{built['id']}/publish", json={}).status_code == 200

    assert _row(client, f"workspace:{created['id']}")["state"] == "running"


# Waiting on a person


async def test_a_wait_registers_as_waiting_on_human_and_leaves_when_answered(client, monkeypatch):
    """Given a live approval wait; Then it is its own row, first, and answering clears it.

    The wait is driven through the real gate: `_sandbox_confirm` is the coroutine the chat
    route runs before an approval-gated tool, and it registers the token the app-wide
    registry answers for. Nothing here is written into that registry by hand.
    """
    from core import security_config
    from core.security_config import SecurityConfig
    from server.routes import chat

    # The profile decides whether the gate asks at all: strict always asks, and the
    # developer's own config must not decide what this case measures.
    monkeypatch.setattr(
        security_config,
        "load_security_config",
        lambda: SecurityConfig(approval_profile="strict"),
    )

    emitted: list[dict] = []
    task = asyncio.create_task(
        chat._sandbox_confirm(
            "run_shell",
            {"command": "git status"},
            emitted.append,
            lambda _line: None,
            chat.StreamRequest(message="check the tree", session_id=WAITING_SESSION, mode="ask"),
        )
    )
    for _ in range(200):  # the registration lands before the wait starts
        if emitted:
            break
        await asyncio.sleep(0.01)
    assert emitted, "the gate never asked"

    board = _board(client)
    waiting = [row for row in board if row["state"] == "waiting_on_human"]
    assert len(waiting) == 1, board
    row = waiting[0]
    assert row["kind"] == "session"
    assert row["agent"] == WAITING_SESSION
    assert row["needs_you"] is True
    assert row["last_event"]["kind"] == "awaiting"
    assert row["last_event"]["text"] == "run_shell"
    assert board.index(row) == 0, "the run that needs a person sorts first"

    res = client.post("/api/sandbox/approve", json={"token": emitted[0]["token"], "approved": True})
    assert res.status_code == 200, res.text
    assert await task is True
    assert not [r for r in _board(client) if r["state"] == "waiting_on_human"]


def test_a_waiting_session_is_its_own_row_and_never_its_helpers(client, monkeypatch):
    """Given a session waiting with two helpers under it; Then only the session is waiting.

    The live board answered this one the hard way: matching a wait to every helper started
    from the waiting session painted three helpers as "waiting for your answer" — one of them
    finished. A helper cannot wait on an approval at all (`spawn_agent` hands out read-only
    tools), so the wait belongs to the session that asked, and a helper keeps its own status.
    """
    from core import subagent_history
    from server.routes import chat

    for agent_id, status in (("subagent-201", "done"), ("subagent-202", "running")):
        subagent_history.begin(
            agent_id,
            role="general-purpose",
            task="check the tree",
            description="the tree check",
            model="test",
            chat_session_id=f"helper-{agent_id}",
            parent_session=WAITING_SESSION,
        )
        if status == "done":
            subagent_history.finish(
                agent_id, status="done", report="clean", duration_ms=800, transcript=[]
            )
    monkeypatch.setattr(
        chat,
        "pending_approvals",
        lambda: [
            {
                "token": "t-1",
                "session_id": WAITING_SESSION,
                "tool": "run_shell",
                "waiting_seconds": 12,
            }
        ],
    )

    waiting = [row for row in _board(client) if row["state"] == "waiting_on_human"]
    assert [row["run_id"] for row in waiting] == [f"session:{WAITING_SESSION}"], waiting
    assert waiting[0]["last_event"]["kind"] == "awaiting"
    assert waiting[0]["last_event"]["text"] == "run_shell"
    assert waiting[0]["last_event"]["age_seconds"] == 12
    # The helpers of that session are what their own registry says they are.
    assert _row(client, "agent:subagent-201")["state"] == "done"
    assert _row(client, "agent:subagent-202")["state"] == "running"
