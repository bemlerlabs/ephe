"""The docker-lint ratchet's decisions, driven by stubbed lint binaries.

`scripts/docker_lint.py` shells out to hadolint and shellcheck, and neither is a dependency of this
project: a test that needed the real binaries would either skip (and the ratchet would be a gate no
machine had ever seen judge) or fail on a fresh checkout. The stubs below answer `--version` and
`--format json` from an environment variable, so the five branches the owner relies on are all
exercised offline against the same code path the CI leg runs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.subprocess_env import hermetic_env

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docker_lint.py"

HADOLINT_STUB = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "Haskell Dockerfile Linter ${FAKE_HADOLINT_VERSION}"; exit 0; fi
printf '%s' "${FAKE_HADOLINT_JSON}"
"""
SHELLCHECK_STUB = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then printf 'ShellCheck\\nversion: %s\\n' "${FAKE_SC_VERSION}"; exit 0; fi
printf '%s' "${FAKE_SC_JSON}"
"""


def hadolint_finding(code: str, line: int = 7) -> dict:
    return {"code": code, "column": 1, "file": "Dockerfile", "level": "warning",
            "line": line, "message": f"planted {code}"}


def shellcheck_finding(code: int, file: str = "install.sh") -> dict:
    return {"file": file, "line": 3, "column": 1, "level": "warning", "code": code,
            "message": f"planted SC{code}", "fix": None}


def make_stub(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def baseline(tmp_path: Path, rules: dict[str, int], *, hadolint: str = "2.15.1",
             shellcheck: str = "0.11.0") -> Path:
    path = tmp_path / "docker-lint-baseline.json"
    path.write_text(json.dumps({
        "policy": "docker-lint-ratchet", "version": 1, "instrument": "scripts/docker_lint.py",
        "hadolint_version": hadolint, "shellcheck_version": shellcheck,
        "measured_at": "2026-10-11", "rules": rules,
    }, indent=2) + "\n", encoding="utf-8")
    return path


def run(tmp_path: Path, argv: list[str], hadolint_json: str = "[]",
        shellcheck_json: str = "[]") -> subprocess.CompletedProcess[str]:
    stubs = {
        "EPHE_HADOLINT_BIN": make_stub(tmp_path, "hadolint", HADOLINT_STUB),
        "EPHE_SHELLCHECK_BIN": make_stub(tmp_path, "shellcheck", SHELLCHECK_STUB),
    }
    env = hermetic_env(
        PATH=os.environ["PATH"],
        FAKE_HADOLINT_VERSION="2.15.1", FAKE_SC_VERSION="0.11.0",
        FAKE_HADOLINT_JSON=hadolint_json, FAKE_SC_JSON=shellcheck_json,
        EPHE_HADOLINT_BIN=str(stubs["EPHE_HADOLINT_BIN"]),
        EPHE_SHELLCHECK_BIN=str(stubs["EPHE_SHELLCHECK_BIN"]),
    )
    return subprocess.run([sys.executable, str(SCRIPT), *argv], env=env, text=True,
                          capture_output=True, check=False, cwd=ROOT)


class TestRatchetBranches:
    def test_a_rule_the_baseline_never_recorded_is_a_regression(self, tmp_path):
        file = baseline(tmp_path, {"DL3008": 2})
        done = run(tmp_path, ["--baseline", str(file)],
                   hadolint_json=json.dumps([hadolint_finding("DL3008"), hadolint_finding("DL3025")]))
        assert done.returncode == 1, done.stdout
        assert "DL3025: 1 finding(s) of a rule the baseline never recorded" in done.stdout, done.stdout

    def test_a_count_above_its_ceiling_names_both_numbers(self, tmp_path):
        file = baseline(tmp_path, {"SC2155": 3})
        done = run(tmp_path, ["--baseline", str(file)],
                   shellcheck_json=json.dumps([shellcheck_finding(2155) for _ in range(4)]))
        assert done.returncode == 1, done.stdout
        assert "SC2155: 4 finding(s) over the recorded 3" in done.stdout, done.stdout

    def test_a_clean_tree_passes_and_reports_what_can_be_lowered(self, tmp_path):
        file = baseline(tmp_path, {"DL3008": 2, "SC2155": 12})
        done = run(tmp_path, ["--baseline", str(file)],
                   hadolint_json=json.dumps([hadolint_finding("DL3008")]))
        assert done.returncode == 0, done.stdout + done.stderr
        assert "pass" in done.stdout, done.stdout
        assert "SC2155: 12 -> 0" in done.stdout, done.stdout
        assert "DL3008: 2 -> 1" in done.stdout, done.stdout

    def test_tool_drift_refuses_because_the_counts_belong_to_the_versions(self, tmp_path):
        file = baseline(tmp_path, {"DL3008": 1}, hadolint="2.12.0")
        done = run(tmp_path, ["--baseline", str(file)],
                   hadolint_json=json.dumps([hadolint_finding("DL3008")]))
        assert done.returncode == 1, done.stdout
        assert "tool drift" in done.stdout and "2.12.0" in done.stdout, done.stdout


class TestUpdateCanOnlyLower:
    def test_update_refuses_a_tree_that_grew(self, tmp_path):
        file = baseline(tmp_path, {"SC2155": 3})
        done = run(tmp_path, ["--baseline", str(file), "--update"],
                   shellcheck_json=json.dumps([shellcheck_finding(2155) for _ in range(5)]))
        assert done.returncode == 1, done.stdout
        assert "REFUSED SC2155: 5 against the recorded 3" in done.stdout, done.stdout
        assert "cannot widen it" in done.stdout, done.stdout
        assert json.loads(file.read_text(encoding="utf-8"))["rules"] == {"SC2155": 3}, "the file moved"

    def test_update_lowers_a_tree_that_shrank(self, tmp_path):
        file = baseline(tmp_path, {"DL3008": 2, "SC2155": 12})
        done = run(tmp_path, ["--baseline", str(file), "--update"],
                   hadolint_json=json.dumps([hadolint_finding("DL3008")]))
        assert done.returncode == 0, done.stdout
        rules = json.loads(file.read_text(encoding="utf-8"))["rules"]
        assert rules == {"DL3008": 1}, rules
        assert "lowered" in done.stdout, done.stdout

    def test_update_with_nothing_to_change_says_so(self, tmp_path):
        file = baseline(tmp_path, {"DL3008": 1})
        done = run(tmp_path, ["--baseline", str(file), "--update"],
                   hadolint_json=json.dumps([hadolint_finding("DL3008")]))
        assert done.returncode == 0, done.stdout
        assert "nothing to lower" in done.stdout, done.stdout


class TestMissingToolIsNamed:
    def test_a_binary_that_does_not_resolve_refuses_naming_the_release(self, tmp_path):
        file = baseline(tmp_path, {})
        empty = tmp_path / "empty-bin"
        empty.mkdir()
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--baseline", str(file)],
            # An empty PATH is the plant: nothing may resolve `hadolint`. The loader keys still cross
        # over, or the child dies on its own shared library before it reaches the refusal this test
        # pins. `resolve()` runs before `git`, so the empty PATH is what the step sees first.
        env=hermetic_env(PATH=str(empty), HOME=str(tmp_path)),
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode == 2, done.stdout + done.stderr
        combined = done.stdout + done.stderr
        assert "hadolint did not resolve" in combined, combined
        assert "v2.15.1" in combined, combined
        assert "Traceback" not in combined, combined

    def test_a_path_that_is_not_executable_is_refused_as_itself(self, tmp_path):
        file = baseline(tmp_path, {})
        fake = tmp_path / "hadolint"
        fake.write_text("not a binary\n", encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--baseline", str(file)],
            env=hermetic_env(PATH=os.environ["PATH"], EPHE_HADOLINT_BIN=str(fake),
                             EPHE_SHELLCHECK_BIN=str(fake)),
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode != 0, done.stdout + done.stderr
        assert "not an executable file" in done.stdout + done.stderr


class TestCommittedBaselineIsHonest:
    def test_the_file_matches_the_instrument_it_ships_with(self):
        """A baseline written by hand is a claim about a tool run.

        The keys and the pinned versions are what `scripts/docker_lint.py` writes; this reads the
        committed file and refuses drift in the shape, so the numbers in the file cannot be edited into
        a pass without the tools agreeing.
        """
        raw = json.loads((ROOT / "scripts" / "docker-lint-baseline.json").read_text(encoding="utf-8"))
        assert raw["policy"] == "docker-lint-ratchet" and raw["version"] == 1
        assert raw["instrument"] == "scripts/docker_lint.py"
        assert set(raw) == {"policy", "version", "instrument", "hadolint_version",
                            "shellcheck_version", "measured_at", "rules"}
        assert all(isinstance(code, str) and count > 0 for code, count in raw["rules"].items())
