"""A commit that declares its paths must not be able to ship another worker's staged work.

The class is recorded in `.husky/pre-commit` itself: 2026-10-08, lint-staged's
hide-and-restore rewrote files five workers held open; 2026-10-09, a prose-only commit
carried another worker's `app/public/llms.txt`; 2026-10-11, a docs commit carried
`core/model_config.py` mid-flight and HEAD grew a docstring denying the model defaults
that same file still shipped. Each was read afterwards as the other worker's mistake.

What these tests pin is the defence. The actor is a separate question, and the guard is
written so that it does not depend on answering it. A pathspec commit was measured in a
throwaway repository in five shapes — named path staged and unstaged, a directory
pathspec, newly added paths, with and without lint-staged running — and in every one the
foreign staged path stayed in the index. The crossing therefore comes from outside git,
and the guard that does not depend on finding it is the hook refusing a commit whose
index is wider than its declaration.

The hook is run as a real `git commit` runs it, in a repository built under `tmp_path`,
with `pnpm` stubbed to record what the commit asked it to do. The child environment comes
from `tests/subprocess_env` for the reason that file states: the arm64 runner's shared-linked
CPython needs its loader keys carried over, and a hook chain that dies with 127 there would
pass here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.subprocess_env import hermetic_env

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".husky" / "pre-commit"


def _git(env: dict[str, str], cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, check=False
    )


@pytest.fixture()
def sandbox(tmp_path: Path) -> dict[str, Any]:
    """A throwaway repository carrying the real hook and a `pnpm` that only records."""
    work = tmp_path / "repo"
    work.mkdir()
    (work / "scripts").mkdir()
    (work / "app" / "src").mkdir(parents=True)
    (work / "docs").mkdir()
    (work / "other").mkdir()

    # The hook's own two downstream calls, stubbed to pass. Which paths a commit may
    # carry is what this file judges; what those two gates say about a path is their own
    # rule and lives in their own tests.
    (work / "scripts" / "language_gate.py").write_text("import sys\n", encoding="utf-8")
    (work / "scripts" / "ci_local.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "pnpm-calls.log"
    stub = bin_dir / "pnpm"
    stub.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$PNPM_LOG\"\nexit 0\n", encoding="utf-8"
    )
    stub.chmod(0o755)

    # The hook calls `python3` by name. Resolved from PATH that is whatever the host
    # happens to carry, which on the arm64 leg is not the interpreter running this test;
    # the shim pins it to `sys.executable`, the same discipline `tests/subprocess_env.py`
    # exists for.
    python_stub = bin_dir / "python3"
    python_stub.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    python_stub.chmod(0o755)

    for name, body in {
        "docs/mine.md": "mine\n",
        "other/theirs.py": "theirs = 1\n",
        "app/src/a.ts": "export const a = 1\n",
        "app/src/b.ts": "export const b = 1\n",
    }.items():
        (work / name).write_text(body, encoding="utf-8")

    env = hermetic_env(
        HOME=str(tmp_path),
        PATH=os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]),
        PNPM_LOG=str(log),
        GIT_AUTHOR_NAME="sandbox",
        GIT_AUTHOR_EMAIL="sandbox@example.invalid",
        GIT_COMMITTER_NAME="sandbox",
        GIT_COMMITTER_EMAIL="sandbox@example.invalid",
    )
    init = _git(env, work, "init", "-q", ".")
    assert init.returncode == 0, init.stderr

    # After `init`, so the directory is git's own and this is the only hook the sandbox
    # repository has. The base commit is taken with it already in place: the guard passes
    # there, and a test that broke that would fail on `base` rather than on itself.
    hooks = work / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
    hook.chmod(0o755)

    base = _git(env, work, "add", "-A")
    assert base.returncode == 0, base.stderr
    committed = _git(env, work, "commit", "-qm", "base")
    assert committed.returncode == 0, committed.stderr
    return {"work": work, "env": env, "log": log}


def commit(env: dict[str, str], work: Path, message: str, pathspec: list[str], declared: str | None):
    """One `git commit -- <paths>`, with or without the declaration.

    The recorder is cleared first: the fixture's own base commit runs the hook too, and a
    test that reads the log after this call must read what this commit asked for.
    """
    sandbox_log(env).write_text("", encoding="utf-8")
    child = dict(env)
    if declared is not None:
        child["EPHE_COMMIT_PATHS"] = declared
    return subprocess.run(
        ["git", "commit", "-m", message, "--", *pathspec],
        cwd=str(work),
        env=child,
        capture_output=True,
        text=True,
        check=False,
    )


def sandbox_log(env: dict[str, str]) -> Path:
    return Path(env["PNPM_LOG"])


def touch(work: Path, name: str, body: str) -> None:
    (work / name).write_text(body, encoding="utf-8")


def test_declared_commit_refuses_an_index_wider_than_its_word(sandbox: dict[str, Any]) -> None:
    """The defect, and the only shape that catches it without knowing the actor.

    `other/theirs.py` is staged by a second strand. The commit names one document. Before
    the guard existed the commit shipped, and the second strand's unfinished line became
    this repository's stated truth under the first strand's message.
    """
    work, env = sandbox["work"], sandbox["env"]
    touch(work, "docs/mine.md", "mine v2\n")
    touch(work, "other/theirs.py", "theirs = 2\n")
    assert _git(env, work, "add", "docs/mine.md", "other/theirs.py").returncode == 0
    before = _git(env, work, "rev-parse", "HEAD").stdout.strip()

    result = commit(env, work, "docs: only mine", ["docs/mine.md"], "docs/mine.md")

    assert result.returncode != 0, (
        "a declared commit shipped a staged path it never declared:\n" + result.stdout
    )
    assert "other/theirs.py" in result.stderr, result.stderr
    assert "docs/mine.md" in _git(env, work, "diff", "--cached", "--name-only").stdout
    assert _git(env, work, "rev-parse", "HEAD").stdout.strip() == before, "the refused commit moved HEAD"


def test_a_declaration_that_covers_the_index_ships(sandbox: dict[str, Any]) -> None:
    """No false refusal: naming every staged path is exactly what the guard asks for."""
    work, env = sandbox["work"], sandbox["env"]
    touch(work, "docs/mine.md", "mine v2\n")
    touch(work, "other/theirs.py", "theirs = 2\n")
    assert _git(env, work, "add", "docs/mine.md", "other/theirs.py").returncode == 0

    result = commit(
        env, work, "docs: both paths declared", ["docs/mine.md"], "docs/mine.md other/theirs.py"
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_undeclared_commit_keeps_the_pass_it_had(sandbox: dict[str, Any]) -> None:
    """A commit that does not declare is left alone: the guard is opt-in by declaration."""
    work, env = sandbox["work"], sandbox["env"]
    touch(work, "app/src/a.ts", "export const a = 2\n")
    assert _git(env, work, "add", "app/src/a.ts").returncode == 0

    result = commit(env, work, "ts: undeclared", ["app/src/a.ts"], None)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "exec lint-staged" in sandbox["log"].read_text(encoding="utf-8")


def test_declared_commit_formats_its_own_paths_and_no_others(sandbox: dict[str, Any]) -> None:
    """The frontend pass goes from the whole staged set to the declared paths."""
    work, env = sandbox["work"], sandbox["env"]
    touch(work, "app/src/a.ts", "export const a = 2\n")
    touch(work, "app/src/b.ts", "export const b = 2\n")
    assert _git(env, work, "add", "app/src/a.ts").returncode == 0

    result = commit(env, work, "ts: declared", ["app/src/a.ts"], "app/src/a.ts")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = sandbox["log"].read_text(encoding="utf-8")
    assert "exec prettier --write src/a.ts" in calls, calls
    assert "exec eslint --fix src/a.ts" in calls, calls
    assert "lint-staged" not in calls, calls
    assert "b.ts" not in calls, "a declared commit formatted a path it never named"
