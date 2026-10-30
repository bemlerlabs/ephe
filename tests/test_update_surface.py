"""The update path speaks product, not git.

A checkout on a development branch used to fail with git's own tracking
message, which named the branch and read like a command. The refusal is a
sentence now, and the CLI prints that sentence instead of git's stderr.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ephe_cli  # noqa: E402
from core.update_apply import apply_update  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo_on(repo: Path, branch: str) -> Path:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("ephe\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "seed")
    _git(repo, "checkout", "-q", "-b", branch)
    return repo


def test_a_development_branch_is_refused_without_naming_it(tmp_path: Path) -> None:
    result = apply_update(_repo_on(tmp_path, "internal-lane"))
    assert result["ok"] is False
    assert result["reason"] == "not_on_main"
    assert "internal-lane" not in result["detail"]
    assert "git" not in result["detail"]


def test_the_cli_reports_the_refusal_as_one_sentence(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "core.update_apply.apply_update",
        lambda root=None: {
            "ok": False,
            "reason": "not_on_main",
            "detail": "this checkout is on a development branch, not on main",
            "steps": [],
        },
    )
    code = ephe_cli.cmd_update(argparse.Namespace(json=False, model=None))
    out = capsys.readouterr().out
    assert code == 1
    assert "development branch" in out
    assert "git " not in out
    assert "--set-upstream" not in out


def test_the_probe_answers_before_anything_is_offered(tmp_path: Path) -> None:
    """The dialog asks first: a release install has no checkout to move, and a
    branch checkout is not one a pull may take. Both come back as codes the
    surface owns, so the user is never handed a button that must refuse."""
    from core.update_apply import probe

    assert probe(tmp_path)["code"] == "not_a_checkout"
    (tmp_path / "b").mkdir()
    branch = probe(_repo_on(tmp_path / "b", "internal-lane"))
    assert branch == {"ok": False, "code": "not_on_main"}

    clean = tmp_path / "c"
    clean.mkdir()
    _git(clean, "init", "-q", "-b", "main")
    _git(clean, "config", "user.email", "test@example.invalid")
    _git(clean, "config", "user.name", "test")
    (clean / "README.md").write_text("ephe\n")
    _git(clean, "add", "README.md")
    _git(clean, "commit", "-q", "-m", "seed")
    assert probe(clean) == {"ok": True, "code": ""}

    (clean / "README.md").write_text("changed\n")
    assert probe(clean)["code"] == "dirty_tree"
