"""The isolation verbs of `ephe_cli`: agents, changes, show, review, publish, reap.

`tests/test_ephe_cli_surface.py` pins the parser shape these verbs hang off; this file
pins what they do. Every case drives `ephe_cli.cmd_*` in-process through the real
parser, against a throwaway register, change-set store, review ledger and git repo — the
checkout at the root of this worktree is never a target, and the operator's own
``~/.ephe`` stores are never read.

The seam under test is ``core/_cli_isolation.py``: it reads the four isolation modules
(``workspace_lifecycle``, ``change_set``, ``review_gate``, ``atomic_publish``) and prints
what they report. Where a case proves a refusal, it asserts the *refusing* module's
sentence survives into the CLI output — a verb that swallowed it would look like a bug in
the operator's terminal instead of a gate doing its job.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ephe_cli

STATE_TAG = "sha256:"


# the throwaway stores


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Register, change-set store and review ledger all under tmp_path."""
    from core import change_set as store
    from core import review_gate as gate
    from core import workspace_lifecycle as wl

    monkeypatch.setattr(wl, "WORKSPACES_DIR", tmp_path / "managed")
    monkeypatch.setattr(wl, "REPO_ROOT", tmp_path / "checkout")
    monkeypatch.setattr(store, "CHANGESETS_DIR", tmp_path / "changesets")
    ledger = gate.ReviewLedger(tmp_path / "reviews.jsonl")
    monkeypatch.setattr("core._cli_isolation._ledger", lambda: ledger)
    return Stores(tmp_path, wl, store, gate, ledger)


class Stores:
    """The four stores a case needs, bundled so the fixture stays a fixture."""

    def __init__(self, tmp_path, wl, store, gate, ledger) -> None:
        self.tmp_path = tmp_path
        self.wl = wl
        self.store = store
        self.gate = gate
        self.ledger = ledger
        self.managed = tmp_path / "managed"


def run(*argv: str) -> int:
    """One CLI call through the real parser, the way `main()` dispatches it."""
    args = ephe_cli.build_parser().parse_args(list(argv))
    return args.func(args)


def git(repo: Path, *argv: str) -> str:
    done = subprocess.run(["git", *argv], cwd=repo, capture_output=True, text=True, check=False)
    assert done.returncode == 0, f"git {argv} failed: {done.stderr}"
    return done.stdout


def new_repo(root: Path) -> Path:
    """A repository on ``main`` with two tracked files and one commit."""
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "cli@example.invalid")
    git(repo, "config", "user.name", "cli")
    (repo / "a.txt").write_text("A\n", encoding="utf-8")
    (repo / "b.txt").write_text("B\n", encoding="utf-8")
    git(repo, "add", "a.txt", "b.txt")
    git(repo, "commit", "-qm", "init")
    return repo


def gate_view(change):
    """The gate's view of a stored change set, through the seam's own conversion."""
    from core._cli_isolation import gate_change_set

    return gate_change_set(change)


def build_set(stores, repo: Path, *, agent: str = "author-agent", summary: str = "cli: one edit"):
    """A real stored change set: an edit in the tree, read by core/change_set.build."""
    (repo / "a.txt").write_text("A2\n", encoding="utf-8")
    return stores.store.build(
        str(repo),
        summary,
        {"session_id": "s-1", "agent_id": agent, "why": "the verbs need a set to read"},
    )


def approve(stores, change, reviewer: str = "rev-1", state: str = "approved") -> None:
    """The state a recorded approval leaves the set in: the ledger line and the state move.

    ``approved`` is the state `ephe review <id> approve` writes, and it is the state the
    publish gate reads — a helper that left the set anywhere else would pin a publish the web
    route refuses. ``state`` is overridable for the cases that move a set after its approval.
    """
    stores.ledger.submit(
        gate_view(change), stores.gate.APPROVE, reviewer, [stores.gate.Reason("a.txt", 1, "read it")]
    )
    stores.store.set_state(change.id, state)


def register_row(stores, tree: Path, **overrides) -> dict:
    """One register row, written the way core/workspace_lifecycle writes it."""
    row = {
        "id": overrides.pop("id", "9f3c1a2b"),
        "path": str(tree),
        "branch": overrides.pop("branch", "ws/agent-a-9f3c1a2b"),
        "state": overrides.pop("state", "ready"),
        "owner": overrides.pop("owner", "agent-a"),
        "created_at": overrides.pop("created_at", datetime.now(tz=timezone.utc).isoformat()),
        "pid": overrides.pop("pid", os.getpid()),
        **overrides,
    }
    stores.managed.mkdir(parents=True, exist_ok=True)
    stores.wl.register_file().write_text(json.dumps({"workspaces": [row]}), encoding="utf-8")
    return row


