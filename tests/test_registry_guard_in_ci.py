"""The registry guard ran where a human remembered it, not where a machine enforces it.

`scripts/registry_guard.py` is the answer to the npm wrapper that handed a release tag's remote
scripts to `bash` and to `iex`: it scanned the shipped files, but it ran only in the pre-commit
hook, through `scripts/ci_local.sh`. A clone with no hooks installed reached the trunk with a
piped shape intact, and CI never looked. `.github/AGENTS.md` names the rule this file holds:
a gate that runs locally alone has to run in `ci-gates.yml` too, with the reason beside it.

A workflow is a claim written in YAML, and YAML is not importable - the same reason
`tests/test_pre_commit_hook_is_installed.py` reads the hook body and `tests/test_macos_usage_strings.py`
reads an Info.plist. The mutation case below removes the step in memory and demands the search
come back empty: a checker that rejects nothing counts as never built.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci-gates.yml"
GUARD_COMMAND = "python3 scripts/registry_guard.py"


def _steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["repo-gates"]["steps"]


def _guard_steps(steps: list[dict]) -> list[dict]:
    return [
        step
        for step in steps
        if isinstance(step.get("run"), str) and "registry_guard.py" in step["run"]
    ]


def test_the_repository_gates_run_the_registry_guard_as_their_own_step():
    found = _guard_steps(_steps())
    assert found, "repo-gates no longer runs scripts/registry_guard.py; the npm-incident rule is local-only again"
    assert GUARD_COMMAND in found[0]["run"].strip(), (
        f"the step must call the gate exactly as the hook calls it, got: {found[0]['run']!r}"
    )


def test_the_step_hands_the_verdict_to_the_run():
    """A guard whose exit code cannot fail the job only produces log lines."""
    step = _guard_steps(_steps())[0]
    assert step.get("continue-on-error") is not True, "the step was muted; a finding would stay green"
    assert not re.search(r"\|\|\s*(?:true|:)", step["run"]), "an || true swallows the guard's exit code"


def test_the_ci_call_is_the_hook_call_line_for_line():
    # GIVEN the promise that this step is the CI copy of the hook's own gate
    ci_call = _guard_steps(_steps())[0]["run"].strip()
    assert ci_call == GUARD_COMMAND, f"the step drifted from the plain call: {ci_call!r}"
    # WHEN the hook-side call is read from the script the pre-commit hook runs
    hook_body = (ROOT / "scripts" / "ci_local.sh").read_text(encoding="utf-8")
    # THEN both call the same command with the same (empty) flag set, so one verdict covers both
    assert f"\n{GUARD_COMMAND}\n" in f"\n{hook_body}\n", (
        "ci_local.sh no longer calls the guard exactly as this step does; the two now scan different sets"
    )


def test_the_step_carries_the_reason_the_area_file_demands():
    """.github/AGENTS.md admits a new gate step only with the reason it exists written beside it."""
    body = WORKFLOW.read_text(encoding="utf-8")
    block = body[body.index("- name:") :]
    starts = [m.start() for m in re.finditer(r"^      - name: ", block, re.MULTILINE)]
    for start in starts:
        end = next((s for s in starts if s > start), len(block))
        step_block = block[start:end]
        if "registry_guard.py" in step_block:
            comment_lines = [
                line for line in step_block.splitlines() if line.strip().startswith("#")
            ]
            assert len(comment_lines) >= 2, "the guard step lost its reason comment"
            assert any("workflow" in line.lower() or "hook" in line.lower() for line in comment_lines), (
                "the comment no longer says why this copy exists next to the hook"
            )
            return
    raise AssertionError("no registry_guard step block found in ci-gates.yml")


def test_removing_the_step_is_seen_by_this_file():
    """The mutation the report has to name: cut the step, and the search must come back empty."""
    steps = _steps()
    guard = _guard_steps(steps)
    assert len(guard) == 1, f"repo-gates must hold exactly one guard step, found {len(guard)}"
    mutated = [step for step in steps if step is not guard[0]]
    assert _guard_steps(mutated) == [], "the search matches something that is not the step"
    assert len(mutated) == len(steps) - 1, "the mutation removed nothing; the search is vacuous"
