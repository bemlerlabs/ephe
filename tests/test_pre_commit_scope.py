"""The pre-commit hook must stay out of parts of the worktree it is not for.

Pinned because it went wrong twice on a shared tree. lint-staged hides every
*unstaged* change before running its tasks and puts them back afterwards — so a
commit that touches nothing in `app/` still rewrites files other workers hold open
(2026-10-08: five translation workers died mid-package), and it can fold their
unfinished work into this commit (2026-10-09: a prose-only commit carried
`app/public/llms.txt`).

The hook reads these files as data on purpose: the rule is about the shipped
pipeline, not about a Python function.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = (ROOT / ".husky" / "pre-commit").read_text(encoding="utf-8")
LINT_STAGED_CONFIG = (ROOT / "app" / "lint-staged.config.js").read_text(encoding="utf-8")


def _staged_sources_match() -> re.Pattern[str]:
    """The predicate the hook actually ships, read out of the hook rather than retyped."""
    match = re.search(r"grep -qE '([^']+)'", HOOK)
    assert match, "the hook must gate lint-staged behind one grep -qE pattern"
    return re.compile(match.group(1))


class TestFrontendGuard:
    def test_given_the_hook_when_it_is_read_then_lint_staged_is_conditional(self):
        """GIVEN the pre-commit hook WHEN its body is inspected THEN lint-staged
        runs only inside a condition, never as the first unconditional command.
        """
        assert "lint-staged" in HOOK
        guard_line = HOOK.index("pnpm exec lint-staged")
        condition = HOOK[:guard_line]
        assert "if " in condition and "grep -qE" in condition, (
            "lint-staged must sit behind the staged-files guard"
        )

    def test_when_the_guard_is_applied_then_only_frontend_sources_pass(self):
        """GIVEN the shipped pattern WHEN it sees candidate staged lists THEN the
        decision depends on `app/` TypeScript sources and on nothing else.
        """
        pattern = _staged_sources_match()
        must_run = ["app/src/lib/duration.ts", "app/src/App.tsx", "app/playwright.config.ts"]
        must_skip = [
            "core/quality.py",
            "docs/release-notes.md",
            "application/notes.py",   # starts with "app", is not the frontend
            "webapp/src/main.ts",     # ends with .ts, is not app/
            "app/src/x.ts.bak",       # the pattern is anchored: a backup is not a source
            "scripts/architecture_check.mjs",
        ]
        assert [bool(pattern.search(p)) for p in must_run] == [True] * len(must_run)
        assert [bool(pattern.search(p)) for p in must_skip] == [False] * len(must_skip)

    def test_the_language_gate_is_not_gated_away(self):
        """The reason the hook exists at all has to keep running for every commit."""
        assert "scripts/language_gate.py" in HOOK
        assert HOOK.index("pnpm exec lint-staged") < HOOK.index("scripts/language_gate.py")


class TestPnpmRunsWithoutATerminal:
    def test_every_pnpm_invocation_exports_ci(self):
        """GIVEN the hook WHEN it runs pnpm in a worktree with no terminal THEN CI=true is set.

        pnpm reads a missing TTY as a question it cannot ask and aborts, so the
        frontend toolchain never reaches prettier, eslint or lint-staged. CI=true
        is the switch that keeps it non-interactive, and each pnpm call sits in its
        own subshell, so the export has to travel with every call.
        """
        pnpm_lines = [line for line in HOOK.splitlines() if "pnpm exec" in line]
        assert pnpm_lines, "the frontend toolchain still runs through pnpm"
        for line in pnpm_lines:
            assert "CI=true" in line, f"pnpm without CI=true aborts with no TTY: {line}"


class TestNoUnboundedStaging:
    def test_the_lint_staged_config_carries_no_git_add(self):
        """`git add` as a task is legacy: lint-staged has re-staged task output
        since v10, and a bare `git add` is the only command in the pipeline that
        can widen a commit beyond the paths the chief staged.

        Comments are stripped first — the config explains why it has no `git add`,
        and that sentence must not fail the rule it describes.
        """
        code = "\n".join(
            line for line in LINT_STAGED_CONFIG.splitlines() if not line.strip().startswith("//")
        )
        assert "git add" not in code
        assert "prettier --write" in code
        assert "eslint --fix" in code


class TestADeletionDoesNotEndTheHook:
    """A declared frontend path that is a deletion must not stop the hook.

    The filter exists because prettier refuses an argument that is not on disk, so an
    unfiltered list would block every rename and every deletion. Spelled `[ -f … ] && …` it
    blocks them anyway and silently: a false test in the last loop turn makes the command
    substitution exit 1, `set -e` is on, and the commit is refused with nothing on either
    stream. Measured 2026-10-15 on a commit that removed two frontend test files.
    """

    def test_the_filter_survives_a_path_that_is_gone(self, tmp_path):
        line = next(
            (ln for ln in HOOK.splitlines() if ln.strip().startswith("live=$(for t in $targets")),
            "",
        )
        assert line, "the hook no longer filters the declared app paths"
        targets = "src/components/dashboard/Gone.test.tsx"
        script = f'set -e\ntargets="{targets}"\napp={tmp_path}\n' + line + '\nprintf "%s" "$live"'
        done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=tmp_path)
        assert done.returncode == 0, (
            f"a deletion in the declared paths ends the hook (exit {done.returncode}): "
            f"{done.stderr.strip() or 'no message'}"
        )
        assert done.stdout == "", "a path that does not exist must not reach the formatter"
