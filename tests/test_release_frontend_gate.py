"""The release bar covers both product surfaces, and a dispatch can test it without a tag.

Tag-push run `39394037022` built and published `v0.1.1` while the test gate ran only
pytest and pass^3. The frontend was red in two other workflows on the same commit
(`ModelPicker`'s wall-clock assertion at 553.7 and 811.2 ms), and the release gate
could not see it: the bundles shipped against a tree whose unit tests never ran on the
path that produces them. This contract holds the gate to the same four frontend checks
`frontend-build.yml` runs, makes `build-bundles` wait for them, and adds a
`workflow_dispatch` dry run so the gate can be exercised before the next tag exists.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
FRONTEND_BUILD = ROOT / ".github" / "workflows" / "frontend-build.yml"


def _doc(path: Path = RELEASE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _triggers(document: dict) -> dict:
    # PyYAML reads the bare `on:` key as the boolean True under YAML 1.1.
    return document.get("on") or document.get(True) or {}


def _jobs(document: dict) -> dict:
    return document.get("jobs") or {}


def _steps(job: dict) -> list[dict]:
    return [step for step in (job.get("steps") or []) if isinstance(step, dict)]


def _runs(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(job))


def _uses(job: dict) -> list[str]:
    return [str(step.get("uses", "")) for step in _steps(job)]


def _needs(job: dict) -> list[str]:
    needs = job.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def test_a_dispatch_runs_the_gates_and_skips_the_bundles():
    """GIVEN the dry-run trigger THEN both gates run and `build-bundles` does not.

    A gate that can only be reached by pushing a tag is tested for the first time on
    the release itself, which is what happened to the frontend: an unresolvable action
    pin once sat in this file because no run had ever reached the job. The dispatch
    exercises the gates; the bundle job stays on the tag push so a dry run never
    creates a draft.
    """
    document = _doc()
    triggers = _triggers(document)
    assert "workflow_dispatch" in triggers, "release.yml has no workflow_dispatch dry run"
    build = _jobs(document)["build-bundles"]
    assert build.get("if") == "github.event_name == 'push'", (
        "build-bundles must run on a tag push only; a dispatch is the gate's dry run"
    )
    for gate in ("test-gate", "frontend-gate"):
        condition = str(_jobs(document)[gate].get("if", ""))
        assert "github.event_name == 'push'" in condition, f"{gate} no longer runs on a tag push"
        assert "workflow_dispatch" in condition, f"{gate} does not run on the dry-run dispatch"


def test_the_bundles_wait_for_the_frontend_gate():
    """GIVEN bundles produced from `app/` THEN the frontend has to be green first.

    `needs: test-gate` alone is the Python-only bar that passed while vitest failed. The
    bundle job must name both gates, or removing the edge silently restores the hole.
    """
    jobs = _jobs(_doc())
    assert "frontend-gate" in jobs, "release.yml has no frontend-gate job"
    assert "frontend-gate" in _needs(jobs["build-bundles"]), (
        "build-bundles does not need frontend-gate; a red frontend would not stop a release"
    )
    assert "test-gate" in _needs(jobs["build-bundles"]), "the Python gate lost its dependency edge"


def test_the_frontend_gate_runs_the_same_checks_as_the_frontend_build():
    """GIVEN the checks that failed on `v0.1.1` THEN the release gate runs all four.

    Type check, unit tests, lint and the frozen install are the four steps
    `frontend-build.yml` runs on every push. Naming them here, rather than trusting a
    future edit to copy them, is what makes the release bar a statement about the
    frontend surface instead of a copy of the Python suite.
    """
    job = _jobs(_doc()).get("frontend-gate")
    assert job is not None, "release.yml has no frontend-gate job"
    runs = _runs(job)
    assert "pnpm install --frozen-lockfile" in runs, "the gate installs outside the lockfile"
    assert "pnpm exec tsc --noEmit" in runs, "the gate does not type-check the frontend"
    assert "pnpm exec vitest run" in runs, "the gate does not run the frontend unit suite"
    assert "pnpm run lint" in runs, "the gate does not lint the frontend"
    assert "corepack enable" in runs and "corepack prepare" in runs, (
        "the gate does not activate the pnpm pinned in app/package.json"
    )
    assert "packageManager" in runs, "the corepack pin is not read from app/package.json"

    setup = [step for step in _steps(job) if "setup-node" in str(step.get("uses", ""))]
    assert setup, "the gate has no actions/setup-node step"
    with_block = setup[0].get("with") or {}
    assert str(with_block.get("node-version")) == "22.23.4", "the gate is not on Node 22.23.4"
    assert with_block.get("package-manager-cache") is False, (
        "a release gate must not restore a package-manager cache (cache poisoning)"
    )


def test_the_python_gate_keeps_its_own_checks():
    """GIVEN the release bar THEN adding the frontend did not replace the Python half."""
    runs = _runs(_jobs(_doc())["test-gate"])
    assert "python -m pytest tests/ -q" in runs
    assert "evals/pass3_release_gate.py" in runs


def test_the_frontend_gate_never_touches_the_signing_environment():
    """GIVEN the signing key lives on the `release` environment THEN only the bundle job
    declares it. The frontend gate runs third-party JavaScript from the lockfile; handing
    it the environment would put the key one workflow edit away from a test step.
    """
    job = _jobs(_doc())["frontend-gate"]
    assert "environment" not in job, "the frontend gate must not enter the release environment"
    assert "permissions" not in job, "the frontend gate needs no write scope of its own"


def test_the_reference_workflow_still_carries_the_steps_the_gate_copies():
    """GIVEN this contract names four checks THEN the source of those checks still exists.

    If `frontend-build.yml` drops one, the release gate would keep asserting a check the
    frontend surface no longer runs. The comparison is textual and offline on purpose.
    """
    runs = _runs(_jobs(_doc(FRONTEND_BUILD))["build"])
    for command in ("pnpm exec tsc --noEmit", "pnpm exec vitest run", "pnpm run lint"):
        assert command in runs, f"frontend-build.yml no longer runs `{command}`"
