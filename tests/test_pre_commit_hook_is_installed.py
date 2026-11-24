"""The pre-commit hook is a promise AGENTS.md makes, so it gets the one thing a promise needs.

`AGENTS.md` "Hooks stay on" tells an agent that a commit runs the checks CI runs. Until 2026-11-24
that sentence was false in a fresh clone: `.husky/pre-commit` was checked in with its executable
bit, `app/package.json` carried husky as a devDependency with no `prepare` script to run it, and
nothing anywhere set `core.hooksPath`, so git never looked at the file. The private checkout had
the key set by hand, which is how the gap survived.

The cases read a shell script, a Makefile recipe and the hub's own sentence because the constraint
exists only in files the product cannot import - the same reason `tests/test_macos_usage_strings.py`
reads an Info.plist and `tests/test_dev_handle_gate.py` reads the shipped bundle. A commit is then
proved the honest way: `make -n hooks` runs the real target, and the live refusal is measured in
the report that ships with this file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".husky" / "pre-commit"
PUSH_HOOK = REPO / ".husky" / "pre-push"
HOOKS_PATH_VALUE = ".husky"


def git(*args: str) -> str:
    """One git call against this checkout; the suite runs inside a clone by definition."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def tracked_mode(path: Path) -> str | None:
    """The mode git recorded for `path`, which is what a fresh clone gets, or None."""
    rel = str(path.relative_to(REPO))
    for line in git("ls-files", "-s", "--", rel).splitlines():
        fields = line.split()
        if fields and fields[-1] == rel:
            return fields[0]
    return None


class TestTheHookIsTheCheckedInOne:
    def test_the_hook_is_tracked_with_its_executable_bit(self):
        """A fresh clone gets a runnable file, which is the difference between a hook and a note."""
        assert tracked_mode(HOOK) == "100755", "the tracked mode is not executable"
        assert tracked_mode(PUSH_HOOK) == "100755", "the tracked mode is not executable"
        assert HOOK.is_file() and HOOK.stat().st_mode & 0o111, "the working copy lost its bit"

    def test_the_hook_runs_the_local_ci_and_the_two_rules_the_hook_owes(self):
        body = HOOK.read_text(encoding="utf-8")
        for call in (
            "bash scripts/ci_local.sh",
            "scripts/language_gate.py --staged",
            "scripts/attribution_check.py --identity",
        ):
            assert call in body, f"the hook no longer runs {call}; the promise in AGENTS.md is then false"

    def test_a_hook_implementation_lives_in_exactly_one_tracked_place(self):
        """One home per fact covers the hook: nothing beside .husky may go stale with it."""
        tracked = [line for line in git("ls-files").splitlines() if line.endswith(("pre-commit", "pre-push"))]
        assert sorted(tracked) == [".husky/pre-commit", ".husky/pre-push"], tracked


class TestACloneKnowsHowToTurnItOn:
    def test_make_hooks_sets_hooks_path_at_the_checked_in_directory(self):
        # GIVEN the command AGENTS.md names
        proc = subprocess.run(
            ["make", "-n", "hooks"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        # THEN the target exists and the recipe is the config call git actually honours
        assert proc.returncode == 0, proc.stderr
        recipe = proc.stdout
        assert f"git config core.hooksPath {HOOKS_PATH_VALUE}" in recipe, recipe

    def test_make_hooks_refuses_to_claim_success_over_a_hook_it_cannot_run(self):
        recipe = subprocess.run(
            ["make", "-n", "hooks"], cwd=REPO, capture_output=True, text=True, check=False
        ).stdout
        assert "-x .husky/pre-commit" in recipe, "the target no longer checks the bit before trusting it"

    def test_the_hub_names_the_command_and_the_file_it_points_at(self):
        hub = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        sentence = hub[hub.index("Hooks stay on") :]
        assert "make hooks" in sentence, "the rule moved away from the command that satisfies it"
        assert ".husky/pre-commit" in sentence, "the rule no longer names the file that runs"
        assert "--no-verify" in sentence, "the refusal an agent needs is gone from the rule"

    def test_doctor_reports_the_state_a_contributor_can_act_on(self):
        recipe = subprocess.run(
            ["make", "-n", "doctor"], cwd=REPO, capture_output=True, text=True, check=False
        ).stdout
        assert "core.hooksPath" in recipe, "doctor no longer reports whether a commit is checked"


class TestTheHookIsValidShell:
    def test_the_hook_and_the_local_ci_parse_as_shell_and_python(self):
        # GIVEN a hook that runs with no terminal and no tolerance for a syntax slip
        for script in (HOOK, PUSH_HOOK):
            proc = subprocess.run(
                ["bash", "-n", str(script)], capture_output=True, text=True, check=False
            )
            assert proc.returncode == 0, f"{script.name}: {proc.stderr}"
        local = REPO / "scripts" / "ci_local.sh"
        proc = subprocess.run(["bash", "-n", str(local)], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, f"ci_local.sh: {proc.stderr}"

    def test_the_hook_calls_no_network_at_a_fresh_clone(self):
        # GIVEN the paths the hook may reach for: a Python interpreter and, only for TypeScript,
        # the workspace's own binaries through pnpm
        body = HOOK.read_text(encoding="utf-8")
        for forbidden in ("curl ", "wget ", "npm install", "pnpm install", "pip install", "npx "):
            assert forbidden not in body, f"the hook now depends on {forbidden.strip()}, a boot-time network call"
        assert "pnpm exec" in body, "the front-end leg lost its offline binary call"
