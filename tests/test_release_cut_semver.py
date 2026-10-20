"""The cut machine on a prerelease line.

`scripts/release_cut.sh` could not cut any version on 0.1.0: its comparison stripped the
prerelease from both sides, so `0.1.0-beta.10` was never ahead of `0.1.0`, and it refused the
folded `## [0.1.0-beta.10]` section as "already released" while `release_checklist.py`,
`release_notes.py` and the beta.4–beta.9 tags all require that section before the tag. Every
beta since beta.4 has therefore been cut by hand. These cases run the real script against a
throwaway repository so beta.11 can go through the machine, and so a future edit cannot
quietly restore either refusal.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "release_cut.sh"

FOLDED = """# Changelog

## [Unreleased]
- nothing yet

## [{top}] – 2026-10-19
### Added
- the round

## [0.1.0-beta.10] – 2026-10-19
### Added
- the last round
"""

UNFOLDED = """# Changelog

## [Unreleased]
- nothing yet

## [0.1.0-beta.10] – 2026-10-19
### Added
- the last round
"""

NEWER_ABOVE = """# Changelog

## [Unreleased]
- nothing yet

## [0.1.0-beta.12] – 2026-10-19
### Added
- a release ahead of the one being cut
"""


def _fixture(tmp_path: Path, version: str, changelog: str) -> Path:
    root = tmp_path
    (root / "scripts").mkdir()
    shutil.copy(SCRIPT, root / "scripts" / "release_cut.sh")
    (root / "app" / "src-tauri").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "ephe"\nversion = "{version}"\n', encoding="utf-8"
    )
    for target in (root / "app" / "package.json", root / "app" / "src-tauri" / "tauri.conf.json"):
        target.write_text(json.dumps({"version": version}), encoding="utf-8")
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    git = ["git", "-C", str(root)]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True, capture_output=True)
    subprocess.run([*git, "config", "user.email", "cut@example.invalid"], check=True, capture_output=True)
    subprocess.run([*git, "config", "user.name", "cut"], check=True, capture_output=True)
    subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True, capture_output=True)
    return root


def _cut(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts" / "release_cut.sh"), "--dry-run", "--skip-gates", "--local"],
        capture_output=True,
        text=True,
        cwd=root,
    )


class TestPrereleaseOrder:
    """The refusals the machine had on the 0.1.0 line, and the one it must keep."""

    def test_a_folded_beta_cuts_through_the_machine(self, tmp_path):
        root = _fixture(tmp_path, "0.1.0-beta.11", FOLDED.format(top="0.1.0-beta.11"))
        out = _cut(root)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "folded for this cut" in out.stdout
        assert "git tag -a v0.1.0-beta.11" in out.stdout

    def test_the_release_outranks_its_own_prereleases(self, tmp_path):
        root = _fixture(tmp_path, "0.1.0", FOLDED.format(top="0.1.0"))
        assert _cut(root).returncode == 0, _cut(root).stdout

    def test_a_folded_section_is_not_read_as_already_released(self, tmp_path):
        root = _fixture(tmp_path, "0.1.0-beta.11", FOLDED.format(top="0.1.0-beta.11"))
        out = _cut(root)
        assert "already released" not in out.stdout + out.stderr

    def test_a_missing_section_still_refuses(self, tmp_path):
        root = _fixture(tmp_path, "0.1.0-beta.11", UNFOLDED)
        out = _cut(root)
        assert out.returncode == 1
        assert "no `## [0.1.0-beta.11]` section" in out.stdout
        assert "write the entry for 0.1.0-beta.11" in out.stdout

    def test_a_newer_section_above_refuses(self, tmp_path):
        root = _fixture(tmp_path, "0.1.0-beta.11", NEWER_ABOVE)
        out = _cut(root)
        assert out.returncode == 1
        assert "behind the last release [0.1.0-beta.12]" in out.stdout

    def test_an_existing_tag_refuses(self, tmp_path):
        root = _fixture(tmp_path, "0.1.0-beta.11", FOLDED.format(top="0.1.0-beta.11"))
        subprocess.run(
            ["git", "-C", str(root), "tag", "-a", "v0.1.0-beta.11", "-m", "x"],
            check=True,
            capture_output=True,
        )
        out = _cut(root)
        assert out.returncode == 1
        assert "tag v0.1.0-beta.11 already exists" in out.stdout


class TestSemverSort:
    """The ordering check 5 rests on, exercised through the script's own functions."""

    @pytest.mark.parametrize(
        ("left", "right", "greater"),
        [
            ("0.1.0-beta.10", "0.1.0-beta.9", True),
            ("0.1.0-beta.9", "0.1.0-beta.10", False),
            ("0.1.0-beta.11", "0.1.0-beta.10", True),
            ("0.1.0", "0.1.0-beta.10", True),
            ("0.1.0-beta.10", "0.1.0", False),
            ("0.1.0-beta.10", "0.1.0-beta.10", False),
            ("0.1.0-beta.2", "0.1.0-alpha.9", True),
            ("0.1.0-rc.1", "0.1.0-beta.10", True),
            ("0.2.0", "0.1.9", True),
            ("0.1.0-beta.10", "0.2.0", False),
        ],
    )
    def test_ordering(self, left, right, greater):
        assert _semver_gt(left, right) is greater


def _semver_gt(left: str, right: str) -> bool:
    body = SCRIPT.read_text(encoding="utf-8")
    start = body.index("semver_num()")
    end = body.index("read_pyproject_version()")
    helpers = body[start:end]
    script = f"set -uo pipefail\n{helpers}\nsemver_gt \"$1\" \"$2\"\n"
    done = subprocess.run(["bash", "-c", script, "semver", left, right], capture_output=True, text=True)
    assert done.returncode in (0, 1), done.stderr
    return done.returncode == 0
