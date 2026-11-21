"""◑ Ephe · TDD — the catalog row a commit leaves behind must match the bundle it ships.

Measured on 0ef1c8e6: 08e192d5 edited two bundles' prompts and left both catalog
rows behind. The drift gate exits 1 on that tree, and the full suite reads those
rows — 14 failures — while the commit hook stayed green, because the hook had no
catalog check. A bundle edit could land without one.

The hook reads staged blobs, never the disk: on a shared tree the file on disk can
carry another strand's unfinished edit. This check therefore hashes the INDEX
entries of the touched bundle and compares them to the INDEX catalog row, which is
what both will say once the commit exists.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.plugin_manifest import dir_sha256

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "catalog_staged.py"

MANIFEST = {
    "name": "demo",
    "version": "1.0.0",
    "description": "A bundle the test edits.",
    "manifest_version": 2,
    "origin": "first-party",
}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout


def _run(repo: Path, *paths: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *paths],
        cwd=repo,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed bundle and a catalog row that matches it."""
    repo = tmp_path / "repo"
    bundle = repo / "plugins" / "demo"
    bundle.mkdir(parents=True)
    (bundle / "ephe-plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (bundle / "handler.py").write_text("VALUE = 1\n", encoding="utf-8")
    catalog = {
        "version": 1,
        "public": [
            {
                "name": "demo",
                "description": MANIFEST["description"],
                "tags": [],
                "enabled": True,
                "sha256": dir_sha256(bundle),
                "url": "",
            }
        ],
        "personal": [],
    }
    (repo / "plugin-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "baseline")
    return repo


def _restage_catalog(repo: Path) -> None:
    bundle = repo / "plugins" / "demo"
    path = repo / "plugin-catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    catalog["public"][0]["sha256"] = dir_sha256(bundle)
    path.write_text(json.dumps(catalog), encoding="utf-8")
    _git(repo, "add", "plugin-catalog.json")


def test_a_bundle_edit_without_a_catalog_row_is_refused(repo: Path):
    """GIVEN a staged bundle edit and a catalog row naming the old bytes
    WHEN the check runs
    THEN it refuses and names the bundle."""
    (repo / "plugins" / "demo" / "handler.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "plugins/demo/handler.py")

    out = _run(repo, "plugins/demo/handler.py")

    assert out.returncode == 1, out.stdout + out.stderr
    assert "demo" in out.stdout


def test_the_same_edit_with_a_regenerated_row_passes(repo: Path):
    """GIVEN the same bundle edit and a catalog row regenerated from it
    WHEN the check runs
    THEN it passes."""
    (repo / "plugins" / "demo" / "handler.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "plugins/demo/handler.py")
    _restage_catalog(repo)

    out = _run(repo, "plugins/demo/handler.py", "plugin-catalog.json")

    assert out.returncode == 0, out.stdout + out.stderr


def test_an_unstaged_edit_on_disk_does_not_decide_the_verdict(repo: Path):
    """GIVEN a committed bundle whose row matches and a stray edit on disk
    WHEN the check runs over a scope that names the bundle
    THEN the index decides, so the stray edit cannot refuse another strand's commit."""
    (repo / "plugins" / "demo" / "handler.py").write_text("VALUE = 99\n", encoding="utf-8")

    out = _run(repo, "plugins/demo/ephe-plugin.json")

    assert out.returncode == 0, out.stdout + out.stderr


def test_a_scope_without_a_bundle_passes(repo: Path):
    """GIVEN a commit that touches no bundle and no catalog
    WHEN the check runs
    THEN it passes without reading either."""
    (repo / "README.md").write_text("note\n", encoding="utf-8")
    _git(repo, "add", "README.md")

    out = _run(repo, "README.md")

    assert out.returncode == 0, out.stdout + out.stderr


def test_a_new_bundle_without_a_row_is_refused(repo: Path):
    """GIVEN a staged bundle the catalog does not name
    WHEN the check runs
    THEN it refuses: a shipped bundle the store cannot see is drift too."""
    extra = repo / "plugins" / "second"
    extra.mkdir(parents=True)
    (extra / "ephe-plugin.json").write_text(
        json.dumps({**MANIFEST, "name": "second"}), encoding="utf-8"
    )
    _git(repo, "add", "plugins/second")

    out = _run(repo, "plugins/second/ephe-plugin.json")

    assert out.returncode == 1, out.stdout + out.stderr
    assert "second" in out.stdout


def test_a_missing_catalog_is_no_verdict_not_a_pass(repo: Path):
    """GIVEN a staged bundle and no catalog in the index
    WHEN the check runs
    THEN it reports that it could not decide, which is not a pass."""
    _git(repo, "rm", "-q", "--cached", "plugin-catalog.json")
    (repo / "plugins" / "demo" / "handler.py").write_text("VALUE = 3\n", encoding="utf-8")
    _git(repo, "add", "plugins/demo/handler.py")

    out = _run(repo, "plugins/demo/handler.py")

    assert out.returncode == 2, out.stdout + out.stderr
    assert "plugin-catalog.json" in out.stdout, out.stdout + out.stderr


def test_the_signature_record_stays_out_of_the_hash(repo: Path):
    """GIVEN a staged signature record beside the bundle
    WHEN the check runs
    THEN the row still matches: signing does not change the hash it signs."""
    (repo / "plugins" / "demo" / "ephe-plugin.sig.json").write_text("{}", encoding="utf-8")
    _git(repo, "add", "plugins/demo/ephe-plugin.sig.json")

    out = _run(repo, "plugins/demo/ephe-plugin.sig.json")

    assert out.returncode == 0, out.stdout + out.stderr


def test_the_shipped_hook_calls_the_check_behind_a_bundle_scope():
    """GIVEN the shipped hook WHEN its body is read THEN the catalog check sits
    behind a scope that names a bundle or the catalog, and a death is not a pass."""
    hook = (ROOT / "scripts" / "ci_local.sh").read_text(encoding="utf-8")

    assert "catalog_staged.py" in hook
    call = hook.index("catalog_staged.py")
    assert "catalog_needed" in hook[:call]
    after = hook[call:]
    assert "-ge 128" in after[:900], "a signal death must not read as a pass"
    assert "skills-lock.json" in hook[:call], "the skills lock is the second catalog"
    assert "skills/*" in hook[:call]


# --- the second committed catalog: skills-lock.json over skills/<pack>/ ---

@pytest.fixture
def skills_repo(tmp_path: Path) -> Path:
    """A committed skill pack and a lock row that matches it."""
    from scripts.generate_skills_lock import pack_hash

    repo = tmp_path / "skillsrepo"
    pack = repo / "skills" / "image-creator"
    (pack / "references").mkdir(parents=True)
    (pack / "SKILL.md").write_text("# image-creator\n\nOriginal prompt.\n", encoding="utf-8")
    (pack / "references" / "rubric.md").write_text("rubric v1\n", encoding="utf-8")
    lock = {
        "version": 1,
        "skills": [
            {
                "name": "image-creator",
                "source": "skills/image-creator",
                "computedHash": pack_hash(pack),
            }
        ],
    }
    (repo / "skills-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "baseline")
    return repo


def _restage_lock(repo: Path) -> None:
    from scripts.generate_skills_lock import pack_hash

    path = repo / "skills-lock.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    lock["skills"][0]["computedHash"] = pack_hash(repo / "skills" / "image-creator")
    path.write_text(json.dumps(lock), encoding="utf-8")
    _git(repo, "add", "skills-lock.json")


def test_a_pack_edit_without_a_lock_row_is_refused(skills_repo: Path):
    """GIVEN a staged skill edit and a lock row naming the old bytes
    WHEN the check runs
    THEN it refuses and names the pack."""
    pack = skills_repo / "skills" / "image-creator"
    (pack / "SKILL.md").write_text("# image-creator\n\nEdited prompt.\n", encoding="utf-8")
    _git(skills_repo, "add", "skills/image-creator/SKILL.md")

    out = _run(skills_repo, "skills/image-creator/SKILL.md")

    assert out.returncode == 1, out.stdout + out.stderr
    assert "image-creator" in out.stdout


def test_the_same_pack_edit_with_a_regenerated_row_passes(skills_repo: Path):
    """GIVEN the same skill edit and a lock row regenerated from it
    WHEN the check runs
    THEN it passes."""
    pack = skills_repo / "skills" / "image-creator"
    (pack / "SKILL.md").write_text("# image-creator\n\nEdited prompt.\n", encoding="utf-8")
    _git(skills_repo, "add", "skills/image-creator/SKILL.md")
    _restage_lock(skills_repo)

    out = _run(skills_repo, "skills/image-creator/SKILL.md", "skills-lock.json")

    assert out.returncode == 0, out.stdout + out.stderr


def test_a_pack_file_outside_the_counted_subdirs_does_not_move_the_hash(skills_repo: Path):
    """GIVEN a staged file at pack level that the lock algorithm does not count
    WHEN the check runs
    THEN the row still matches: only SKILL.md and the four subdirs are hashed."""
    pack = skills_repo / "skills" / "image-creator"
    (pack / "NOTES.txt").write_text("not counted\n", encoding="utf-8")
    _git(skills_repo, "add", "skills/image-creator/NOTES.txt")

    out = _run(skills_repo, "skills/image-creator/NOTES.txt")

    assert out.returncode == 0, out.stdout + out.stderr


def test_an_unstaged_pack_edit_on_disk_does_not_decide(skills_repo: Path):
    """GIVEN a committed pack whose row matches and a stray edit on disk
    WHEN the check runs
    THEN the index decides, so the stray edit cannot refuse the commit."""
    pack = skills_repo / "skills" / "image-creator"
    (pack / "SKILL.md").write_text("stray edit\n", encoding="utf-8")

    out = _run(skills_repo, "skills/image-creator/references/rubric.md")

    assert out.returncode == 0, out.stdout + out.stderr


def test_a_missing_skills_lock_is_no_verdict(skills_repo: Path):
    """GIVEN a staged pack and no lock in the index
    WHEN the check runs
    THEN it reports no verdict, which is not a pass."""
    _git(skills_repo, "rm", "-q", "--cached", "skills-lock.json")
    pack = skills_repo / "skills" / "image-creator"
    (pack / "SKILL.md").write_text("edited\n", encoding="utf-8")
    _git(skills_repo, "add", "skills/image-creator/SKILL.md")

    out = _run(skills_repo, "skills/image-creator/SKILL.md")

    assert out.returncode == 2, out.stdout + out.stderr
    assert "skills-lock.json" in out.stdout