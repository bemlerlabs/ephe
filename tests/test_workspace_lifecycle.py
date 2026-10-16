"""tests/test_workspace_lifecycle.py — a tree per agent run, and the register that collects it.

Finding 2026-10-14, measured on this machine: ``git worktree list`` named twenty-four
checkouts under ``ephe-wt/`` and ``~/.ephe``, while nothing in ``core`` or ``server``
could create, name, report or remove a single one of them — the only hits for the word
were evidence metadata on a finished run. A wave that died left its directory standing,
and the oldest entries in that list were days old. Every case below fails while that
lifecycle is absent, and every one of them runs against a throwaway repository under
``tmp_path``: the checkout at the root of this worktree is never the target.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CHECKOUT_FILE = "README.md"


def _wl():
    from core import workspace_lifecycle

    return workspace_lifecycle


def _git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A repository with one commit, plus the managed directory beside it."""
    wl = _wl()
    root = tmp_path / "checkout"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    (root / CHECKOUT_FILE).write_text("the checkout\n", encoding="utf-8")
    _git(["add", CHECKOUT_FILE], root)
    _git(["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "init"], root)
    monkeypatch.setattr(wl, "REPO_ROOT", root)
    monkeypatch.setattr(wl, "WORKSPACES_DIR", tmp_path / "managed")
    return root


def _rows(wl) -> list[dict]:
    path = wl.register_file()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["workspaces"]


def _worktrees(root: Path) -> set[str]:
    out = _git(["worktree", "list", "--porcelain"], root)
    named = (line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("worktree "))
    return {str(Path(name).resolve()) for name in named}


def _tree(root: Path) -> set[str]:
    """Every path the checkout carries outside its own git directory."""
    return {str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.parts}


def _exited_pid() -> int:
    """A pid that is certainly gone: a child that has been started and reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _claim_owner(wl, tree_id: str, pid: int) -> None:
    """Hand a row to another pid, the way a crashed owner leaves it behind."""
    rows = _rows(wl)
    for row in rows:
        if row["id"] == tree_id:
            row["pid"] = pid
    wl.register_file().write_text(json.dumps({"workspaces": rows}), encoding="utf-8")


def _poison(wl, target: Path, pid: int) -> str:
    """Point a register row at a directory the module must never delete."""
    row = {
        "id": "beefbeef",
        "path": str(target),
        "branch": "main",
        "state": "ready",
        "owner": "poison",
        "created_at": "2020-01-01T00:00:00+00:00",
        "pid": pid,
    }
    wl.register_file().parent.mkdir(parents=True, exist_ok=True)
    wl.register_file().write_text(json.dumps({"workspaces": [row]}), encoding="utf-8")
    return "beefbeef"


# A tree per run

def test_create_adds_one_worktree_beside_the_register(checkout):
    wl = _wl()
    ws = wl.create("agent-a")

    assert ws.state == "ready"
    assert ws.owner == "agent-a"
    assert len(ws.id) == 8
    assert ws.branch == f"ws/agent-a-{ws.id}"
    assert Path(ws.path).is_dir()
    assert Path(ws.path).parent == wl.WORKSPACES_DIR
    assert (Path(ws.path) / CHECKOUT_FILE).read_text(encoding="utf-8") == "the checkout\n"
    assert str(Path(ws.path).resolve()) in _worktrees(checkout)
    assert wl.register_file().exists()


def test_create_on_a_base_git_does_not_know_is_marked_for_the_reaper(checkout):
    wl = _wl()

    with pytest.raises(wl.WorkspaceError):
        wl.create("doomed", base="no-such-base")

    rows = _rows(wl)
    assert [row["state"] for row in rows] == ["discarded"]
    assert wl.list_live() == []
    assert wl.reap_orphans(0) == [rows[0]["id"]]
    assert _rows(wl) == []
    assert _worktrees(checkout) == {str(checkout.resolve())}


def test_list_live_names_every_tree_and_skips_strays(checkout):
    wl = _wl()
    first = wl.create("agent-a")
    second = wl.create("agent-b")
    stray = wl.WORKSPACES_DIR / "notregistered"
    stray.mkdir(parents=True)

    live = wl.list_live()
    assert {w.id for w in live} == {first.id, second.id}
    assert {w.state for w in live} == {"ready"}
    assert {w.owner for w in live} == {"agent-a", "agent-b"}
    assert str(stray) not in {w.path for w in live}


def test_get_reports_one_tree_and_refreshes_its_state(checkout):
    wl = _wl()
    ws = wl.create("agent-a")
    assert wl.get(ws.id).state == "ready"

    (Path(ws.path) / "edit.txt").write_text("local work\n", encoding="utf-8")

    assert wl.get(ws.id).state == "dirty"
    assert next(row for row in _rows(wl) if row["id"] == ws.id)["state"] == "dirty"
    assert wl.get("00000000") is None


def test_remove_takes_the_tree_the_branch_and_the_row_away(checkout):
    wl = _wl()
    ws = wl.create("agent-a")
    branch = ws.branch

    wl.remove(ws.id)

    assert not Path(ws.path).exists()
    assert wl.get(ws.id) is None
    assert wl.list_live() == []
    assert _rows(wl) == []
    assert str(Path(ws.path).resolve()) not in _worktrees(checkout)
    assert branch not in _git(["branch", "--list"], checkout)


def test_remove_refuses_a_dirty_tree_until_force_says_otherwise(checkout):
    wl = _wl()
    ws = wl.create("agent-a")
    (Path(ws.path) / "edit.txt").write_text("local work\n", encoding="utf-8")

    with pytest.raises(wl.WorkspaceError):
        wl.remove(ws.id)
    assert Path(ws.path).is_dir()

    wl.remove(ws.id, force=True)
    assert not Path(ws.path).exists()


def test_remove_of_an_unknown_id_changes_nothing(checkout):
    wl = _wl()
    ws = wl.create("agent-a")

    wl.remove("deadbeef")

    assert Path(ws.path).is_dir()
    assert {w.id for w in wl.list_live()} == {ws.id}


# The register collects what a crash leaves

def test_reap_takes_a_tree_whose_owner_process_is_gone(checkout):
    wl = _wl()
    ws = wl.create("crashed")
    (Path(ws.path) / "left.txt").write_text("half-done\n", encoding="utf-8")
    _claim_owner(wl, ws.id, _exited_pid())

    assert wl.reap_orphans(0) == [ws.id]

    assert not Path(ws.path).exists()
    assert wl.get(ws.id) is None
    assert wl.list_live() == []
    assert _rows(wl) == []
    assert _worktrees(checkout) == {str(checkout.resolve())}


def test_reap_leaves_a_living_owner_alone(checkout):
    wl = _wl()
    ws = wl.create("running")

    assert wl.reap_orphans(0) == []

    assert Path(ws.path).is_dir()
    assert {w.id for w in wl.list_live()} == {ws.id}


def test_reap_waits_out_the_grace_period(checkout):
    wl = _wl()
    ws = wl.create("crashed")
    _claim_owner(wl, ws.id, _exited_pid())

    assert wl.reap_orphans(60) == []
    assert Path(ws.path).is_dir()

    assert wl.reap_orphans(0) == [ws.id]
    assert not Path(ws.path).exists()


# The checkout is never the target

def test_a_teardown_never_reaches_the_checkout(checkout, tmp_path):
    """GIVEN a register row aimed at the checkout, at the managed directory or at a
    directory beside them
    WHEN remove is called on that row
    THEN it is refused and every one of those directories is still standing."""
    wl = _wl()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    for target in (checkout, elsewhere, wl.WORKSPACES_DIR):
        assert _poison(wl, target, os.getpid()) == "beefbeef"
        with pytest.raises(wl.UnsafePath):
            wl.remove("beefbeef")

    assert (checkout / CHECKOUT_FILE).read_text(encoding="utf-8") == "the checkout\n"
    assert elsewhere.is_dir()
    assert wl.WORKSPACES_DIR.is_dir() or not wl.WORKSPACES_DIR.exists()
    assert _git(["status", "--porcelain"], checkout) == ""


def test_the_reaper_will_not_collect_the_checkout(checkout):
    wl = _wl()
    _poison(wl, checkout, _exited_pid())

    assert wl.reap_orphans(0) == []

    assert [row["id"] for row in _rows(wl)] == ["beefbeef"]
    assert (checkout / CHECKOUT_FILE).exists()
    assert _worktrees(checkout) == {str(checkout.resolve())}


def test_a_whole_lifecycle_leaves_the_checkout_untouched(checkout):
    wl = _wl()
    before = _tree(checkout)

    ws = wl.create("agent-a")
    wl.get(ws.id)
    (Path(ws.path) / "edit.txt").write_text("local work\n", encoding="utf-8")
    wl.remove(ws.id, force=True)
    wl.reap_orphans(0)

    assert _tree(checkout) == before
    assert _git(["status", "--porcelain"], checkout) == ""
    assert _worktrees(checkout) == {str(checkout.resolve())}