def an_exited_pid() -> int:
    """A pid that is certainly gone: a child started and reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


# ephe agents


def test_agents_says_so_when_no_workspace_is_live(stores, capsys):
    """
    GIVEN a machine whose register holds no live row
    WHEN `ephe agents` runs
    THEN one line names the register it read — no row, no invented example.
    """
    assert run("agents") == 0

    out = capsys.readouterr().out
    assert out.strip() == f"no live workspaces (register {stores.wl.register_file()})"


def test_agents_prints_id_owner_state_and_age_per_live_row(stores, capsys, tmp_path):
    """
    GIVEN one live row whose tree is a dirty checkout, created three hours ago
    WHEN `ephe agents` runs
    THEN one line carries its id, owner, git-refreshed state and age.
    """
    tree = new_repo(tmp_path)
    (tree / "a.txt").write_text("A3\n", encoding="utf-8")
    created = datetime.now(tz=timezone.utc) - timedelta(hours=3, minutes=4)
    row = register_row(stores, tree, created_at=created.isoformat())

    assert run("agents") == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"1 live workspace (register {stores.wl.register_file()})"
    assert out[1] == f"{row['id']}  agent-a  dirty  age 3h04m"


def test_agents_json_carries_every_row_and_the_register(stores, capsys, tmp_path):
    """
    GIVEN one live row
    WHEN `ephe agents --json` runs
    THEN the payload carries the register path, the count and the row's fields as data.
    """
    tree = new_repo(tmp_path)
    row = register_row(stores, tree)

    assert run("agents", "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["register"] == str(stores.wl.register_file())
    assert payload["workspaces"][0]["id"] == row["id"]
    assert payload["workspaces"][0]["age_seconds"] >= 0


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0s"), (42, "42s"), (59, "59s"), (60, "1m"), (1020, "17m"), (11040, "3h04m"),
     (183600, "2d03h"), (None, "?")],
)
def test_age_text_shortens_a_span_to_one_unit_pair(seconds, expected):
    """
    GIVEN a span in seconds
    WHEN it is rendered for the agents table
    THEN it reads as one unit pair, and an unknown span reads as a question mark.
    """
    from core._cli_isolation import age_text

    assert age_text(seconds) == expected


def test_agents_lists_a_row_whose_stamp_will_not_parse(stores, capsys, tmp_path):
    """
    GIVEN a register row whose created_at is not a stamp at all
    WHEN `ephe agents` runs
    THEN the row is still listed and its age reads as unknown, never as an age of zero.
    """
    tree = new_repo(tmp_path)
    row = register_row(stores, tree, created_at="not-a-stamp")

    assert run("agents") == 0

    assert capsys.readouterr().out.splitlines()[1] == f"{row['id']}  agent-a  ready  age ?"


def test_agents_reads_a_stamp_without_a_timezone(stores, capsys, tmp_path):
    """
    GIVEN a row written before the stamps carried an offset
    WHEN `ephe agents` runs
    THEN the stamp is read as UTC and the row still gets an age.
    """
    tree = new_repo(tmp_path)
    (tree / "a.txt").write_text("A5\n", encoding="utf-8")
    stamp = (datetime.now(tz=timezone.utc) - timedelta(minutes=17)).replace(tzinfo=None)
    register_row(stores, tree, created_at=stamp.isoformat())

    assert run("agents") == 0

    age = capsys.readouterr().out.splitlines()[1].split("age ")[-1]
    assert age.endswith("m") and age != "?"


@pytest.mark.parametrize(
    "digest,expected",
    [("sha256:" + "ab" * 32, "sha256:" + "ab" * 6), ("deadbeef", "deadbeef"), ("", "no digest")],
)
def test_short_sha_keeps_the_algorithm_and_twelve_hex(digest, expected):
    """
    GIVEN a stored diff digest, a bare one and none at all
    WHEN the table renders it
    THEN the algorithm tag survives, twelve hex characters follow, and an empty one says so.
    """
    from core._cli_isolation import short_sha

    assert short_sha(digest) == expected


def test_changes_refuses_an_empty_workspace_argument(stores, capsys):
    """
    GIVEN an empty workspace token
    WHEN `ephe changes ""` runs
    THEN it is a usage error (exit 2) naming what a workspace may be.
    """
    assert run("changes", "") == 2

    captured = capsys.readouterr()
    assert "a workspace is an id or a path" in captured.err
    assert "ids come from `ephe agents`" in captured.err


# ephe changes


def test_changes_lists_a_workspaces_sets_newest_first_with_digests(stores, capsys, tmp_path):
    """
    GIVEN a workspace with two stored change sets
    WHEN `ephe changes <path>` runs
    THEN both are listed, newest first, with the file count and the diff-sha prefix.
    """
    repo = new_repo(tmp_path)
    first = build_set(stores, repo, summary="cli: the first edit")
    # The store orders by its own creation stamp, so two builds have to be a moment
    # apart for "newest first" to be a fact rather than a tie.
    time.sleep(0.02)
    second = build_set(stores, repo, summary="cli: the second edit")

    assert run("changes", str(repo)) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"2 change sets for {repo} (newest first)"
    assert second.id in out[1] and "1 file" in out[1] and second.summary in out[1]
    assert first.id in out[3] and first.summary in out[3]
    digest = second.files[0].diff_sha
    assert digest.startswith(STATE_TAG)
    assert out[2].strip() == f"modify  a.txt  {STATE_TAG}{digest[len(STATE_TAG):][:12]}"


def test_changes_accepts_a_register_id_for_the_workspace(stores, capsys, tmp_path):
    """
    GIVEN a live register row
    WHEN `ephe changes <id>` runs
    THEN the id resolves to the tree path and that workspace's sets are listed.
    """
    tree = new_repo(tmp_path)
    row = register_row(stores, tree)
    change = build_set(stores, tree)

    assert run("changes", row["id"]) == 0

    out = capsys.readouterr().out
    assert f"for {tree} (newest first)" in out
    assert change.id in out


def test_changes_says_so_when_a_workspace_has_no_change_set(stores, capsys, tmp_path):
    """
    GIVEN a workspace that exists and holds nothing
    WHEN `ephe changes <path>` runs
    THEN it reports that fact instead of an empty table.
    """
    repo = new_repo(tmp_path)

    assert run("changes", str(repo)) == 0

    assert capsys.readouterr().out.strip() == f"no change sets for {repo}"


def test_changes_refuses_a_workspace_it_cannot_find(stores, capsys):
    """
    GIVEN a token that is neither a live id nor a directory
    WHEN `ephe changes ghost` runs
    THEN the CLI exits 1 with the refusal and the fix that names `ephe agents`.
    """
    assert run("changes", "ghost") == 1

    captured = capsys.readouterr()
    assert "unknown workspace 'ghost'" in captured.err
    assert "ephe agents" in captured.err


# ephe review


def test_review_records_an_approve_and_moves_the_set_out_of_draft(stores, capsys, tmp_path):
    """
    GIVEN a draft change set and a reviewer who is not its author
    WHEN `ephe review <id> approve` runs with a located reason
    THEN the verdict is in the ledger, the reason is printed, and the set reads `approved` —
    the state the publish gate consults, so an approval given here lands and one given on the
    Workspaces page leaves the same record.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)

    assert run("review", change.id, "approve", "--reviewer", "w2-arch",
               "--reason", "a.txt:1:the rename case is not covered") == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"approve recorded for {change.id} by w2-arch (1 reason)"
    assert out[1].strip() == "a.txt:1  the rename case is not covered"
    assert out[2] == f"{change.id} state: draft -> approved"
    assert stores.ledger.may_publish(gate_view(change)) is True
    assert stores.store.load(change.id).state == "approved"


