"""A commit is refused only by a verdict a gate actually reached.

`scripts/ci_local.sh` runs three instruments over the staged blobs and turns their exit
statuses into a refusal. Two different things can produce a non-zero status: the check
decided that the commit is wrong, and the check died before deciding anything. The script
used to fold both into one message and one code, and the pipeline shape made the second one
common: `git show :path | ruff` under `pipefail` reports the writer's signal death as the
pipeline status whenever ruff exits before draining stdin, so a clean blob came back as
status 141 and was reported as "a usage error, which means scripts/lint_policy.sh carries a
code ruff does not know". The repo-verify lane was refused three commits that way on
2026-10-11 (`out/lane/74-report.md`), on the excluded `evals/repo_verify` paths, where ruff
finishes fastest.

These tests run the real script against a real git repository with the instruments stubbed,
and hold the two exit paths apart: 1 for a verdict that refuses, 3 for a check that never
reached one. The pipe-closing case is the one that used to refuse a good commit, so it is
asserted as a pass.

The child environment comes from `tests/subprocess_env`, and `python3` and `mypy` are pinned
to stubs in the same directory as the stub `ruff`, so the sandbox measures the script rather
than whatever the host happens to carry.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.subprocess_env import hermetic_env

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ci_local.sh"
POLICY = REPO_ROOT / "scripts" / "lint_policy.sh"

#: A blob big enough that a consumer which never reads stdin leaves `git show` mid-write.
PAD = "# a line long enough to make the blob worth writing " * 4


@pytest.fixture()
def sandbox(tmp_path: Path) -> dict[str, Any]:
    """A repository whose only instruments are the stubs this test controls."""
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    shutil.copyfile(SCRIPT, work / "scripts" / "ci_local.sh")
    shutil.copyfile(POLICY, work / "scripts" / "lint_policy.sh")
    (work / "scripts" / "hygiene_check.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (work / "scripts" / "prose_scope_check.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (work / "clean.py").write_text("import os\n" + "".join(f"{PAD}\n" for _ in range(400)), encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def exe(name: str, body: str) -> None:
        path = bin_dir / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    exe("python3", f'exec "{sys.executable}" "$@"')
    exe("mypy", "exit 0")
    exe(
        "ruff",
        """
case "$RUFF_STUB_MODE" in
  ok)       cat > /dev/null; exit 0 ;;
  early)    exit 0 ;;
  findings) cat > /dev/null; echo "$1:1:1: E901 syntax error"; exit 1 ;;
  die)      cat > /dev/null; kill -TERM $$ ;;
esac
exit 0
""",
    )

    env = hermetic_env(
        HOME=str(tmp_path),
        PATH=os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]),
        GIT_AUTHOR_NAME="sandbox",
        GIT_AUTHOR_EMAIL="sandbox@example.invalid",
        GIT_COMMITTER_NAME="sandbox",
        GIT_COMMITTER_EMAIL="sandbox@example.invalid",
    )
    init = subprocess.run(["git", "init", "-q", "."], cwd=str(work), env=env, capture_output=True, text=True, check=False)
    assert init.returncode == 0, init.stderr
    subprocess.run(["git", "add", "-A"], cwd=str(work), env=env, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=str(work), env=env, check=True)
    return {"work": work, "env": env}


def run_gate(sandbox: dict[str, Any], mode: str) -> subprocess.CompletedProcess[str]:
    """One gate run over a staged python blob, with the instrument in `mode`."""
    env = dict(sandbox["env"])
    env["RUFF_STUB_MODE"] = mode
    env["EPHE_COMMIT_PATHS"] = "clean.py"
    # The gate reads the STAGED blob, so the file has to differ from its base commit for
    # there to be a scope at all.
    (sandbox["work"] / "clean.py").write_text(
        "import os\n" + "".join(f"{PAD} # {mode}\n" for _ in range(400)), encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "clean.py"], cwd=str(sandbox["work"]), env=env, check=True
    )
    return subprocess.run(
        ["bash", "scripts/ci_local.sh"],
        cwd=str(sandbox["work"]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_check_that_reads_all_of_stdin_and_passes_passes(sandbox: dict[str, Any]) -> None:
    result = run_gate(sandbox, "ok")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ci-local: pass" in result.stdout


def test_an_instrument_that_never_reads_stdin_does_not_refuse_the_commit(
    sandbox: dict[str, Any],
) -> None:
    """The refused-good-commit case, and the reason stdin is a file and not a pipe.

    `early` is ruff finishing without draining: under the old pipeline `git show` is still
    writing when the reader goes away, pipefail hands back 141, and the gate reports a usage
    error for a file nobody checked.
    """
    result = run_gate(sandbox, "early")

    assert "141" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ci-local: pass" in result.stdout


def test_a_real_finding_refuses_with_the_verdict_code(sandbox: dict[str, Any]) -> None:
    """The other exit path, which must stay distinguishable from a dead instrument."""
    result = run_gate(sandbox, "findings")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL ruff: blocking finding in the staged blob clean.py" in result.stdout
    assert "NO VERDICT" not in result.stdout


def test_a_killed_instrument_refuses_with_the_no_verdict_code(sandbox: dict[str, Any]) -> None:
    result = run_gate(sandbox, "die")

    assert result.returncode == 3, result.stdout + result.stderr
    assert "NO VERDICT ruff died with signal 15 on clean.py" in result.stdout
    assert "blocking finding" not in result.stdout, "a dead check blamed the commit"
