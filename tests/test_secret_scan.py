"""A committed credential fails the secret-scan gate; a clean tree passes it.

`scripts/secret_scan.py` is the object under test. The git-backed scopes run
against a throwaway repository built with `tests/subprocess_env.hermetic_env`,
so the host's git config cannot decide the outcome, and the file-backed scope
runs against files this test writes.

Every value is assembled at runtime (`"AKIA" + "…"`), so no rule-shaped literal
sits in this file: the scanner's own `--all` run reads it and has to stay clean.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.subprocess_env import hermetic_env

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "secret_scan.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "secret-scan.yml"
ALLOWLIST = REPO_ROOT / ".github" / "secrets-allowlist.txt"

#: Rule-shaped values, split so the source of this file carries no match.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLZ"
AWS_SECRET = "wJalr" + "XUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
GENERIC = "Xk9m" + "Q2vR7pL4nT8wZ1sB"
GH_TOKEN = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz"
PRIVATE_BLOCK = "-----BEGIN " + "RSA PRIVATE KEY-----"


def run(args: list[str], *, root: Path = REPO_ROOT, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(root), env=env, capture_output=True, text=True, check=False,
    )


@pytest.fixture()
def sandbox(tmp_path: Path) -> dict[str, object]:
    """A git repository whose only content is what each test commits."""
    work = tmp_path / "repo"
    work.mkdir()
    env = hermetic_env(
        PATH=os.environ.get("PATH", ""),
        HOME=str(tmp_path),
        GIT_AUTHOR_NAME="sandbox",
        GIT_AUTHOR_EMAIL="sandbox@example.invalid",
        GIT_COMMITTER_NAME="sandbox",
        GIT_COMMITTER_EMAIL="sandbox@example.invalid",
    )

    def git(*args: str) -> None:
        done = subprocess.run(["git", *args], cwd=str(work), env=env,
                              capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr

    git("init", "-q", ".")
    (work / "clean.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    return {"work": work, "env": env, "git": git}


def test_a_planted_aws_key_fails_and_names_the_rule(tmp_path: Path) -> None:
    target = tmp_path / "leak.py"
    target.write_text(f'AWS_ACCESS_KEY_ID = "{AWS_KEY}"\n', encoding="utf-8")
    result = run(["--files", str(target)])
    assert result.returncode == 1
    assert "aws-access-key-id" in result.stdout
    assert str(target) in result.stdout


def test_the_value_is_never_printed(tmp_path: Path) -> None:
    """A leak the scanner repeats is a second leak: only a prefix and a length."""
    target = tmp_path / "leak.py"
    target.write_text(f'AWS_ACCESS_KEY_ID = "{AWS_KEY}"\n', encoding="utf-8")
    result = run(["--files", str(target)])
    assert AWS_KEY not in result.stdout
    assert AWS_KEY not in result.stderr
    assert AWS_KEY[:4] in result.stdout


def test_a_clean_file_passes(tmp_path: Path) -> None:
    target = tmp_path / "clean.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert run(["--files", str(target)]).returncode == 0


def test_a_generic_password_assignment_fails(tmp_path: Path) -> None:
    """The keyword may embed itself: `db_password = "…"` is the leak `\\b` missed."""
    target = tmp_path / "conf.ini"
    target.write_text(f'db_password = "{GENERIC}"\n', encoding="utf-8")
    result = run(["--files", str(target)])
    assert result.returncode == 1
    assert "generic-secret-assignment" in result.stdout


def test_a_css_custom_property_name_is_not_a_finding(tmp_path: Path) -> None:
    """A palette entry is `token="--color-figure-plate"`, and the keyword rule saw a secret.

    The value is a name: a credential does not start with two hyphens and does not read
    as a word, which is the check this pins.
    """
    target = tmp_path / "brand_palette.py"
    target.write_text('token="--color-figure-plate",\n', encoding="utf-8")
    result = run(["--files", str(target)])
    assert result.returncode == 0, result.stdout


def test_a_provider_prefix_and_a_private_key_block_are_each_found(tmp_path: Path) -> None:
    gh = tmp_path / "a.ts"
    gh.write_text(f'const token = "{GH_TOKEN}";\n', encoding="utf-8")
    pem = tmp_path / "b.pem"
    pem.write_text(PRIVATE_BLOCK + "\n", encoding="utf-8")
    result = run(["--files", str(gh), str(pem)])
    assert result.returncode == 1
    assert "private-key-block" in result.stdout
    assert "github-token" in result.stdout


def test_the_specific_rule_wins_over_the_generic_one(tmp_path: Path) -> None:
    """One finding per value, reported under the rule that named it exactly."""
    target = tmp_path / "leak.py"
    target.write_text(f'AWS_ACCESS_KEY_ID = "{AWS_KEY}"\n', encoding="utf-8")
    result = run(["--files", str(target)])
    assert result.stdout.count(AWS_KEY[:4]) == 1
    assert "generic-secret-assignment" not in result.stdout


def test_a_line_marker_exempts_that_line(tmp_path: Path) -> None:
    target = tmp_path / "fixture.py"
    target.write_text(f'client_secret = "{GENERIC}"  # secret-scan: allow\n',
                      encoding="utf-8")
    assert run(["--files", str(target)]).returncode == 0


def test_the_allowlist_exempts_a_value(tmp_path: Path) -> None:
    target = tmp_path / "fixture.py"
    target.write_text(f'client_secret = "{GENERIC}"\n', encoding="utf-8")
    allowlist = tmp_path / "allow.txt"
    allowlist.write_text(f"# a reviewed acceptance\n{GENERIC}\n", encoding="utf-8")
    result = run(["--files", str(target), "--allowlist", str(allowlist)])
    assert result.returncode == 0


def test_a_path_entry_exempts_a_whole_file(tmp_path: Path) -> None:
    target = tmp_path / "fixture.py"
    target.write_text(f'client_secret = "{GENERIC}"\n', encoding="utf-8")
    allowlist = tmp_path / "allow.txt"
    allowlist.write_text("path:*fixture.py\n", encoding="utf-8")
    result = run(["--files", str(target), "--allowlist", str(allowlist)])
    assert result.returncode == 0


def test_an_unreadable_path_is_no_verdict_and_not_a_pass(tmp_path: Path) -> None:
    """An unscanned input is not a clean one: exit 2, never 0."""
    result = run(["--files", str(tmp_path / "missing.py")])
    assert result.returncode == 2
    assert "NO VERDICT" in result.stderr


def test_all_catches_a_tracked_secret(sandbox: dict[str, object]) -> None:
    work: Path = sandbox["work"]  # type: ignore[assignment]
    (work / "leak.py").write_text(f'api_key = "{GENERIC}"\n', encoding="utf-8")
    sandbox["git"]("add", "-A")  # type: ignore[operator]
    sandbox["git"]("commit", "-qm", "leak")  # type: ignore[operator]
    result = run(["--all", "--root", str(work)], env=sandbox["env"])  # type: ignore[arg-type]
    assert result.returncode == 1
    assert "leak.py" in result.stdout


def test_range_catches_a_secret_removed_in_the_same_push(sandbox: dict[str, object]) -> None:
    """HEAD is clean, the history is not: only the added-line view sees the leak."""
    work: Path = sandbox["work"]  # type: ignore[assignment]
    (work / "leak.py").write_text(f'api_key = "{GENERIC}"\n', encoding="utf-8")
    sandbox["git"]("add", "-A")  # type: ignore[operator]
    sandbox["git"]("commit", "-qm", "add leak")  # type: ignore[operator]
    (work / "leak.py").unlink()
    sandbox["git"]("add", "-A")  # type: ignore[operator]
    sandbox["git"]("commit", "-qm", "remove leak")  # type: ignore[operator]

    env = sandbox["env"]
    assert run(["--all", "--root", str(work)], env=env).returncode == 0  # type: ignore[arg-type]
    ranged = run(["--range", "HEAD~2..HEAD", "--root", str(work)], env=env)  # type: ignore[arg-type]
    assert ranged.returncode == 1
    assert "leak.py" in ranged.stdout


def test_staged_catches_a_secret_in_the_index(sandbox: dict[str, object]) -> None:
    work: Path = sandbox["work"]  # type: ignore[assignment]
    (work / "staged.py").write_text(f'password = "{GENERIC}"\n', encoding="utf-8")
    sandbox["git"]("add", "-A")  # type: ignore[operator]
    result = run(["--staged", "--root", str(work)], env=sandbox["env"])  # type: ignore[arg-type]
    assert result.returncode == 1
    assert "staged.py" in result.stdout


def test_the_workflow_wires_the_scan_and_cannot_warn_through() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/secret_scan.py --all" in text
    assert "--range" in text
    assert "continue-on-error:" not in text
    assert "permissions:" in text and "contents: read" in text
    assert "persist-credentials: false" in text
    assert "vars.CI_LINUX_RUNNER" in text
    for ref in re.findall(r"uses:\s*([^\s@]+)@(\S+)", text):
        assert re.fullmatch(r"[0-9a-f]{40}", ref[1]), f"unpinned action {ref[0]}@{ref[1]}"


def test_the_allowlist_file_exists_and_documents_its_format() -> None:
    text = ALLOWLIST.read_text(encoding="utf-8")
    assert "path:" in text
    assert "secret-scan" in text or "secret_scan" in text


def test_the_tracked_tree_is_clean_today() -> None:
    """The gate the workflow runs must be green on the tree it landed in."""
    result = run(["--all"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 finding(s)" in result.stderr
