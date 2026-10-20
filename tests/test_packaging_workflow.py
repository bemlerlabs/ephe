"""Packaging freshness judges a release that exists, never a tag still waiting for one.

Release run `39394034904` went red on the public main push that carried the `v0.1.1`
candidate: the manifests named 0.1.1, `releases/latest` still answered 0.1.0, and the
release was published minutes later. The check was right about the two numbers and
wrong about the moment. It now runs on `release: published` against that exact tag,
on the weekly schedule against the feed, and on a dispatch; a branch push no longer
asks a question whose answer is "not yet".
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "packaging.yml"


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}


def _triggers() -> dict:
    document = _doc()
    return document.get("on") or document.get(True) or {}


def _freshness() -> dict:
    return (_doc().get("jobs") or {})["freshness"]


def _runs() -> list[tuple[str, str, str]]:
    """(name, condition, command) for each step that runs the checker."""
    out = []
    for step in _freshness().get("steps") or []:
        run = str(step.get("run", ""))
        if "packaging_freshness.py" in run:
            out.append((str(step.get("name", "")), str(step.get("if", "")), run))
    return out


def test_a_branch_push_is_not_a_trigger():
    """GIVEN a main push that carries the next candidate THEN the release it names may
    not exist yet. Judging it against `releases/latest` at that moment is the race.
    """
    triggers = _triggers()
    assert "push" not in triggers, (
        "packaging.yml still runs on a push; a candidate commit can precede its release"
    )
    assert "release" in triggers, "packaging.yml does not run on release: published"
    release = triggers["release"] or {}
    assert release.get("types") == ["published"], (
        "the release trigger must be `published`, the event that makes the assets real"
    )
    assert "schedule" in triggers, "the weekly drift check is gone"
    assert "workflow_dispatch" in triggers, "the manual check is gone"


def test_the_published_event_judges_its_own_tag():
    """GIVEN the publish click THEN the reference is the tag that was published, not
    whatever `latest` happens to say. The two are different while a draft is open.
    """
    steps = _runs()
    assert steps, "the workflow no longer runs scripts/packaging_freshness.py"
    release_steps = [step for step in steps if "github.event_name == 'release'" in step[1]]
    assert len(release_steps) == 1, f"expected one release-event check, found {release_steps!r}"
    name, _condition, command = release_steps[0]
    assert "--release" in command, f"{name} does not pass an explicit release"
    assert "github.event.release.tag_name" in str(_freshness()), (
        "the release tag is not read from the published event payload"
    )
    assert "#v}" in command or "#v}" in str(_freshness()), (
        "the leading v is not stripped from the release tag"
    )


def test_the_scheduled_check_still_reads_the_feed():
    """GIVEN no release event THEN the weekly run asks the live feed, so a manifest
    that drifts after publication is still caught.
    """
    steps = [step for step in _runs() if "github.event_name == 'release'" not in step[1]]
    assert steps, "no step checks the feed on the schedule"
    commands = "\n".join(step[2] for step in steps)
    assert "python3 scripts/packaging_freshness.py" in commands
    assert "--release" not in commands, (
        "the scheduled step pins a version instead of reading the published release"
    )


def test_the_check_still_runs_on_a_pull_request():
    """GIVEN a manifest edit in a PR THEN the offline-compatible check still runs there;
    a packaging change should not wait for a schedule to be judged.
    """
    triggers = _triggers()
    assert "pull_request" in triggers, "the PR check is gone"
