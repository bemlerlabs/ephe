"""The provenance gate, on planted repositories and on this one.

The gate answers one question per tag: does its commit sit on the trunk? The
v0.1.7 incident is recorded in the baseline, so the repository run has to pass
while still naming that tag as diverged.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provenance_check.py"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ("git", *args), cwd=str(repo), text=True, capture_output=True, check=True
    )
    return done.stdout


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Provenance Test")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "one")
    return repo


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def baseline(tmp_path: Path, known: list[str]) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"known_diverged": known}), encoding="utf-8")
    return path


def baseline_with_outside(tmp_path: Path, known: list[str], outside: list[str]) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"known_diverged": known, "not_a_release": outside}), encoding="utf-8"
    )
    return path


class TestOnAPlant:
    def test_a_tag_on_the_trunk_passes(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "tag", "-a", "v0.1.0", "-m", "cut")
        done = run(repo, "--base", "main", "--baseline", str(baseline(tmp_path, [])))
        assert done.returncode == 0, done.stdout + done.stderr
        assert "on base" in done.stdout, done.stdout

    def test_a_tag_on_a_side_branch_fails_and_names_the_tag(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "switch", "-q", "-c", "side")
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-qm", "two")
        git(repo, "tag", "-a", "v0.2.0", "-m", "cut")
        git(repo, "switch", "-q", "main")
        done = run(repo, "--base", "main", "--baseline", str(baseline(tmp_path, [])))
        assert done.returncode == 1, done.stdout
        assert "DIVERGED" in done.stdout and "v0.2.0" in done.stdout, done.stdout

    def test_a_recorded_divergence_passes(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "switch", "-q", "-c", "side")
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-qm", "two")
        git(repo, "tag", "-a", "v0.2.0", "-m", "cut")
        git(repo, "switch", "-q", "main")
        done = run(repo, "--base", "main", "--baseline", str(baseline(tmp_path, ["v0.2.0"])))
        assert done.returncode == 0, done.stdout
        assert "recorded in the baseline" in done.stdout, done.stdout

    def test_a_baseline_entry_that_became_an_ancestor_is_reported(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "tag", "-a", "v0.1.0", "-m", "cut")
        done = run(repo, "--base", "main", "--baseline", str(baseline(tmp_path, ["v0.1.0"])))
        assert done.returncode == 0, done.stdout
        assert "can go" in done.stdout, done.stdout

    def test_a_base_that_does_not_resolve_is_not_a_verdict(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "tag", "-a", "v0.1.0", "-m", "cut")
        done = run(repo, "--base", "origin/nope", "--baseline", str(baseline(tmp_path, [])))
        assert done.returncode == 2, done.stdout
        assert "does not resolve" in done.stdout, done.stdout

    def test_a_checkout_without_tags_is_not_a_silent_pass(self, tmp_path):
        repo = make_repo(tmp_path)
        done = run(repo, "--base", "main", "--baseline", str(baseline(tmp_path, [])))
        assert done.returncode == 2, done.stdout
        assert "no v* tag" in done.stdout, done.stdout

    def test_a_recorded_tag_says_so_on_its_line(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "switch", "-q", "-c", "side")
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-qm", "two")
        git(repo, "tag", "-a", "v0.2.0", "-m", "cut")
        git(repo, "switch", "-q", "main")
        done = run(repo, "--base", "main", "--baseline", str(baseline(tmp_path, ["v0.2.0"])))
        assert done.returncode == 0, done.stdout
        assert "DIVERGED (recorded)" in done.stdout, done.stdout

    def test_a_new_baseline_entry_is_refused_against_the_base(self, tmp_path):
        repo = make_repo(tmp_path)
        tracked = repo / "provenance-baseline.json"
        tracked.write_text(json.dumps({"known_diverged": []}), encoding="utf-8")
        git(repo, "add", "provenance-baseline.json")
        git(repo, "commit", "-qm", "baseline")
        git(repo, "switch", "-q", "-c", "side")
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-qm", "two")
        git(repo, "tag", "-a", "v0.2.0", "-m", "cut")
        git(repo, "switch", "-q", "main")
        tracked.write_text(json.dumps({"known_diverged": ["v0.2.0"]}), encoding="utf-8")
        done = run(repo, "--base", "main", "--baseline", str(tracked), "--baseline-at", "main")
        assert done.returncode == 1, done.stdout
        assert "adds v0.2.0" in done.stdout, done.stdout


    def test_a_ref_outside_the_release_line_is_skipped_and_says_so(self, tmp_path):
        """A checkout can carry another lineage's tags. Such a ref is not a diverged
        release of this project, and judging one would report a defect that is not there."""
        repo = make_repo(tmp_path)
        git(repo, "switch", "-q", "-c", "other")
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-qm", "two")
        git(repo, "tag", "-a", "v9.9.0", "-m", "another lineage")
        git(repo, "switch", "-q", "main")
        git(repo, "tag", "-a", "v0.1.0", "-m", "cut")
        done = run(
            repo,
            "--base",
            "main",
            "--baseline",
            str(baseline_with_outside(tmp_path, [], ["v9.9.0"])),
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "v9.9.0 skipped — recorded as outside the release line" in done.stdout, done.stdout
        assert "DIVERGED" not in done.stdout, done.stdout
        assert "1 tag(s) on main" in done.stdout, done.stdout

    def test_a_recorded_ref_that_carries_no_tag_here_is_named(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "tag", "-a", "v0.1.0", "-m", "cut")
        done = run(
            repo,
            "--base",
            "main",
            "--baseline",
            str(baseline_with_outside(tmp_path, [], ["v9.9.0"])),
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "v9.9.0 is listed as outside the line and carries no tag here" in done.stdout

    def test_a_skipped_ref_is_not_counted_as_a_tag_on_the_base(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "tag", "-a", "v0.1.0", "-m", "cut")
        git(repo, "tag", "-a", "v0.2.0", "-m", "cut")
        done = run(
            repo,
            "--base",
            "main",
            "--baseline",
            str(baseline_with_outside(tmp_path, [], ["v0.2.0"])),
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "PASS — 1 tag(s)" in done.stdout, done.stdout


class TestOnAShallowCopy:
    def test_a_shallow_checkout_is_refused_not_read_as_diverged(self, tmp_path):
        """A depth-1 clone carries every tag but no history, so an older tag's commit
        reads as diverged. The gate has to say it cannot judge, not fail the tag."""
        source = make_repo(tmp_path)
        git(source, "tag", "-a", "v0.1.0", "-m", "cut")
        (source / "b.txt").write_text("two\n", encoding="utf-8")
        git(source, "add", "b.txt")
        git(source, "commit", "-qm", "two")

        clone = tmp_path / "clone"
        clone.mkdir()
        git(clone, "init", "-q", "-b", "main")
        git(clone, "remote", "add", "origin", source.as_uri())
        git(
            clone,
            "fetch",
            "-q",
            "--depth",
            "1",
            "origin",
            "+refs/tags/*:refs/tags/*",
            "refs/heads/main:refs/remotes/origin/main",
        )
        git(clone, "checkout", "-q", "main")

        # The state is misleading on purpose: the tag is on the trunk, yet the
        # grafted history puts its commit outside the base.
        misleading = subprocess.run(
            ("git", "merge-base", "--is-ancestor", "v0.1.0^{commit}", "origin/main"),
            cwd=str(clone),
            capture_output=True,
            check=False,
        )
        assert misleading.returncode == 1, "the planted clone is not shallow in the expected shape"

        done = run(clone, "--base", "origin/main", "--baseline", str(baseline(tmp_path, [])))
        assert done.returncode == 2, done.stdout + done.stderr
        assert "shallow" in done.stdout, done.stdout


class TestOnThisRepository:
    @staticmethod
    def _base_ref() -> str:
        """Which ref the release line is actually cut from.

        A working checkout on the owner's machine carries the publication remote as `public`
        and the private development history as `origin`; a CI clone of the published
        repository knows the trunk only as `origin/main`. The gate has to judge the tags
        against the trunk that ships them."""
        override = os.environ.get("EPHE_PROVENANCE_BASE")
        if override:
            return override
        for candidate in ("public/main", "origin/main"):
            done = subprocess.run(
                ("git", "rev-parse", "--verify", candidate),
                cwd=str(ROOT),
                capture_output=True,
                check=False,
            )
            if done.returncode == 0:
                return candidate
        return "origin/main"

    def test_every_tag_is_on_main_or_recorded(self):
        shallow = subprocess.run(
            ("git", "rev-parse", "--is-shallow-repository"),
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        if shallow.stdout.strip() == "true":
            pytest.skip("a shallow checkout cannot judge tag ancestry")
        base_ref = self._base_ref()
        base = subprocess.run(
            ("git", "rev-parse", "--verify", base_ref),
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        if base.returncode != 0:
            pytest.skip(f"this checkout has no {base_ref} (shallow clone)")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--base", base_ref],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "PASS" in done.stdout, done.stdout
