"""Atomic ChangeSet publishing — every file or none, with a proven rollback.

These tests pin the contract of ``core.atomic_publish.publish`` and, in
``TestTheDefectItReplaces``, reproduce the defect it removes: applying a partial set file by
file with ``git apply`` leaves a half-applied tree. A publish must never do that — on any
failure the target must be *byte-identical* to before, which each test below measures
directly (ref oid, whole tree, every worktree byte, every loose object).

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from core import atomic_publish
from core.atomic_publish import publish


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, check=False, text=True
    )
    assert done.returncode == 0, f"git {args} failed: {done.stderr}"
    return done.stdout


def new_repo(tmp_path: Path) -> Path:
    """A repository on ``main`` with two tracked files, no bare worktree surprises."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "publish@example.invalid")
    git(repo, "config", "user.name", "publish")
    (repo / "a.txt").write_text("A\n", encoding="utf-8")
    (repo / "b.txt").write_text("B\n", encoding="utf-8")
    git(repo, "add", "a.txt", "b.txt")
    git(repo, "commit", "-qm", "init")
    return repo


@dataclass
class FakeWorkspace:
    """Stands in for ``core/ephemeral_workspace.py``: it exposes the repo root as ``.path``."""

    path: Path


@dataclass
class FakeChangeSet:
    """Stands in for the change-set owner's type: read structurally, as publish expects."""

    workspace: FakeWorkspace
    files: list = field(default_factory=list)
    message: str = "test: atomic publish"


def change_set(repo: Path, files: list, message: str = "test: atomic publish") -> FakeChangeSet:
    return FakeChangeSet(workspace=FakeWorkspace(repo), files=files, message=message)


def snapshot(repo: Path) -> tuple:
    """Everything a publish must not touch on failure: ref, tree, worktree bytes, objects."""
    oid = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/heads/main"],
        cwd=repo, capture_output=True, text=True, check=False,
    ).stdout.strip()
    tree = ""
    if oid:
        tree = git(repo, "ls-tree", "-r", "--full-tree", oid)
    worktree = {
        str(p.relative_to(repo)): p.read_bytes()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }
    objects = {
        str(p.relative_to(repo / ".git" / "objects"))
        for p in (repo / ".git" / "objects").rglob("*")
        if p.is_file()
    }
    return oid, tree, worktree, objects


def show(repo: Path, spec: str) -> str:
    return git(repo, "show", f"main:{spec}")


class TestCleanPublish:
    def test_a_clean_publish_applies_every_file(self, tmp_path):
        repo = new_repo(tmp_path)
        before = git(repo, "rev-parse", "main")

        result = publish(change_set(repo, [("a.txt", "A2\n"), ("b.txt", "B2\n")]), "main")

        assert result.ok is True, result.reason
        assert result.applied == ["a.txt", "b.txt"]
        assert result.rolled_back == []
        assert show(repo, "a.txt") == "A2\n"
        assert show(repo, "b.txt") == "B2\n"
        assert git(repo, "rev-parse", "main") != before

    def test_a_new_file_arrives_with_the_rest_of_the_set(self, tmp_path):
        repo = new_repo(tmp_path)

        result = publish(change_set(repo, [("a.txt", "A2\n"), ("c.txt", "C\n")]), "main")

        assert result.ok is True
        assert show(repo, "c.txt") == "C\n"
        assert show(repo, "a.txt") == "A2\n"


class TestDryRun:
    def test_a_dry_run_reports_the_set_and_changes_nothing(self, tmp_path):
        repo = new_repo(tmp_path)
        before = snapshot(repo)

        result = publish(
            change_set(repo, [("a.txt", "A2\n"), ("b.txt", "B2\n")]), "main", dry_run=True
        )

        assert result.ok is True
        assert result.applied == ["a.txt", "b.txt"]
        assert result.rolled_back == []
        assert "would publish" in result.reason
        assert snapshot(repo) == before

    def test_a_dry_run_that_cannot_apply_reports_false_and_still_changes_nothing(self, tmp_path):
        repo = new_repo(tmp_path)
        before = snapshot(repo)
        broken = change_set(repo, [{"path": "b.txt", "diff": _patch("b.txt", "-ZZZ", "+B2")}])

        result = publish(broken, "main", dry_run=True)

        assert result.ok is False
        assert result.applied == []
        assert snapshot(repo) == before


def _patch(path: str, *lines: str) -> str:
    body = "\n".join(lines)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}\n"


class TestConflict:
    def test_a_conflict_aborts_the_whole_set_and_leaves_the_target_identical(self, tmp_path):
        repo = new_repo(tmp_path)
        before = snapshot(repo)
        conflicting = change_set(repo, [{"path": "b.txt", "diff": _patch("b.txt", "-ZZZ", "+B2")}])

        result = publish(conflicting, "main")

        assert result.ok is False
        assert result.applied == []
        assert "b.txt" in result.reason or "aborted" in result.reason
        assert snapshot(repo) == before

    def test_a_later_file_conflicting_rolls_back_the_earlier_one(self, tmp_path):
        repo = new_repo(tmp_path)
        before = snapshot(repo)
        mixed = change_set(repo, [
            {"path": "a.txt", "content": "A2\n"},
            {"path": "b.txt", "diff": _patch("b.txt", "-ZZZ", "+B2")},
        ])

        result = publish(mixed, "main")

        assert result.ok is False
        assert result.applied == []
        assert result.rolled_back == ["a.txt"]
        assert snapshot(repo) == before


