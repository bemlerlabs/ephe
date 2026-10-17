"""Only one workflow may own the `release` environment, and it is not release.yml's badge.

Measured on 2026-10-09 with `gh api repos/bemlerlabs/ephe/environments/release` and
`gh secret list`: both signing secrets (`TAURI_SIGNING_PRIVATE_KEY`,
`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`) live in the `release` environment, the repository scope
holds neither (its secret list is empty), and `release.yml:68` is the only job that declares
`environment: release`. What is NOT set is the protection rule the environment was supposed
to carry — `reviewers: 0`, `wait_timer: None`, `can_admins_bypass: true` — because GitHub
refuses required reviewers on this plan with a 422. The owner confirmed that; it is the
boundary written up in docs/CI_CAPACITY_RUNNER_DECISION_2026-10-09.md.

That leaves one barrier, and it is a convention: an environment is not a perimeter, it is an
address. Any workflow in this repository that adds `environment: release` to one of its jobs
is handed both signing secrets by GitHub, with no approval step in between — the same reach
`release.yml` itself has. So the rule "exactly one workflow may hold that address" has to be
machine-checked, or it is a sentence in a document and nothing more.

Offline and filesystem-only, the same way tests/test_ci_action_pins.py works: the assertion is
about what the tree declares, and a network check would make the hygiene suite depend on
GitHub being reachable and on a token that can read environments.

What it also holds, because the same three lines of the tree are what make the address safe
today:
  - `release.yml:71` (`permissions: contents: write`) is the only write grant anywhere; every
    workflow's own block is `contents: read` — release.yml:26-27, ci-gates.yml:27-28,
    tests.yml:9-10, frontend-build.yml:10-11, bench-trend.yml:17-18, supply-chain.yml:50-51 —
    so no other workflow can be handed a writable `secrets.GITHUB_TOKEN`;
  - `release.yml` is the only file that references `secrets.` at all (4 references, measured
    2026-10-09; every other workflow has 0), so the signing key cannot be echoed into a log
    by a workflow nobody reviewed for it.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: The single environment this repository uses, and the only workflow allowed to name it.
ENVIRONMENT = "release"
ENVIRONMENT_OWNER = "release.yml"

#: Secrets that must never be reachable from outside the owning workflow.
SIGNING_SECRETS = ("TAURI_SIGNING_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY_PASSWORD")


def _workflows() -> dict[str, dict]:
    """Every workflow in the directory, parsed to a mapping keyed by file name."""
    out: dict[str, dict] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        out[path.name] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert out, f"no workflows found under {WORKFLOWS}"
    return out


def _environment_declarations() -> dict[str, list[str]]:
    """`environment:` per file, as a list of the names it declares.

    GitHub accepts both `environment: release` and the block form carrying `name:`/`url:`;
    reading only the inline form would let the block form slip past the fence.
    """
    found: dict[str, list[str]] = {}
    for name, doc in _workflows().items():
        names: list[str] = []
        for job in (doc.get("jobs") or {}).values():
            env = (job or {}).get("environment")
            if isinstance(env, dict):
                names.append(str(env.get("name")))
            elif env is not None:
                names.append(str(env))
        if names:
            found[name] = names
    return found


def test_one_workflow_and_only_one_holds_the_release_environment():
    """THEN exactly one file names an environment, it is release.yml, and the name it uses is
    `release`. GIVEN a second file that tries it, the message has to say which file, because
    the person adding the line is not the person who wrote this test.
    """
    declarations = _environment_declarations()
    owners = sorted(declarations)
    assert owners == [ENVIRONMENT_OWNER], (
        f"`environment:` must appear in exactly one workflow, {ENVIRONMENT_OWNER}. "
        f"Found in: {owners or 'nobody'}. Any workflow that declares the `release` "
        "environment is handed TAURI_SIGNING_PRIVATE_KEY and its _PASSWORD, and on this "
        "plan the environment enforces no reviewer approval (422 on required reviewers), "
        "so a second owner is an unreviewed path to the signing key."
    )


def test_the_one_environment_is_named_release_and_not_something_else():
    """GIVEN the owner THEN it declares the environment the secrets were moved into. A renamed
    or renamed-away environment would silently drop the protection the scope provides: the
    secrets are environment-scoped, so `environment: releases` grants nothing and a job that
    stops declaring `release` stops receiving them — both are breakage this must not hide.
    """
    declarations = _environment_declarations()
    assert declarations.get(ENVIRONMENT_OWNER) == [ENVIRONMENT], (
        f"{ENVIRONMENT_OWNER} must declare exactly one job on environment "
        f"`{ENVIRONMENT}`, found {declarations.get(ENVIRONMENT_OWNER)!r}"
    )


def test_the_signing_key_is_referenced_by_the_owner_alone():
    """GIVEN the signing secret names anywhere in the tree of workflows THEN only release.yml
    mentions them. An environment can only be entered by a job that declares it; a copy of the
    `secrets.TAURI_SIGNING_PRIVATE_KEY` string in another workflow is either dead code or the
    first half of a leak, and this test should be the thing that says which.
    """
    hits = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        referenced = [s for s in SIGNING_SECRETS if re.search(rf"\b{s}\b", text)]
        if referenced:
            hits[path.name] = referenced
    assert list(hits) == [ENVIRONMENT_OWNER], f"signing secrets referenced outside the owner: {hits}"
    assert set(hits[ENVIRONMENT_OWNER]) == set(SIGNING_SECRETS), (
        f"{ENVIRONMENT_OWNER} is expected to reference both signing secrets, found "
        f"{hits[ENVIRONMENT_OWNER]}"
    )


def test_no_workflow_outside_the_owner_reads_any_secret():
    """GIVEN `secrets.` appears only in the owning workflow THEN no other workflow can echo a
    secret into a log or hand it to a third-party action. This is broader than the two key
    names above and it costs nothing while the count is what it is today (measured: 4 in
    release.yml, 0 everywhere else), so a future `secrets.GITHUB_TOKEN` in a new workflow has
    to be a deliberate edit to this file's expectation rather than a quiet addition.
    """
    users = [p.name for p in sorted(WORKFLOWS.glob("*.yml"))
             if "secrets." in p.read_text(encoding="utf-8")]
    assert users == [ENVIRONMENT_OWNER], (
        f"workflows referencing `secrets.` outside {ENVIRONMENT_OWNER}: {users}. The "
        "release token is the one credential every workflow already holds; if a job needs "
        "it, say what for in the workflow and update this test with that reason."
    )


def test_the_only_write_scope_in_the_tree_is_the_publishing_job():
    """GIVEN every permissions block, workflow-level and job-level THEN the single write grant
    is `contents: write` in release.yml's publishing job (release.yml:70-71) and everything
    else reads. This is the half of the fence that stops a new workflow being handed a
    writable token with which to push a tag that then runs the release.
    """
    writes: list[str] = []
    for name, doc in _workflows().items():
        blocks = [("workflow", doc.get("permissions"))]
        blocks += [(f"job:{job_id}", job.get("permissions"))
                   for job_id, job in (doc.get("jobs") or {}).items()]
        for where, block in blocks:
            if not isinstance(block, dict):
                if block is not None and str(block) not in {"read-all", "contents: read"}:
                    writes.append(f"{name} {where} = {block!r}")
                continue
            for scope, level in block.items():
                if str(level).strip() == "write":
                    writes.append(f"{name} {where} {scope}: write")
    assert writes == [f"{ENVIRONMENT_OWNER} job:build-bundles contents: write"], (
        f"unexpected write grants: {writes}. Exactly one is allowed and it must stay in the "
        "job that creates the GitHub release; `can_admins_bypass: true` on the environment "
        "means a writable token is the other thing that could reach the signing path."
    )


def test_every_workflow_declares_its_own_permissions():
    """GIVEN each file THEN it sets workflow-level `permissions: contents: read`, rather than
    inheriting the account default. Without this, the rule above could pass simply because no
    block was written at all — and an inherited default is exactly what changes when somebody
    flips a repository setting.
    """
    missing = [name for name, doc in _workflows().items() if not isinstance(doc.get("permissions"), dict)]
    assert not missing, f"workflows without an explicit workflow-level permissions block: {missing}"


def test_the_fence_is_about_files_that_exist():
    """A guard against the whole module passing because a path moved: the owner must be in the
    directory it polices, and the reference test it borrows a convention from must be present.
    """
    assert (WORKFLOWS / ENVIRONMENT_OWNER).is_file(), f"{ENVIRONMENT_OWNER} is missing"
    assert (ROOT / "tests" / "test_ci_action_pins.py").is_file(), \
        "the offline-pin convention this test follows is gone"
