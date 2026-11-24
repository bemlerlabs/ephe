"""The publish page, SECURITY.md and the workflows tell the same story or none of them is trusted.

`docs/NPM_PUBLISHING.md` is the home of the publish path and SECURITY.md carries its short form;
both claim, in the present tense, that no workflow publishes to the registry today. That claim
lives in prose the product cannot import, so the only seam left is reading the files beside each
other - the same reason `tests/test_pre_commit_hook_is_installed.py` reads a hook body and
`tests/test_public_docs_policy.py` reads markdown. The workflow side is checked against the real
workflows, not against the documents: a page that promises what `release.yml` does not do is the
defect this tree already had once with the wrapper, and it is the class `scripts/citation_check.py`
cannot see because a wrong claim reads as well-written prose.

Given/When/Then, because each case is one promise a reader of the public page relies on.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "NPM_PUBLISHING.md"
SECURITY = ROOT / "SECURITY.md"
WORKFLOWS = ROOT / ".github" / "workflows"


#: The commands and credential shapes that would move a package to a registry. Comments are
#: skipped by the caller: every `registry.npmjs.org` mention today is a comment about the fetch
#: side (corepack, pnpm install), which is a download and legal; a publish is a command.
PUBLISH_CALL = re.compile(r"\b(?:npm|npx|pnpm|yarn)\s+publish\b|//registry\.npmjs\.org/:|_authToken")


def _publish_calls_in_workflows() -> list[str]:
    """Every workflow line that would move a package to a registry, in the whole workflows dir."""
    hits: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if PUBLISH_CALL.search(line):
                hits.append(f"{workflow.name}:{number}: {line.strip()}")
    return hits


class TestThePageStatesTheConditions:
    def test_the_page_names_the_registry_the_environment_and_the_credential_rule(self):
        # GIVEN the page that owns the publish path
        text = DOC.read_text(encoding="utf-8")
        # THEN a reader finds each condition the incident made necessary, in the page itself
        for promise in (
            "npm registry",
            "protected environment",
            "required reviewers",
            "does not exist today",
            "OIDC",
            "id-token",
            "Long-lived registry token",
        ):
            assert promise.lower() in text.lower(), f"the publish page no longer names {promise!r}"

    def test_the_page_holds_the_dry_run_contract_and_the_revocation_order(self):
        text = DOC.read_text(encoding="utf-8")
        assert "dry run" in text.lower(), "the dry-run contract lost its home"
        assert "revoke" in text.lower(), "the revocation order lost its home"


class TestThePagesAgreeWithTheWorkflows:
    def test_no_workflow_publishes_to_a_registry(self):
        # WHEN the documents both claim, in the present tense, that nothing publishes
        # THEN the workflows themselves say the same
        assert _publish_calls_in_workflows() == [], (
            "a workflow now publishes to a registry while the documents say nothing does; "
            "the pages must be rewritten in the same patch that adds the step"
        )

    def test_the_release_environment_the_page_binds_publishing_to_exists(self):
        # GIVEN the page's promise that a publish step runs in the release environment
        # THEN that environment is real in the workflow it is borrowed from
        release = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
        environments = {
            job.get("environment")
            for job in release["jobs"].values()
            if isinstance(job.get("environment"), str)
        }
        assert "release" in environments, "release.yml no longer declares the release environment"

    def test_no_workflow_mints_an_id_token_today(self):
        """The page promises no OIDC trust is requested anywhere until a publish step needs it."""
        mints: list[str] = []
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            parsed = yaml.safe_load(workflow.read_text(encoding="utf-8"))
            scopes: list[str] = []
            top = parsed.get("permissions")
            if isinstance(top, dict):
                scopes.extend(top)
            for job in parsed.get("jobs", {}).values():
                job_permissions = job.get("permissions")
                if isinstance(job_permissions, dict):
                    scopes.extend(job_permissions)
                for step in job.get("steps", []):
                    step_permissions = step.get("permissions")
                    if isinstance(step_permissions, dict):
                        scopes.extend(step_permissions)
            if "id-token" in scopes:
                mints.append(workflow.name)
        assert mints == [], f"{mints} request an id-token while no publish job exists to need one"


class TestTheShortFormPointsHome:
    def test_security_md_carries_the_publish_section_and_links_the_page(self):
        text = SECURITY.read_text(encoding="utf-8")
        assert "## Publishing to the package registry" in text, "the short form lost its section"
        assert "docs/NPM_PUBLISHING.md" in text, "the short form no longer points at the page that owns the detail"

    def test_the_short_form_says_the_package_is_not_published(self):
        # GIVEN a reader who only ever opens SECURITY.md
        # THEN they are not left believing a registry carries the package today
        text = SECURITY.read_text(encoding="utf-8")
        assert "not published at the time of writing" in text, "the honest present tense is gone from the short form"
        assert "no workflow in this repository" in text, "the short form no longer states that nothing publishes today"