class TestInjectedFailure:
    def test_a_failure_between_two_files_rolls_the_set_back(self, tmp_path, monkeypatch):
        repo = new_repo(tmp_path)
        before = snapshot(repo)
        real_hook = atomic_publish._file_boundary_hook

        def boom(path: str) -> None:
            real_hook(path)
            if path == "b.txt":
                raise atomic_publish.PublishError("injected failure between a.txt and b.txt")

        monkeypatch.setattr(atomic_publish, "_file_boundary_hook", boom)

        result = publish(change_set(repo, [("a.txt", "A2\n"), ("b.txt", "B2\n")]), "main")

        assert result.ok is False
        assert result.applied == []
        assert result.rolled_back == ["a.txt"]
        assert "injected failure" in result.reason
        assert snapshot(repo) == before


class TestConcurrentUpdate:
    def test_a_target_moved_mid_flight_makes_the_publish_lose_cleanly(self, tmp_path, monkeypatch):
        repo = new_repo(tmp_path)
        real_build = atomic_publish._build_in_flight

        def build_then_move(*args, **kwargs):
            commit = real_build(*args, **kwargs)
            # another publisher wins the race after we read the base and built our tree
            (repo / "a.txt").write_text("WINNER\n", encoding="utf-8")
            git(repo, "add", "a.txt")
            git(repo, "commit", "-qm", "winner")
            return commit

        monkeypatch.setattr(atomic_publish, "_build_in_flight", build_then_move)

        result = publish(change_set(repo, [("b.txt", "B2\n")]), "main")

        assert result.ok is False
        assert result.applied == []
        assert show(repo, "a.txt") == "WINNER\n"
        assert show(repo, "b.txt") == "B\n"


class TestUnbornTarget:
    def test_publishing_creates_an_unborn_target_in_one_step(self, tmp_path):
        repo = tmp_path / "fresh"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "publish@example.invalid")
        git(repo, "config", "user.name", "publish")

        result = publish(change_set(repo, [("a.txt", "A\n"), ("b.txt", "B\n")]), "main")

        assert result.ok is True
        assert result.applied == ["a.txt", "b.txt"]
        assert show(repo, "a.txt") == "A\n"
        assert show(repo, "b.txt") == "B\n"


@dataclass
class FakeFileChange:
    """The real shape of ``core/change_set.FileChange``: a path, an op and a diff digest."""

    path: str
    op: str
    diff_sha: str = "sha256:0000"


class TestRealChangeSetShape:
    """A change set names paths; the bytes live in the workspace worktree, not in the set."""

    def test_a_change_set_of_paths_reads_its_bytes_from_the_workspace(self, tmp_path):
        repo = new_repo(tmp_path)
        (repo / "a.txt").write_text("A2\n", encoding="utf-8")  # an uncommitted workspace edit
        change = {
            "workspace_id": str(repo),
            "files": [FakeFileChange("a.txt", "modify"), FakeFileChange("b.txt", "delete")],
        }

        result = publish(change, "main")

        assert result.ok is True, result.reason
        assert result.applied == ["a.txt", "b.txt"]
        assert show(repo, "a.txt") == "A2\n"
        assert "b.txt" not in git(repo, "ls-tree", "-r", "--name-only", "main")

    def test_a_change_set_built_in_a_linked_worktree_publishes_to_main(self, tmp_path):
        repo = new_repo(tmp_path)
        worktree = tmp_path / "wt"
        git(repo, "worktree", "add", "-q", str(worktree), "-b", "ephemeral")
        (worktree / "a.txt").write_text("A2\n", encoding="utf-8")
        (worktree / "b.txt").unlink()
        before = git(repo, "rev-parse", "main")
        change = {
            "workspace_id": str(worktree),
            "files": [FakeFileChange("a.txt", "modify"), FakeFileChange("b.txt", "delete")],
        }

        result = publish(change, "main")

        assert result.ok is True, result.reason
        assert show(repo, "a.txt") == "A2\n"
        assert "b.txt" not in git(repo, "ls-tree", "-r", "--name-only", "main")
        assert git(repo, "rev-parse", "main") != before
        assert (worktree / "a.txt").read_text(encoding="utf-8") == "A2\n"  # source untouched

    def test_a_path_missing_from_the_workspace_aborts_before_anything_moves(self, tmp_path):
        repo = new_repo(tmp_path)
        before = snapshot(repo)
        change = {"workspace_id": str(repo), "files": [FakeFileChange("ghost.txt", "modify")]}

        result = publish(change, "main")

        assert result.ok is False
        assert "ghost.txt" in result.reason
        assert snapshot(repo) == before


class TestTheDefectItReplaces:
    def test_a_per_file_git_apply_leaves_a_half_applied_worktree(self, tmp_path):
        """The behaviour publish removes: apply file by file, the second fails, the first stays."""
        repo = new_repo(tmp_path)
        good = "/tmp/good.patch"
        bad = "/tmp/bad.patch"
        Path(good).write_text(_patch("a.txt", "-A", "+A2"), encoding="utf-8")
        Path(bad).write_text(_patch("b.txt", "-ZZZ", "+B2"), encoding="utf-8")
        git(repo, "apply", good)  # first file lands...
        failed = subprocess.run(["git", "apply", bad], cwd=repo, capture_output=True, text=True)

        assert failed.returncode != 0  # ...the second does not...
        assert (repo / "a.txt").read_text(encoding="utf-8") == "A2\n"  # ...yet the tree is half-done

    def test_publish_on_the_same_set_leaves_the_target_identical(self, tmp_path):
        repo = new_repo(tmp_path)
        before = snapshot(repo)
        mixed = change_set(repo, [
            {"path": "a.txt", "content": "A2\n"},
            {"path": "b.txt", "diff": _patch("b.txt", "-ZZZ", "+B2")},
        ])

        result = publish(mixed, "main")

        assert result.ok is False
        assert snapshot(repo) == before