def test_review_refuses_a_self_approval_and_records_nothing(stores, capsys, tmp_path):
    """
    GIVEN a change set whose author names the same reviewer
    WHEN that reviewer approves it
    THEN the gate's refusal is printed, the exit code is 1, and the ledger stays empty.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo, agent="author-agent")

    assert run("review", change.id, "approve", "--reviewer", "author-agent",
               "--reason", "a.txt:1:my own work") == 1

    captured = capsys.readouterr()
    assert "authored" in captured.err and "cannot approve it" in captured.err
    assert "nothing was recorded" in captured.err
    assert stores.ledger.entries() == []
    assert stores.store.load(change.id).state == "draft"


def test_review_refuses_a_reason_outside_the_change_set(stores, capsys, tmp_path):
    """
    GIVEN a reason naming a path the change set does not touch
    WHEN the verdict is filed
    THEN the gate refuses it by name and nothing is recorded.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)

    assert run("review", change.id, "approve", "--reviewer", "w2-arch",
               "--reason", "b.txt:4:nothing here") == 1

    captured = capsys.readouterr()
    assert "does not touch b.txt:4" in captured.err
    assert stores.ledger.entries() == []


def test_review_refuses_a_reason_that_is_not_path_line_why(stores, capsys, tmp_path):
    """
    GIVEN a --reason without a line and a why
    WHEN the verdict is filed
    THEN it is a usage error (exit 2) naming the shape and an example.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)

    assert run("review", change.id, "approve", "--reviewer", "w2-arch", "--reason", "a.txt") == 2

    captured = capsys.readouterr()
    assert "a reason is path:line:why" in captured.err
    assert "--reason core/change_set.py:120" in captured.err


def test_review_refuses_a_line_number_below_one(stores, capsys, tmp_path):
    """
    GIVEN a reason whose line is zero
    WHEN the verdict is filed
    THEN the gate's own rule is printed as a usage error (exit 2).
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)

    assert run("review", change.id, "approve", "--reviewer", "w2-arch",
               "--reason", "a.txt:0:nowhere") == 2

    assert "line number above zero" in capsys.readouterr().err


