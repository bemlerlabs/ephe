"""tests/test_change_set_lifecycle.py — a change set runs a loop, and stays the same set.

`core/change_set` stores the record and `core/review_gate` holds the verdicts, but neither
names the life between them: an approval left the record reading `draft`, and a set a reviewer
sent back could only be replaced by reading the tree again under a new id, which took the
provenance with it. Every case here drives that loop against a git repo and a store built
inside the test's own tmp directory, so the owner's real ``~/.ephe`` is never the target and
the real review ledger is never read.

The load-bearing part is `amend`: the id, the workspace, the provenance and the moment the set
was first recorded all survive a re-read of the tree, and the set stands back in draft so an
approval the earlier bytes earned cannot carry the ones that replaced them.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _cs():
    from core import change_set

    return change_set


def _loop():
    from core import change_set_lifecycle

    return change_set_lifecycle


def _gate():
    from core import review_gate

    return review_gate


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _commit(repo: Path, message: str = "init") -> None:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "user.email=ephe@test",
         "-c", "user.name=ephe", "commit", "-q", "-m", message],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    assert _git(path, "init", "-q").returncode == 0
    (path / "edit.txt").write_text("one\ntwo\n", encoding="utf-8")
    assert _git(path, "add", "-A").returncode == 0
    _commit(path)
    return path


def _why(text: str = "the wave asked for a described publish") -> dict:
    return {"session_id": "s-1", "agent_id": "a-1", "why": text}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A private change-set store and a private, in-memory review ledger."""
    change_set = _cs()
    gate = _gate()
    target = tmp_path / "changesets"
    monkeypatch.setenv("EPHE_CHANGESETS_DIR", str(target))
    monkeypatch.setattr(change_set, "CHANGESETS_DIR", target)
    monkeypatch.setattr(gate, "_default_ledger", gate.ReviewLedger(None))
    return target


@pytest.fixture
def repo(tmp_path, store):
    return _make_repo(tmp_path / "repo")


def _draft(repo: Path):
    change_set = _cs()
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    return change_set.build(str(repo), "add a third line", _why())


# The vocabulary


def test_approved_is_a_state_between_review_and_published():
    assert _cs().STATES == ("draft", "review", "approved", "published", "rejected")


def test_published_is_terminal_and_the_review_draft_pair_closes():
    loop = _loop()
    assert loop.TRANSITIONS["published"] == frozenset()
    assert loop.may_move("approved", "draft")
    assert loop.may_move("review", "draft")
    assert not loop.may_move("draft", "published")
    assert loop.STATIONS == ("draft", "review", "approved", "published")


def test_a_rejected_set_sits_at_the_review_station():
    loop = _loop()
    stations = loop.stations_of("rejected")
    assert [row["name"] for row in stations] == list(loop.STATIONS)
    assert [row["name"] for row in stations if row["current"]] == ["review"]
    assert [row["name"] for row in stations if row["done"]] == ["draft", "review"]


# Moving


def test_a_move_the_loop_allows_is_written(repo, store):
    loop = _loop()
    built = _draft(repo)
    moved = loop.move(built.id, "review")
    assert moved.state == "review"
    assert _cs().load(built.id).state == "review"


def test_an_illegal_move_is_refused_and_nothing_is_written(repo, store):
    loop = _loop()
    built = _draft(repo)
    with pytest.raises(loop.LifecycleError):
        loop.move(built.id, "published")
    assert _cs().load(built.id).state == "draft"


def test_published_is_final_to_the_loop(repo, store):
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")
    loop.move(built.id, "published")
    with pytest.raises(loop.LifecycleError):
        loop.move(built.id, "draft")


def test_a_move_on_an_unknown_id_answers_nothing(repo, store):
    assert _loop().move("cs-absent", "review") is None


def test_an_unknown_state_is_refused(repo, store):
    loop = _loop()
    built = _draft(repo)
    with pytest.raises(loop.LifecycleError):
        loop.move(built.id, "sideways")


