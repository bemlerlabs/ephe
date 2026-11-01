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


class TestOnTheReleaseRemoteList:
    """The tags a release carries are the ones its remote lists.

    A working clone can hold a second lineage's objects under the same tag names, and the
    shadow is invisible from `git tag`: the name resolves, the commit is real, and only the
    verdict is wrong. The gate reads a ref namespace, so a cut can judge the release remote's
    own list."""

    def test_the_remote_list_is_judged_when_a_local_ref_shadows_it(self, tmp_path):
        upstream = make_repo(tmp_path)
        git(upstream, "tag", "-a", "v0.1.0", "-m", "cut on the trunk")
        work = tmp_path / "work"
        work.mkdir()
        git(work, "init", "-q", "-b", "shadow")
        git(work, "config", "user.email", "test@example.invalid")
        git(work, "config", "user.name", "Provenance Test")
        git(work, "remote", "add", "upstream_repo", upstream.as_uri())
        git(
            work,
            "fetch",
            "-q",
            "--prune",
            "upstream_repo",
            "refs/heads/main:refs/remotes/upstream_repo/main",
            "+refs/tags/*:refs/remotes/upstream_repo/tags/*",
        )
        (work / "shadow.txt").write_text("mine\n", encoding="utf-8")
        git(work, "add", "shadow.txt")
        git(work, "commit", "-qm", "a commit upstream never carried")
        # -f on purpose: the fetch followed upstream's tag into refs/tags, and the shadow is
        # the same name landing on an object the trunk never carried.
        git(work, "tag", "-f", "-a", "v0.1.0", "-m", "the same name, another lineage")

        ns = "refs/remotes/upstream_repo/tags"
        shadowed = run(work, "--base", "refs/remotes/upstream_repo/main",
                       "--baseline", str(baseline(tmp_path, [])))
        assert shadowed.returncode == 1, shadowed.stdout
        assert "DIVERGED" in shadowed.stdout, shadowed.stdout

        judged = run(work, "--base", "refs/remotes/upstream_repo/main", "--tag-namespace", ns,
                     "--baseline", str(baseline(tmp_path, [])))
        assert judged.returncode == 0, judged.stdout + judged.stderr
        assert "on base" in judged.stdout and "PASS — 1 tag(s)" in judged.stdout, judged.stdout

    def test_an_empty_namespace_is_not_read_as_a_clean_release_line(self, tmp_path):
        upstream = make_repo(tmp_path)
        git(upstream, "tag", "-a", "v0.1.0", "-m", "cut")
        work = tmp_path / "work"
        work.mkdir()
        git(work, "init", "-q", "-b", "main")
        git(work, "remote", "add", "upstream_repo", upstream.as_uri())
        git(work, "fetch", "-q", "upstream_repo", "refs/heads/main:refs/remotes/upstream_repo/main")
        done = run(work, "--base", "refs/remotes/upstream_repo/main",
                   "--tag-namespace", "refs/remotes/upstream_repo/tags",
                   "--baseline", str(baseline(tmp_path, [])))
        assert done.returncode == 2, done.stdout
        assert "lists no v* tag" in done.stdout, done.stdout


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
    """The published release line, judged from the refs that carry it.

    A CI clone of the published repository holds one lineage, so `refs/tags` and `origin/main`
    are the release line and the default namespace answers the question. A development checkout
    can hold a second lineage's objects under the same tag names, so it judges the publication
    remote's own ref namespace — the list `scripts/release_cut.sh` fetches before a cut."""

    @staticmethod
    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *args), cwd=str(ROOT), text=True, capture_output=True, check=False
        )

    @staticmethod
    def _namespace_listed(ref: str) -> bool:
        listed = TestOnThisRepository._git("for-each-ref", "--count=1", f"{ref}/")
        return bool(listed.stdout.strip())

    def test_every_tag_is_on_main_or_recorded(self):
        if self._git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            pytest.skip("a shallow checkout cannot judge tag ancestry")

        override_base = os.environ.get("EPHE_PROVENANCE_BASE")
        override_ns = os.environ.get("EPHE_PROVENANCE_TAG_NAMESPACE")
        if override_base:
            base_ref, namespace = override_base, override_ns
        elif self._git("remote", "get-url", "public").returncode == 0:
            if not self._namespace_listed("refs/remotes/public/tags"):
                pytest.skip(
                    "this checkout carries the publication remote and has not fetched its tag "
                    "refs; run: git fetch public '+refs/tags/*:refs/remotes/public/tags/*'"
                )
            base_ref, namespace = "public/main", "refs/remotes/public/tags"
        else:
            base_ref, namespace = "origin/main", override_ns

        if self._git("rev-parse", "--verify", "-q", base_ref).returncode != 0:
            pytest.skip(f"this checkout has no {base_ref}")
        command = [sys.executable, str(SCRIPT), "--base", base_ref]
        if namespace:
            command += ["--tag-namespace", namespace]
        done = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, check=False)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "PASS" in done.stdout, done.stdout
