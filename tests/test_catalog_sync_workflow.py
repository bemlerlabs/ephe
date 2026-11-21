"""Offline contract check for `.github/workflows/catalog-sync.yml`.

The weekly sync is the only writer of the three committed Discover files, and a scheduled run has no
pull request to leave a comment on: when it fails, the failure is a red row in a table nobody opens.
That is not hypothetical. The runs of 2, 9 and 16 November each refreshed the mirror, force-pushed
`catalog/weekly-sync`, and then died at `gh pr create` with `GitHub Actions is not permitted to
create or approve pull requests` — a repository switch that the job's own `pull-requests: write`
scope cannot override. `marketplace/registry-snapshot.json` was 15 days old when this was measured,
and the nightly job named *freshness* passed every one of those nights, because it checks that packs
and plugins agree with their lock and never asks how old the mirror is.

Two ways to lose the warning again are structural, so both are read out of the file: the step
quietly reverting to a bare `gh pr create`, which leaves the operator with forty lines of log and no
name for the switch, and the age line disappearing, which is the only thing the run says every week
about a shelf that is served to users.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog-sync.yml"

SHELF_FILES = (
    "marketplace/registry-snapshot.json",
    "marketplace/registry-curated.json",
    "marketplace/search-intents.json",
)


def _job() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["sync"]


def _bodies() -> dict[str, str]:
    return {step["name"]: step["run"] for step in _job()["steps"] if "run" in step}


def names_the_refusal_switch(body: str) -> bool:
    """The step says which switch refused it and how to flip it, in text a person reads."""
    return (
        "not permitted to create or approve pull requests" in body
        and "can_approve_pull_request_reviews=true" in body
        and "GITHUB_STEP_SUMMARY" in body
    )


def ends_red_on_a_refusal(body: str) -> bool:
    """Naming the cause does not soften the verdict: the step still fails the run."""
    refusal_arm = body.split("then", 1)
    return len(refusal_arm) == 2 and "exit 1" in refusal_arm[1]


def states_the_shelf_age(body: str) -> bool:
    """Every run, changed or not, says how old each committed shelf file claims to be."""
    return (
        all(name in body for name in SHELF_FILES)
        and '"generated"' in body
        and "GITHUB_STEP_SUMMARY" in body
    )


def test_the_refused_run_names_the_switch_and_how_to_flip_it() -> None:
    body = _bodies()["Open or update the sync pull request"]
    assert names_the_refusal_switch(body), "the step must name the refusal and the setting behind it"


def test_a_refused_run_is_still_a_red_run() -> None:
    body = _bodies()["Open or update the sync pull request"]
    assert ends_red_on_a_refusal(body), "explaining the failure may not turn it into a warning"


def test_the_hint_points_at_a_switch_the_job_cannot_flip_itself() -> None:
    permissions = _job()["permissions"]
    assert permissions["contents"] == "write"
    assert permissions["pull-requests"] == "write"


def test_every_run_says_how_old_the_shelf_is() -> None:
    body = _bodies()["Compare with what is committed"]
    assert states_the_shelf_age(body), f"the age of {', '.join(SHELF_FILES)} must be stated weekly"


def test_the_three_readings_are_not_reading_nothing() -> None:
    bodies = _bodies()
    proposal = bodies["Open or update the sync pull request"]
    delta = bodies["Compare with what is committed"]
    assert not names_the_refusal_switch(proposal.replace("can_approve_pull_request_reviews=true", ""))
    assert not ends_red_on_a_refusal(proposal.replace("exit 1", "echo continuing"))
    assert not states_the_shelf_age(delta.replace(SHELF_FILES[0], "marketplace/elsewhere.json"))
    assert not states_the_shelf_age(delta.replace('"generated"', '"whatever"'))


def test_the_workflow_still_opens_nothing_beyond_its_own_branch() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"push --force origin \"\$branch\"", text), "the sync still may not write to main"