@pytest.mark.parametrize(
    "decision,expected_state",
    [("request-changes", "review"), ("reject", "rejected")],
)
def test_review_moves_the_set_the_way_the_decision_says(stores, capsys, tmp_path, decision, expected_state):
    """
    GIVEN a draft change set
    WHEN the reviewer requests changes or rejects it
    THEN the recorded verdict is printed and the set reaches the state that decision means.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)

    assert run("review", change.id, decision, "--reviewer", "w2-arch",
               "--reason", "a.txt:2:not yet") == 0

    verdict = stores.gate.REQUEST_CHANGES if decision == "request-changes" else stores.gate.REJECT
    assert f"{verdict} recorded for {change.id} by w2-arch (1 reason)" in capsys.readouterr().out
    assert stores.store.load(change.id).state == expected_state
    assert stores.ledger.may_publish(gate_view(change)) is False


def test_review_counts_every_reason_it_is_given(stores, capsys, tmp_path):
    """
    GIVEN two located reasons
    WHEN the verdict is filed
    THEN both are printed under a count of two.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)

    assert run("review", change.id, "request-changes", "--reviewer", "w2-arch",
               "--reason", "a.txt:1:first", "--reason", "a.txt:2:second") == 0

    out = capsys.readouterr().out
    assert "(2 reasons)" in out
    assert "a.txt:1  first" in out and "a.txt:2  second" in out


def test_review_leaves_a_published_set_published(stores, capsys, tmp_path):
    """
    GIVEN a change set that already landed
    WHEN a later verdict is filed against it
    THEN the verdict is recorded and the state stays `published`, with a line saying so.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    stores.store.set_state(change.id, "published")
    landed = stores.store.load(change.id)

    assert run("review", change.id, "reject", "--reviewer", "w2-arch",
               "--reason", "a.txt:1:it should not have landed") == 0

    assert f"{change.id} stays published" in capsys.readouterr().out
    assert stores.store.load(change.id).state == landed.state


def test_review_refuses_a_change_set_whose_author_is_unrecorded(stores, capsys, tmp_path):
    """
    GIVEN a change set whose provenance names neither an agent nor a session
    WHEN a verdict is filed
    THEN the CLI reports that no author can be named, and records nothing.
    """
    repo = new_repo(tmp_path)
    (repo / "a.txt").write_text("A4\n", encoding="utf-8")
    change = stores.store.build(str(repo), "cli: anonymous", {"session_id": "", "agent_id": "", "why": "nobody"})

    assert run("review", change.id, "approve", "--reviewer", "w2-arch",
               "--reason", "a.txt:1:fine") == 1

    captured = capsys.readouterr()
    assert "records no author" in captured.err
    assert stores.ledger.entries() == []


def test_review_refuses_a_change_set_that_is_not_stored(stores, capsys):
    """
    GIVEN an id no store holds
    WHEN a verdict is filed
    THEN the refusal names the store directory and points at `ephe changes`.
    """
    assert run("review", "cs-nosuch", "approve", "--reviewer", "w2-arch",
               "--reason", "a.txt:1:fine") == 1

    captured = capsys.readouterr()
    assert f"no change set 'cs-nosuch' in {stores.store.CHANGESETS_DIR}" in captured.err
    assert "ephe changes" in captured.err


# ephe publish


def test_publish_refuses_a_change_set_with_no_verdict(stores, capsys, tmp_path):
    """
    GIVEN an approved-by-nobody change set
    WHEN `ephe publish` runs
    THEN it refuses with "no verdict is recorded", exits 1, and the branch has not moved.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    before = git(repo, "rev-parse", "refs/heads/main")

    assert run("publish", change.id) == 1

    captured = capsys.readouterr()
    assert "may not publish: no verdict is recorded" in captured.err
    assert f"ephe review {change.id} approve" in captured.err
    assert git(repo, "rev-parse", "refs/heads/main") == before


