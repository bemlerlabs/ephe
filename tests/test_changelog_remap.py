"""The changelog remap moves an address only when the diff proves the commit is the same change.

`scripts/changelog_remap.py` exists because a rebase merge rewrites every commit it lands: the
`[Unreleased]` block is written on the branch, so its bullets name shas that exist only there, and
`scripts/changelog_unreleased.py` reads the string — which makes the trunk report its own wave as
unrecorded. The tool is the repair, so these cases are about the repair not becoming a lie: a
subject is a sentence two different changes could share, and the patch id is what says otherwise.

Each case builds its own repository in `tmp_path` and points the module at it, because every
function reads `ROOT` at call time.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "changelog_remap.py"

_spec = importlib.util.spec_from_file_location("changelog_remap", SCRIPT)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A trunk with one commit, and a branch whose commit was cherry-picked onto it.

    The cherry-pick is the rebase merge in miniature: same diff, same subject, different sha,
    and the branch's own object still resolvable in the same store.
    """
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "test")
    (root / "a.txt").write_text("first\n", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "fix(alpha): the first change")
    git(root, "checkout", "-qb", "feature")
    (root / "b.txt").write_text("second\n", encoding="utf-8")
    git(root, "add", "b.txt")
    git(root, "commit", "-qm", "fix(beta): the second change")
    branch_sha = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    # A second commit on the trunk first, so the replayed change cannot land on the same
    # parent — with an identical parent, tree, message and dates git would hand back the
    # very same sha, and the case would prove nothing.
    (root / "a2.txt").write_text("between\n", encoding="utf-8")
    git(root, "add", "a2.txt")
    git(root, "commit", "-qm", "fix(alpha): a second trunk change")
    git(root, "cherry-pick", "feature")
    trunk_sha = git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(mod, "ROOT", root)
    return {"root": root, "branch": branch_sha, "trunk": trunk_sha}


def block(*tokens: str) -> str:
    body = "\n".join(f"- item: named here (`{t}`)" for t in tokens)
    return f"# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n{body}\n\n## [0.1.0] - 2026-01-01\n"


class TestPlan:
    def test_a_rebased_address_moves_to_the_commit_the_trunk_carries(self, repo):
        text = block(repo["branch"][:8])
        remaps, pending, refused = mod.plan(text, "main")
        assert refused == [] and pending == []
        assert remaps == [(repo["branch"][:8], repo["trunk"][:8])], remaps

    def test_an_address_the_trunk_already_carries_is_left_alone(self, repo):
        remaps, pending, refused = mod.plan(block(repo["trunk"][:8]), "main")
        assert (remaps, pending, refused) == ([], [], [])

    def test_a_subject_that_matches_a_different_diff_is_refused(self, repo, tmp_path):
        """Same sentence, different bytes: the tool must say no rather than move the address."""
        root = repo["root"]
        git(root, "checkout", "-qb", "other")
        (root / "c.txt").write_text("third\n", encoding="utf-8")
        git(root, "add", "c.txt")
        git(root, "commit", "-qm", "fix(beta): the second change")
        other = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "-q", "main")
        remaps, pending, refused = mod.plan(block(other[:8]), "main")
        assert remaps == []
        assert pending == [], pending
        assert refused and "diffs differ" in refused[0], refused

    def test_an_address_with_no_object_here_is_refused_not_invented(self, repo):
        remaps, pending, refused = mod.plan(block("deadbee"), "main")
        assert remaps == [] and pending == []
        assert refused and "no such object" in refused[0], refused


class TestApply:
    def test_both_writing_forms_are_replaced(self, repo):
        branch, trunk = repo["branch"][:8], repo["trunk"][:8]
        text = f"## [Unreleased]\n\n- bullet (`{branch}`)\n\nThe wave is named (`{branch}`, `b1`)\n"
        out = mod.apply_remaps(text, [(branch, trunk)])
        assert out.count(f"`{trunk}`") == 2, out
        assert branch not in out

    def test_a_shorter_token_is_not_eaten_from_inside_a_longer_one(self, repo):
        """`a02adcf` is a prefix of nothing here, but a bare substring swap would corrupt the
        comma list; the backticks are the whole context, so a longer sha stays intact."""
        long_sha = repo["branch"][:12]
        short = repo["branch"][:8]
        out = mod.apply_remaps(f"(`{long_sha}`)", [(short, "ffffffff")])
        assert f"(`{long_sha}`)" in out, out
