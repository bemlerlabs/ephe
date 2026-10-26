"""The provenance gate, on planted repositories and on this one.

The gate answers one question per tag: does its commit sit on the trunk? The
v0.1.7 incident is recorded in the baseline, so the repository run has to pass
while still naming that tag as diverged.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


class TestOnThisRepository:
    def test_every_tag_is_on_main_or_recorded(self):
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--base", "origin/main"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "PASS" in done.stdout, done.stdout