def test_publish_refuses_a_change_set_whose_latest_verdict_is_not_an_approve(stores, capsys, tmp_path):
    """
    GIVEN a change set whose reviewer asked for changes
    WHEN `ephe publish` runs
    THEN the refusal names that verdict and its reviewer, and the branch has not moved.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    run("review", change.id, "request-changes", "--reviewer", "w2-arch", "--reason", "a.txt:1:not yet")
    before = git(repo, "rev-parse", "refs/heads/main")

    assert run("publish", change.id) == 1

    assert "the latest verdict is request_changes by w2-arch" in capsys.readouterr().err
    assert git(repo, "rev-parse", "refs/heads/main") == before


def test_publish_refuses_a_self_approval_it_finds_in_the_ledger(stores, capsys, tmp_path):
    """
    GIVEN a hand-written ledger line where the reviewer is the author
    WHEN `ephe publish` runs
    THEN the fail-closed answer stays a refusal, naming the self-approval.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    stores.ledger.path.write_text(
        json.dumps({
            "schema": 1,
            "change_set_id": change.id,
            "author": "author-agent",
            "verdict": "approve",
            "reviewer": "author-agent",
            "reasons": [{"path": "a.txt", "line": 1, "why": "mine"}],
        }) + "\n",
        encoding="utf-8",
    )

    assert run("publish", change.id) == 1

    assert "the approve is author-agent's own change set" in capsys.readouterr().err


def test_publish_refuses_a_verdict_filed_against_another_author(stores, capsys, tmp_path):
    """
    GIVEN a ledger approval recorded for a different author than the stored change set
    WHEN `ephe publish` runs
    THEN the mismatch is the refusal, because the gate compares the author it is handed.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    stores.ledger.submit(
        stores.gate.ChangeSet(change_set_id=change.id, author="someone-else"),
        stores.gate.APPROVE, "rev-1", [stores.gate.Reason("a.txt", 1, "read it")],
    )

    assert run("publish", change.id) == 1

    assert "filed against someone other than author-agent" in capsys.readouterr().err


def test_publish_dry_run_builds_the_tree_and_moves_nothing(stores, capsys, tmp_path):
    """
    GIVEN an approved change set
    WHEN `ephe publish --dry-run` runs
    THEN it prints what would land, moves no ref, and leaves the state where it was.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    before = (git(repo, "rev-parse", "refs/heads/main"), (repo / "a.txt").read_bytes())

    assert run("publish", change.id, "--dry-run") == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{change.id} -> main: dry run: 1 file(s) would publish to main"
    assert out[1].strip() == "a.txt"
    assert "no ref moved" in out[-1]
    assert (git(repo, "rev-parse", "refs/heads/main"), (repo / "a.txt").read_bytes()) == before
    assert stores.store.load(change.id).state == "approved"


def test_publish_lands_the_set_and_reports_the_state_move(stores, capsys, tmp_path):
    """
    GIVEN an approved change set whose workspace carries the edit
    WHEN `ephe publish` runs
    THEN the branch carries the workspace's bytes, the ref moved, and the state is published.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    before = git(repo, "rev-parse", "refs/heads/main")

    assert run("publish", change.id) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{change.id} -> main: published 1 file(s) to main"
    assert out[1].strip() == "a.txt"
    assert out[2] == f"{change.id} state: approved -> published"
    assert git(repo, "rev-parse", "refs/heads/main") != before
    assert git(repo, "show", "main:a.txt") == "A2\n"
    assert stores.store.load(change.id).state == "published"
    assert (repo / "a.txt").read_text(encoding="utf-8") == "A2\n"


def test_publish_refuses_a_change_set_that_already_landed(stores, capsys, tmp_path):
    """
    GIVEN a change set whose files are already on the branch
    WHEN `ephe publish` runs again
    THEN it refuses, because a second landing would commit an unchanged tree.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    assert run("publish", change.id) == 0
    capsys.readouterr()
    after = git(repo, "rev-parse", "refs/heads/main")

    assert run("publish", change.id) == 1

    captured = capsys.readouterr()
    assert f"{change.id} is already published" in captured.err
    assert "unchanged tree" in captured.err
    assert git(repo, "rev-parse", "refs/heads/main") == after