def test_a_verdict_settles_the_set_and_a_late_one_does_not(repo, store):
    loop = _loop()
    built = _draft(repo)
    assert loop.settle(built.id, "approve") is True
    assert _cs().load(built.id).state == "approved"
    # Push it past the point a verdict can move, then file another one: the verdict stands,
    # the move does not, and the loop says so instead of raising into the route.
    loop.move(built.id, "published")
    assert loop.settle(built.id, "reject") is False
    assert _cs().load(built.id).state == "published"


# Amending


def test_amend_keeps_the_id_the_provenance_and_the_moment(repo, store):
    loop = _loop()
    built = _draft(repo)
    (repo / "edit.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    amended = loop.amend(built.id)

    assert amended is not None
    assert amended.id == built.id
    assert amended.workspace_id == built.workspace_id
    assert amended.provenance == built.provenance
    assert amended.created_at == built.created_at
    assert amended.state == "draft"
    assert amended.files[0].diff_sha != built.files[0].diff_sha
    assert _cs().load(built.id) == amended


def test_amend_stands_an_approved_set_back_in_draft(repo, store):
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")
    amended = loop.amend(built.id)
    assert amended.state == "draft"
    # The move an approval earned is gone with the bytes it covered.
    assert not loop.may_move(amended.state, "published")


def test_amend_reads_the_tree_again_under_the_same_summary(repo, store):
    loop = _loop()
    built = _draft(repo)
    (repo / "fresh.txt").write_text("brand new\n", encoding="utf-8")
    amended = loop.amend(built.id)
    assert [change.path for change in amended.files] == ["edit.txt", "fresh.txt"]
    assert amended.summary == built.summary
    renamed = loop.amend(built.id, summary="a better sentence")
    assert renamed.summary == "a better sentence"


def test_amend_refuses_a_published_set(repo, store):
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")
    loop.move(built.id, "published")
    with pytest.raises(loop.LifecycleError):
        loop.amend(built.id)
    assert _cs().load(built.id).state == "published"


def test_amend_on_an_unknown_id_answers_nothing(repo, store):
    assert _loop().amend("cs-absent") is None


def test_amend_on_a_tree_that_is_gone_raises_the_store_error(tmp_path, store):
    loop = _loop()
    repo = _make_repo(tmp_path / "gone")
    (repo / "edit.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    built = _cs().build(str(repo), "add a third line", _why())
    import shutil

    shutil.rmtree(repo)
    with pytest.raises(_cs().ChangeSetError):
        loop.amend(built.id)


# The view


def test_the_view_of_a_draft_offers_a_verdict_and_an_amend(repo, store):
    loop = _loop()
    built = _draft(repo)
    life = loop.view(built, author="a-1")
    assert life["state"] == "draft"
    assert life["author"] == "a-1"
    assert life["verdict"] is None
    assert life["reasons"] == []
    assert life["decidable"] is True
    assert life["amendable"] is True
    assert life["withdraw"] == []
    assert life["can_publish"] is False
    assert [row["name"] for row in life["stations"] if row["current"]] == ["draft"]


def test_the_view_carries_the_last_verdict_and_its_located_reasons(repo, store):
    loop = _loop()
    gate = _gate()
    built = _draft(repo)
    target = gate.ChangeSet(
        change_set_id=built.id, author="a-1", paths=tuple(c.path for c in built.files)
    )
    gate.submit(target, "request_changes", "a-2", [{"path": "edit.txt", "line": 3,
                                                   "why": "the third line needs a reason"}])
    loop.settle(built.id, "request_changes")

    life = loop.view(_cs().load(built.id), author="a-1")

    assert life["state"] == "review"
    assert life["verdict"]["reviewer"] == "a-2"
    assert life["reasons"] == [
        {"path": "edit.txt", "line": 3, "why": "the third line needs a reason"}
    ]
    assert life["withdraw"] == ["draft"]
    assert [row["name"] for row in life["stations"] if row["current"]] == ["review"]


def test_the_view_lets_only_an_approved_set_publish(repo, store):
    loop = _loop()
    gate = _gate()
    built = _draft(repo)
    target = gate.ChangeSet(
        change_set_id=built.id, author="a-1", paths=tuple(c.path for c in built.files)
    )
    gate.submit(target, "approve", "a-2", [{"path": "edit.txt", "line": 1, "why": "reads well"}])

    assert loop.view(built)["can_publish"] is False, "the state has not caught up yet"
    loop.settle(built.id, "approve")
    assert loop.view(_cs().load(built.id))["can_publish"] is True


def test_the_view_of_a_published_set_offers_no_move(repo, store):
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")
    loop.move(built.id, "published")
    life = loop.view(_cs().load(built.id))
    assert life["decidable"] is False
    assert life["amendable"] is False
    assert life["withdraw"] == []
    assert [row["name"] for row in life["stations"] if row["current"]] == ["published"]


# Taking a landing back


def test_a_landing_is_recorded_with_the_oid_it_wrote(repo, store):
    """Given a set that lands; Then the record names the commit the publish moved to."""
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")

    landed = loop.move(built.id, "published", "f" * 40)

    assert landed.published_oid == "f" * 40
    assert _cs().load(built.id).published_oid == "f" * 40


def test_a_published_set_comes_back_to_a_draft_through_the_named_revert(repo, store):
    """Given a landing; Then the revert returns a draft and keeps the mark of what it undid."""
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")
    loop.move(built.id, "published", "f" * 40)

    reverted = loop.unpublish(built.id)

    assert reverted.state == loop.REVERT_TO == "draft"
    stored = _cs().load(built.id)
    assert stored.state == "draft"
    assert stored.published_at, "the moment it landed stays on the record"
    assert stored.published_oid == "f" * 40, "and so does the commit it landed as"
    assert loop.may_move(stored.state, "review"), "the loop carries the set again"


def test_no_legal_move_leads_off_the_end_of_the_line(repo, store):
    """Given a published set; Then the forwards table is still empty there, as the view says."""
    loop = _loop()
    built = _draft(repo)
    loop.move(built.id, "approved")
    loop.move(built.id, "published")

    with pytest.raises(loop.LifecycleError):
        loop.move(built.id, "draft")
    assert loop.TRANSITIONS["published"] == frozenset()
    assert loop.AMENDABLE == frozenset({"draft", "review", "approved", "rejected"})


def test_a_revert_of_a_set_that_never_landed_is_refused(repo, store):
    """Given a draft; Then there is no landing to take back and nothing is written."""
    loop = _loop()
    built = _draft(repo)

    with pytest.raises(loop.LifecycleError):
        loop.unpublish(built.id)

    assert _cs().load(built.id).state == "draft"


def test_a_revert_on_an_unknown_id_answers_nothing(repo, store):
    assert _loop().unpublish("cs-absent") is None


# An amend needs something to describe


def test_an_amend_of_a_tree_that_holds_no_change_is_refused(repo, store):
    """Given a set whose tree reads back clean; Then the amend is refused and nothing is written."""
    loop = _loop()
    built = _draft(repo)
    (repo / "edit.txt").write_text("one\ntwo\n", encoding="utf-8")

    with pytest.raises(loop.LifecycleError):
        loop.amend(built.id)

    assert _cs().load(built.id) == built, "the record is where it was, with its own diff still"


def test_an_amend_that_finds_a_change_records_it(repo, store):
    """Given a further edit; Then the amend reads it, so the guard above is not the whole amend."""
    loop = _loop()
    built = _draft(repo)
    (repo / "edit.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    amended = loop.amend(built.id)

    assert [change.op for change in amended.files] == ["modify"]
    assert amended.files[0].diff_sha != built.files[0].diff_sha
