"""tests/test_change_set.py — a set of changes is described, or nothing publishes.

The product records provenance for a run (`core/run_evidence.py`) and versions an
artifact with its provenance chain (`core/artifact_store.py`), while the changes a
publish hands over had no object that names the paths, the operations and the reason.
Every case here fails while `core/change_set.py` is absent, and each one runs against a
git repo and a store built inside the test's own tmp directory: the owner's real
``~/.ephe/changesets`` is never the target.

The diff digest is the load-bearing part: it hashes the diff text of one file, so an
edit made after the change set was built moves the digest while the store holds no file
content at all.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest


def _cs():
    from core import change_set

    return change_set


def _read():
    from core import change_set_read

    return change_set_read


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _commit(repo: Path, message: str = "init") -> None:
    """Commit without reading the machine's config: an identity or a signing key from
    ``~/.gitconfig`` would decide the outcome of a test about change sets."""
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "user.email=ephe@test",
         "-c", "user.name=ephe", "commit", "-q", "-m", message],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr


def _make_repo(path: Path) -> Path:
    """A committed repo with one file to edit, one to drop and one to leave alone."""
    path.mkdir(parents=True, exist_ok=True)
    assert _git(path, "init", "-q").returncode == 0
    (path / "edit.txt").write_text("one\ntwo\n", encoding="utf-8")
    (path / "drop.txt").write_text("gone\n", encoding="utf-8")
    (path / "untouched.txt").write_text("still here\n", encoding="utf-8")
    assert _git(path, "add", "-A").returncode == 0
    _commit(path)
    return path


def _why(text: str = "the wave asked for a described publish") -> dict:
    return {"session_id": "s-1", "agent_id": "a-1", "why": text}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A private change-set store; the real directory is never written."""
    change_set = _cs()
    target = tmp_path / "changesets"
    monkeypatch.setenv("EPHE_CHANGESETS_DIR", str(target))
    monkeypatch.setattr(change_set, "CHANGESETS_DIR", target)
    assert change_set.CHANGESETS_DIR == target
    return target


@pytest.fixture
def repo(tmp_path, store):
    return _make_repo(tmp_path / "repo")


def _ops(change_set_obj) -> dict[str, str]:
    return {entry.path: entry.op for entry in change_set_obj.files}


def _shas(change_set_obj) -> dict[str, str]:
    return {entry.path: entry.diff_sha for entry in change_set_obj.files}