def test_publish_prints_the_rollback_an_abort_reports(stores, capsys, tmp_path, monkeypatch):
    """
    GIVEN a publish that fails between two files of the set
    WHEN `ephe publish` runs
    THEN the applied paths are empty, the rolled-back path is named, the ref is unchanged.
    """
    from core import atomic_publish as publisher

    repo = new_repo(tmp_path)
    (repo / "a.txt").write_text("A2\n", encoding="utf-8")
    (repo / "b.txt").write_text("B2\n", encoding="utf-8")
    change = stores.store.build(
        str(repo), "cli: two edits",
        {"session_id": "s-1", "agent_id": "author-agent", "why": "two files for one abort"},
    )
    approve(stores, change)
    before = git(repo, "rev-parse", "refs/heads/main")
    real_hook = publisher._file_boundary_hook

    def boom(path: str) -> None:
        real_hook(path)
        if path == "b.txt":
            raise publisher.PublishError("injected failure between a.txt and b.txt")

    monkeypatch.setattr(publisher, "_file_boundary_hook", boom)

    assert run("publish", change.id) == 1

    out = capsys.readouterr().out.splitlines()
    assert "aborted before publish: injected failure" in out[0]
    assert "rolled back before the ref moved (1 file):" in out
    assert out[out.index("rolled back before the ref moved (1 file):") + 1].strip() == "a.txt"
    assert out[-1] == "nothing landed: the target ref, its tree and the real object store are unchanged"
    assert git(repo, "rev-parse", "refs/heads/main") == before
    assert stores.store.load(change.id).state == "approved"


def test_publish_refuses_a_set_whose_workspace_is_gone(stores, capsys, tmp_path):
    """
    GIVEN an approved change set whose workspace directory has been removed
    WHEN `ephe publish` runs
    THEN it refuses before it builds anything, with the code the web route refuses with, and
    the state stays where the approval left it.
    """
    import shutil

    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    shutil.rmtree(repo)

    assert run("publish", change.id) == 1

    captured = capsys.readouterr()
    # The refusal has to arrive as a refusal — stderr, the route's own reason — and not as an
    # abort reported from halfway through a publish that only then found the tree missing.
    assert "no workspace to read it from" not in captured.out
    assert stores.store.load(change.id).state == "approved"

    from core import publish_readiness as preflight

    assert f"[{preflight.TREE_GONE}]" in captured.err
    assert "record the set again from a live tree" in captured.err


