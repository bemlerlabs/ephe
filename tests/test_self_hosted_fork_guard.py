"""Every self-hosted pull-request job carries the fork guard.

A fork PR that reaches a runner this project controls executes foreign code on
the machine that holds the repository credentials and the Mac keys. The guard
that keeps fork PRs off that runner is only as good as its presence on every
job that can be scheduled there.
"""
from __future__ import annotations

import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = (
    "github.event_name != 'pull_request' "
    "|| github.event.pull_request.head.repo.full_name == github.repository"
)
RUNNER_VARS = ("CI_LINUX_RUNNER", "CI_MAC_RUNNER", "SUPPLY_CHAIN_RUNNER")


def _on(document: dict) -> object:
    return document.get("on") if "on" in document else document.get(True)


def _self_hosted_jobs():
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        on = _on(document) or {}
        triggers = on if isinstance(on, (str, list, dict)) else {}
        if isinstance(triggers, str):
            triggers = {triggers: {}}
        if isinstance(triggers, list):
            triggers = {item: {} for item in triggers}
        if "pull_request" not in triggers:
            continue
        for name, job in (document.get("jobs") or {}).items():
            runs_on = str(job.get("runs-on") or "")
            if any(variable in runs_on for variable in RUNNER_VARS):
                yield path, name, job


def test_every_self_hosted_pull_request_job_has_the_guard():
    missing = []
    for path, name, job in _self_hosted_jobs():
        condition = str(job.get("if") or "")
        # Excluding every pull request is at least as strong as the fork guard.
        if "github.event_name != 'pull_request'" in condition:
            continue
        if GUARD not in condition:
            missing.append(f"{path.name}:{name}")
    assert not missing, (
        "self-hosted pull-request jobs without the fork guard: " + ", ".join(missing)
    )


def test_no_workflow_uses_pull_request_target():
    offenders = [
        path.name
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        if "pull_request_target" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