def test_build_describes_the_worktree_diff(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (repo / "fresh.txt").write_text("brand new\n", encoding="utf-8")
    (repo / "drop.txt").unlink()

    built = change_set.build(str(repo), "add three, add fresh, drop drop", _why())

    assert _ops(built) == {"edit.txt": "modify", "fresh.txt": "create", "drop.txt": "delete"}
    assert built.state == "draft"
    assert built.workspace_id == str(repo)
    assert built.id.startswith("cs-")
    for digest in _shas(built).values():
        assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64
    assert change_set.load(built.id) == built


def test_an_unchanged_path_contributes_nothing(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    built = change_set.build(str(repo), "one edit", _why())

    assert [entry.path for entry in built.files] == ["edit.txt"]
    assert "untouched.txt" not in _ops(built)


def test_a_clean_tree_gives_a_change_set_with_no_files(repo, store):
    change_set = _cs()

    built = change_set.build(str(repo), "nothing yet", _why())

    reloaded = change_set.load(built.id)
    assert reloaded is not None and reloaded.files == []


def test_a_deleted_path_is_missing_on_disk_and_still_described(repo, store):
    """The file is gone, so the digest can only come from the diff text."""
    change_set = _cs()
    (repo / "drop.txt").unlink()

    built = change_set.build(str(repo), "drop the file", _why())

    assert not (repo / "drop.txt").exists()
    assert _ops(built) == {"drop.txt": "delete"}
    assert _shas(built)["drop.txt"].startswith("sha256:")


def test_the_digest_covers_the_diff_and_not_the_file(tmp_path, store):
    """Two paths with identical content digest differently, because the diff text names
    the path — a hash of the bytes could not tell them apart."""
    change_set = _cs()
    repo = _make_repo(tmp_path / "twin")
    (repo / "a.txt").write_text("same bytes\n", encoding="utf-8")
    (repo / "b.txt").write_text("same bytes\n", encoding="utf-8")

    built = change_set.build(str(repo), "two twins", _why())

    assert _ops(built) == {"a.txt": "create", "b.txt": "create"}
    assert _shas(built)["a.txt"] != _shas(built)["b.txt"]
    # no edit, so a rebuild repeats the digests exactly: nothing time-dependent is in them
    assert _shas(change_set.build(str(repo), "two twins again", _why())) == _shas(built)


def test_a_rebuild_after_an_edit_moves_that_digest(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    first = change_set.build(str(repo), "three", _why())

    (repo / "edit.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    second = change_set.build(str(repo), "three and four", _why())

    assert second.id != first.id
    assert _ops(first) == _ops(second) == {"edit.txt": "modify"}
    assert _shas(first)["edit.txt"] != _shas(second)["edit.txt"]
    # the older record keeps the digest it was built with: nothing rewrote history
    reloaded = change_set.load(first.id)
    assert reloaded is not None and reloaded.files[0].diff_sha == _shas(first)["edit.txt"]


def test_verify_current_names_the_path_that_moved(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = change_set.build(str(repo), "three", _why())
    assert _read().verify_current(built) == []

    (repo / "edit.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    drifted = _read().verify_current(built.id)
    assert [row["path"] for row in drifted] == ["edit.txt"]
    assert drifted[0]["recorded"] == _shas(built)["edit.txt"]
    assert drifted[0]["current"] != drifted[0]["recorded"]


def test_verify_current_reports_a_path_that_left_the_diff(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = change_set.build(str(repo), "three", _why())

    assert _git(repo, "restore", "edit.txt").returncode == 0
    drifted = _read().verify_current(built)

    assert [row["path"] for row in drifted] == ["edit.txt"]
    assert drifted[0]["current"] is None


def test_the_store_holds_no_file_content(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nsecret-payload\n", encoding="utf-8")

    built = change_set.build(str(repo), "the payload line", _why())

    stored = json.loads((store / f"{built.id}.json").read_text(encoding="utf-8"))
    assert stored["files"][0]["diff_sha"] == _shas(built)["edit.txt"]
    assert "secret-payload" not in json.dumps(stored)


def test_provenance_and_state_survive_a_reload(repo, store):
    """The session that built the change set is gone; the why is not."""
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = change_set.build(str(repo), "three", _why("because the reviewer asked"))

    loaded = change_set.load(built.id)

    assert loaded is not None
    assert loaded.provenance.session_id == "s-1"
    assert loaded.provenance.agent_id == "a-1"
    assert loaded.provenance.why == "because the reviewer asked"
    assert loaded["provenance"]["why"] == "because the reviewer asked"
    assert dict(loaded.provenance) == _why("because the reviewer asked")


def test_a_repo_config_cannot_reshape_the_digests(repo, store):
    """A prefix form or a diff algorithm set inside the repo would otherwise move every
    digest the change set recorded, and verify_current would report drift that is not there."""
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    before = _shas(change_set.build(str(repo), "before the config", _why()))

    assert _git(repo, "config", "diff.noprefix", "true").returncode == 0
    assert _git(repo, "config", "diff.algorithm", "histogram").returncode == 0

    assert _shas(change_set.build(str(repo), "after the config", _why())) == before


def test_a_summary_is_required(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    with pytest.raises(change_set.ChangeSetError):
        change_set.build(str(repo), "   ", _why())


def test_a_why_is_required(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    with pytest.raises(change_set.ChangeSetError):
        change_set.build(str(repo), "three", {"session_id": "s-1", "agent_id": "a-1"})
    with pytest.raises(change_set.ChangeSetError):
        change_set.build(str(repo), "three", {"session_id": "s-1", "why": "   "})


def test_an_unknown_provenance_field_is_refused(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    raw = dict(_why(), mood="hopeful")

    with pytest.raises(change_set.ChangeSetError):
        change_set.build(str(repo), "three", raw)


def test_a_workspace_that_is_not_a_repo_is_refused(tmp_path, store):
    change_set = _cs()
    plain = tmp_path / "plain"
    plain.mkdir()

    with pytest.raises(change_set.ChangeSetError):
        change_set.build(str(plain), "nothing to read", _why())


def test_a_repo_without_a_commit_is_still_described(tmp_path, store):
    change_set = _cs()
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert _git(fresh, "init", "-q").returncode == 0
    (fresh / "first.txt").write_text("hello\n", encoding="utf-8")
    assert _git(fresh, "add", "first.txt").returncode == 0

    built = change_set.build(str(fresh), "the first file", _why())

    assert _ops(built) == {"first.txt": "create"}
    assert _shas(built)["first.txt"].startswith("sha256:")


def test_a_rename_is_reported_once_at_its_new_path(repo, store):
    change_set = _cs()
    assert _git(repo, "mv", "untouched.txt", "moved.txt").returncode == 0

    built = change_set.build(str(repo), "renamed", _why())

    assert _ops(built) == {"moved.txt": "modify"}


def test_state_moves_and_an_unknown_state_is_refused(repo, store):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = change_set.build(str(repo), "three", _why())

    moved = change_set.set_state(built.id, "published")
    after_move = change_set.load(built.id)
    assert after_move is not None and after_move.state == "published"
    assert moved is not None and moved.state == "published"
    assert change_set.set_state("cs-absent", "review") is None
    with pytest.raises(change_set.ChangeSetError):
        change_set.set_state(built.id, "shipped")
    still = change_set.load(built.id)
    assert still is not None and still.state == "published"


def test_load_returns_none_for_an_id_that_is_not_there(repo, store):
    change_set = _cs()
    assert change_set.load("cs-20260101T000000Z-deadbeef") is None
    store.mkdir(parents=True, exist_ok=True)
    (store / "cs-20260101T000000Z-deadbeef.json").write_text("{ not json", encoding="utf-8")
    assert change_set.load("cs-20260101T000000Z-deadbeef") is None


def test_load_refuses_an_id_that_would_leave_the_store(store):
    change_set = _cs()
    for bad in ("../registry", "a/b", ".", "", "cs-1/../../x"):
        assert change_set.load(bad) is None


def test_list_for_separates_two_workspaces_and_orders_newest_first(tmp_path, store):
    change_set = _cs()
    first_repo = _make_repo(tmp_path / "one")
    second_repo = _make_repo(tmp_path / "two")
    (first_repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (second_repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    older = change_set.build(str(first_repo), "older", _why())
    time.sleep(0.01)
    newer = change_set.build(str(first_repo), "newer", _why())
    change_set.build(str(second_repo), "elsewhere", _why())

    mine = _read().list_for(str(first_repo))
    assert [entry.summary for entry in mine] == ["newer", "older"]
    assert [entry.id for entry in mine] == [newer.id, older.id]
    assert [entry.summary for entry in _read().list_for(str(second_repo))] == ["elsewhere"]
    assert _read().list_for(str(tmp_path / "absent")) == []


def test_a_symlink_to_the_workspace_reaches_the_same_records(repo, tmp_path, store):
    change_set = _cs()
    link = tmp_path / "link"
    link.symlink_to(repo, target_is_directory=True)
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    built = change_set.build(str(repo), "three", _why())

    assert [entry.id for entry in _read().list_for(str(link))] == [built.id]

    (repo / "edit.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    through_link = change_set.build(str(link), "four through the link", _why())
    assert through_link.workspace_id == built.workspace_id
    assert len(_read().list_for(str(repo))) == 2


def test_a_nested_workspace_sees_only_its_own_paths(repo, tmp_path, store):
    change_set = _cs()
    inner = repo / "inner"
    inner.mkdir()
    (inner / "inside.txt").write_text("inside\n", encoding="utf-8")
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    built = change_set.build(str(inner), "inside only", _why())

    assert [entry.path for entry in built.files] == ["inner/inside.txt"]


# Who else is in this file


def _why_by(agent_id: str, text: str = "the wave asked for a described publish") -> dict:
    return {"session_id": f"s-{agent_id}", "agent_id": agent_id, "why": text}


def _two_editing_repos(tmp_path, *names: str) -> list[Path]:
    """One committed repo per name, every one of them editing the same relative path."""
    repos = [_make_repo(tmp_path / name) for name in names]
    for repo in repos:
        (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    return repos


def test_claims_name_every_run_in_a_path_and_since_when(tmp_path, store):
    """Given two runs editing one path; Then a claim per run, each with its own moment."""
    change_set = _cs()
    first, second = _two_editing_repos(tmp_path, "one", "two")
    older = change_set.build(str(first), "older", _why_by("a-1"))
    time.sleep(0.01)
    newer = change_set.build(str(second), "newer", _why_by("a-2"))

    held = _read().claims_by_path(["edit.txt"])

    claims = held["edit.txt"]
    assert [claim.change_set_id for claim in claims] == [older.id, newer.id]
    assert [claim.agent_id for claim in claims] == ["a-1", "a-2"]
    assert claims[0].since < claims[1].since, "the moment the diff was taken is what orders them"
    assert all(claim.state == "draft" and claim.path == "edit.txt" for claim in claims)
    assert claims[0].op == "modify"
    assert claims[0].diff_sha.startswith("sha256:")


def test_claims_drop_a_workspace_own_sets_and_the_paths_nobody_asked_about(tmp_path, store):
    """Given two runs; Then a named tree is not in conflict with itself, and bounds are read."""
    change_set = _cs()
    first, second = _two_editing_repos(tmp_path, "one", "two")
    change_set.build(str(first), "mine", _why_by("a-1"))
    change_set.build(str(second), "theirs", _why_by("a-2"))

    alone = _read().claims_by_path(["edit.txt"], exclude_workspace=str(first))

    assert [claim.agent_id for claim in alone["edit.txt"]] == ["a-2"]
    assert _read().claims_by_path(["untouched.txt"]) == {}


def test_a_rejected_set_holds_nothing(tmp_path, store):
    """Given an abandoned set; Then it is gone from the answer a reader acts on."""
    change_set = _cs()
    first, second = _two_editing_repos(tmp_path, "one", "two")
    change_set.build(str(first), "mine", _why_by("a-1"))
    abandoned = change_set.build(str(second), "theirs", _why_by("a-2"))

    change_set.set_state(abandoned.id, "rejected")

    held = _read().claims_by_path(["edit.txt"])
    assert [claim.agent_id for claim in held["edit.txt"]] == ["a-1"]
    # A landing is not a claim either, but it is still shown: it holds the path's history.
    change_set.set_state(abandoned.id, "published")
    assert len(_read().claims_by_path(["edit.txt"])["edit.txt"]) == 2


def test_conflicts_name_a_holding_run_and_a_landing_newer_than_the_record(tmp_path, store):
    """Given four runs on one path; Then one is met and one is not, and the reason is the time."""
    change_set = _cs()
    landed_early, mine, holding, landed_late = _two_editing_repos(
        tmp_path, "early", "mine", "holding", "late"
    )
    before = change_set.build(str(landed_early), "landed before mine was taken", _why_by("a-4"))
    change_set.set_state(before.id, "published")
    taken = change_set.build(str(mine), "mine", _why_by("a-1"))
    time.sleep(0.01)
    peer = change_set.build(str(holding), "still in the file", _why_by("a-2"))
    after = change_set.build(str(landed_late), "landed after my record", _why_by("a-3"))
    change_set.set_state(after.id, "published")

    met = _read().conflicts(taken)

    assert set(met) == {"edit.txt"}
    assert [claim.change_set_id for claim in met["edit.txt"]] == [peer.id, after.id]
    assert [claim.state for claim in met["edit.txt"]] == ["draft", "published"]
    assert before.id not in [claim.change_set_id for claim in met["edit.txt"]], (
        "a landing older than this set was already on the branch when the diff was taken"
    )


def test_conflicts_leave_two_sets_of_one_workspace_alone(repo, store):
    """Given consecutive sets in one tree on one path; Then one agent's own sequencing is not a
    collision, because reporting it would make the notice meaningless."""
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    change_set.build(str(repo), "first", _why_by("a-1"))
    second = change_set.build(str(repo), "second", _why_by("a-1"))

    assert _read().conflicts(second) == {}


def test_landing_carries_its_own_time_and_keeps_it(repo, store):
    """Given a set that lands; Then the record carries when, and a later move does not erase it."""
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = change_set.build(str(repo), "three", _why())

    assert change_set.load(built.id).published_at == ""
    landed = change_set.set_state(built.id, "published")
    assert landed is not None
    assert landed.published_at
    moved = change_set.set_state(built.id, "review")
    assert moved is not None
    assert moved.published_at == landed.published_at


def test_one_reader_of_the_tree_serves_the_store_and_the_checker(repo, store):
    """Given an edited tree; Then `core.change_set.read_files` names it, digest and all."""
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    files = change_set.read_files(str(repo))

    assert [entry.path for entry in files] == ["edit.txt"]
    assert _ops(change_set.build(str(repo), "three", _why())) == {"edit.txt": "modify"}


def test_the_current_read_asks_the_store_and_no_private_helper(repo, store, monkeypatch):
    """Given a stored set; Then verify_current asks `read_files`, so a private reach is gone."""
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = change_set.build(str(repo), "three", _why())
    asked: list[str] = []
    real = change_set.read_files

    def spy(workspace_id: str):
        asked.append(workspace_id)
        return real(workspace_id)

    monkeypatch.setattr(change_set, "read_files", spy)

    assert _read().verify_current(built) == []
    assert asked == [built.workspace_id]

    (repo / "edit.txt").write_text("one\ntwo\nchanged\n", encoding="utf-8")
    drifted = _read().verify_current(built)

    assert [row["path"] for row in drifted] == ["edit.txt"]
    assert drifted[0]["current"] != drifted[0]["recorded"]