def test_publish_refuses_a_set_whose_tree_moved_after_it_was_recorded(stores, capsys, tmp_path):
    """
    GIVEN an approved change set and an edit made to its file after the record was taken
    WHEN `ephe publish` runs
    THEN it refuses with the code the web route refuses with, names the drifted path, and the
    branch has not moved: no surface ships bytes its own verifier never saw.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    before = git(repo, "rev-parse", "refs/heads/main")
    (repo / "a.txt").write_text("A3\n", encoding="utf-8")

    assert run("publish", change.id) == 1

    captured = capsys.readouterr()
    assert git(repo, "rev-parse", "refs/heads/main") == before
    assert stores.store.load(change.id).state == "approved"

    from core import publish_readiness as preflight

    assert f"may not publish [{preflight.TREE_MOVED}]" in captured.err
    assert "the tree moved after this set was recorded: a.txt" in captured.err


def test_publish_refuses_a_set_the_state_has_not_approved(stores, capsys, tmp_path):
    """
    GIVEN a set an amend stood back in draft after an approval was filed on it
    WHEN `ephe publish` runs
    THEN it refuses with the route's code for an unapproved set, and the branch has not moved.
    """
    from core import change_set_lifecycle as loop

    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    (repo / "a.txt").write_text("A3\n", encoding="utf-8")
    amended = loop.amend(change.id, summary=None)
    assert amended is not None and amended.state == "draft", "the amend is the state under test"
    before = git(repo, "rev-parse", "refs/heads/main")

    assert run("publish", change.id) == 1

    captured = capsys.readouterr()
    assert git(repo, "rev-parse", "refs/heads/main") == before
    assert stores.store.load(change.id).state == "draft"

    from core import publish_readiness as preflight

    assert f"may not publish [{preflight.WITHOUT_APPROVAL}]" in captured.err
    assert "draft" in captured.err


def test_the_terminal_and_the_route_refuse_one_set_for_one_reason(stores, capsys, tmp_path, monkeypatch):
    """
    GIVEN an approved set whose tree moved after the record was taken
    WHEN the route's publish handler and `ephe publish` are asked about that one set
    THEN both answer `publish_tree_moved`: one tree, one set, one answer, whichever surface asked.
    """
    import asyncio

    from core import publish_readiness as preflight
    from core import review_gate
    from server.refusals import Refused
    from server.routes.workspaces import publish_change_set

    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)
    (repo / "a.txt").write_text("A3\n", encoding="utf-8")
    # The route reads the gate's singleton, so hand it the file this case filed its verdict in.
    monkeypatch.setattr(review_gate, "_default_ledger", stores.ledger)

    with pytest.raises(Refused) as refused:
        asyncio.run(publish_change_set(change.id))

    assert refused.value.code == preflight.TREE_MOVED

    assert run("publish", change.id) == 1
    assert f"[{preflight.TREE_MOVED}]" in capsys.readouterr().err


def test_publish_json_prints_the_result_field_for_field(stores, capsys, tmp_path):
    """
    GIVEN an approved change set
    WHEN `ephe publish --json --dry-run` runs
    THEN the payload carries every PublishResult field and the target that was asked for.
    """
    repo = new_repo(tmp_path)
    change = build_set(stores, repo)
    approve(stores, change)

    assert run("publish", change.id, "--dry-run", "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["change_set"] == change.id
    assert payload["target"] == "main"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["applied"] == ["a.txt"]
    assert payload["rolled_back"] == []
    assert payload["state"] == "approved"
    assert "would publish" in payload["reason"]


def test_publish_honours_the_target_flag(stores, capsys, tmp_path):
    """
    GIVEN a branch other than main
    WHEN `ephe publish --target release` runs
    THEN the ref that moves is that branch's.
    """
    repo = new_repo(tmp_path)
    git(repo, "branch", "release")
    change = build_set(stores, repo)
    approve(stores, change)

    assert run("publish", change.id, "--target", "release") == 0

    assert "published 1 file(s) to release" in capsys.readouterr().out
    assert git(repo, "show", "release:a.txt") == "A2\n"


# ephe reap


def test_reap_reports_the_orphan_it_removed(stores, capsys, tmp_path):
    """
    GIVEN a registered tree whose owning process is gone and the grace has passed
    WHEN `ephe reap --older-than 0` runs
    THEN the tree is gone, its id is printed, and the register no longer holds it.
    """
    tree = stores.managed / "9f3c1a2b"
    tree.mkdir(parents=True)
    row = register_row(stores, tree, pid=an_exited_pid())

    assert run("reap", "--older-than", "0") == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "reaped 1 orphaned workspace (grace 0m)"
    assert out[1].strip() == row["id"]
    assert not tree.exists()
    assert stores.wl.list_live() == []


def test_reap_says_so_when_there_is_nothing_to_collect(stores, capsys, tmp_path, monkeypatch):
    """
    GIVEN one registered tree whose owner is still alive
    WHEN `ephe reap` runs on the module's default grace
    THEN it reports that nothing was collected and prints the grace it applied.
    """
    tree = stores.managed / "9f3c1a2b"
    tree.mkdir(parents=True)
    register_row(stores, tree)
    seen: list[float] = []
    real_reap = stores.wl.reap_orphans

    def spy(minutes: float) -> list[str]:
        seen.append(minutes)
        return real_reap(minutes)

    monkeypatch.setattr(stores.wl, "reap_orphans", spy)

    assert run("reap") == 0

    out = capsys.readouterr().out
    assert out.startswith(f"no orphans to reap (grace {stores.wl.DEFAULT_REAP_MINUTES:g}m)")
    assert seen == [stores.wl.DEFAULT_REAP_MINUTES]
    assert tree.is_dir()


def test_reap_refuses_a_negative_grace(stores, capsys):
    """
    GIVEN a grace below zero
    WHEN `ephe reap --older-than -5` runs
    THEN it is a usage error (exit 2) naming the value and the default.
    """
    assert run("reap", "--older-than", "-5") == 2

    captured = capsys.readouterr()
    assert "--older-than needs zero or more minutes, got -5" in captured.err
    assert "the default is 240 minutes" in captured.err


def test_reap_json_reports_the_grace_and_the_ids(stores, capsys, tmp_path):
    """
    GIVEN an orphan past the grace
    WHEN `ephe reap --older-than 0 --json` runs
    THEN the payload carries the grace, the count and the ids that went.
    """
    tree = stores.managed / "9f3c1a2b"
    tree.mkdir(parents=True)
    row = register_row(stores, tree, pid=an_exited_pid())

    assert run("reap", "--older-than", "0", "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"grace_minutes": 0.0, "count": 1, "reaped": [row["id"]]}


# the seam's own defaults


def test_the_seam_asks_the_gate_for_its_own_ledger():
    """
    GIVEN no repointed ledger
    WHEN the seam asks for one
    THEN it is the gate's singleton, so a verdict written here is the one publish reads.
    """
    from core import _cli_isolation as iso
    from core import review_gate as gate

    assert iso._ledger() is gate.default_ledger()


def test_the_seam_refuses_a_decision_that_is_not_a_verdict(stores, tmp_path):
    """
    GIVEN a decision word the parser would never pass on
    WHEN the seam is called directly
    THEN it raises the refusal instead of filing something the gate cannot name.
    """
    from core import _cli_isolation as iso

    with pytest.raises(iso.IsolationError) as refused:
        iso.run_review("cs-1", "maybe", "rev-1", ["a.txt:1:why"], as_json=False)

    assert refused.value.code == 2
    assert "unknown decision 'maybe'" in str(refused.value)


# ephe show — the read half of the accept loop


def test_show_prints_the_unified_diff_of_a_stored_change_set(stores, capsys):
    """
    GIVEN a stored change set built from a real edit
    WHEN `ephe show <id>` runs
    THEN the diff body, the path and the state are printed, not only the digest.
    """
    repo = new_repo(stores.tmp_path)
    change = build_set(stores, repo)

    assert run("show", change.id) == 0

    out = capsys.readouterr().out
    assert change.id in out
    assert "a.txt" in out
    assert "[modify]" in out
    assert "+A2" in out  # the diff body `ephe changes` never had room for


def test_show_json_carries_the_diff_text_under_each_path(stores, capsys):
    """
    GIVEN a stored change set
    WHEN `ephe show <id> --json` runs
    THEN every file row carries its regenerated diff text and the drift list is empty.
    """
    repo = new_repo(stores.tmp_path)
    change = build_set(stores, repo)

    assert run("show", change.id, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == change.id
    assert payload["drift"] == []
    rows = {row["path"]: row for row in payload["files"]}
    assert rows["a.txt"]["present"] is True
    assert "+A2" in rows["a.txt"]["text"]


def test_show_flags_a_path_that_drifted_since_the_set_was_built(stores, capsys):
    """
    GIVEN a change set built, then an edit that moves the recorded digest
    WHEN `ephe show <id>` runs
    THEN the path is flagged as drifted instead of shown as if it still matched.
    """
    repo = new_repo(stores.tmp_path)
    change = build_set(stores, repo)
    (repo / "a.txt").write_text("A3\n", encoding="utf-8")

    assert run("show", change.id) == 0

    out = capsys.readouterr().out
    assert "drifted since recorded" in out
    assert "drifted since this set was built" in out


def test_show_refuses_an_unknown_change_set_with_the_store_it_looked_in(stores, capsys):
    """
    GIVEN no change set carries the given id
    WHEN `ephe show` runs
    THEN it refuses with exit code 1 and names the store and the verb that lists ids.
    """
    assert run("show", "cs-nope") == 1

    err = capsys.readouterr().err
    assert "cs-nope" in err
    assert "ephe changes" in err


def test_an_approval_from_the_terminal_reaches_the_state_the_web_publish_gate_reads():
    """One record for two surfaces.

    A set approved with `ephe review --approve` must satisfy the same gate as one approved on
    the Workspaces page, because `server/routes/workspaces.py` reads the state that both
    surfaces write. Should only one of them write `approved`, the two drift, and the web
    publish route answers a set a person did approve with a 409 and a sentence claiming no
    approval exists.
    """
    from core import change_set as cs
    from core._cli_isolation import STATE_AFTER
    from core.review_gate import APPROVE

    assert STATE_AFTER[APPROVE] == "approved"
    assert STATE_AFTER[APPROVE] in cs.STATES, (
        "the state an approval writes must be one the store accepts"
    )
