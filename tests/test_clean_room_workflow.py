"""Offline contract check for `.github/workflows/clean-room.yml` and its script.

The leg this guards answers one question: can the two lockfiles be installed cold, on a machine
that has nothing pre-installed. Two ways to lose that answer without noticing are structural, so
both are asserted from the files rather than run: the leg quietly pointing its install at a
directory that outlives the job, and the leg quietly stopping covering one of the halves or one of
the interpreters that `tests.yml` actually tests. Action pins and permission scopes are checked
here in the same style as `tests/test_ci_action_pins.py`, because a supply-chain leg that can write
to the repository is its own incident.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "clean-room.yml"
SCRIPT = ROOT / "scripts" / "clean_room_install.sh"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

USES = re.compile(r"uses:\s*([^\s@]+)@(\S+)")
SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION_LIST = re.compile(r"python-version:\s*\[([^\]]+)\]")


def _body() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _versions(path: Path) -> set[str]:
    match = VERSION_LIST.search(path.read_text(encoding="utf-8"))
    assert match, f"no literal python-version list in {path.name}"
    return {v.strip().strip("'\"") for v in match.group(1).split(",")}


def test_the_workflow_and_its_script_exist():
    """GIVEN the lane THEN both halves are in the tree: the leg and the instrument it runs. A
    workflow pointing at a deleted script is green for exactly as long as nobody dispatches it.
    """
    assert WORKFLOW.is_file(), "the clean-room workflow is missing"
    assert SCRIPT.is_file(), "scripts/clean_room_install.sh is missing"
    assert SCRIPT.stat().st_mode & 0o111 or SCRIPT.read_text().startswith("#!/usr/bin/env bash"), \
        "the script is neither executable nor shebanged"


def test_the_leg_installs_into_a_directory_the_job_loses():
    """GIVEN the leg THEN its install root is declared from `runner.temp` and nowhere else. This is
    the assertion that reddens when the venv step is deleted: an unset root makes the script refuse,
    and a root taken from `github.workspace` or a literal path puts the result where the next job
    can read it as satisfied, which is the `9910615d` incident this lane exists to stop.
    """
    body = _body()
    roots = re.findall(r"EPHE_CLEAN_ROOM_ROOT:\s*(.+?)\s*$", body, re.M)
    assert roots, "EPHE_CLEAN_ROOM_ROOT is no longer declared: the leg has no install root"
    for root in roots:
        assert "runner.temp" in root, f"install root {root} is not the runner's temporary directory"
    for leaked in ("github.workspace", ".venv", "RUNNER_TOOL_CACHE"):
        assert not any(leaked in r for r in roots), f"install root {roots} points into {leaked}"


def test_every_action_is_pinned_to_a_commit():
    """GIVEN every `uses:` line THEN it names a 40-hex commit. A tag can be repointed by whoever owns
    that repository, and this leg installs code from the lockfile it is checking.
    """
    pins = USES.findall(_body())
    assert pins, "the workflow uses no action at all, which is not what this file does"
    unpinned = [ref for ref, sha in pins if not SHA.match(sha)]
    assert not unpinned, f"actions pinned to a moving ref: {unpinned}"


def test_the_leg_does_not_provision_the_shared_interpreter_cache():
    """GIVEN the guarantee that nothing lands in `_tool` THEN this file must not call the actions that
    write it. `actions/setup-python` and `actions/setup-node` install into the runner's tool cache by
    design, so their absence here is what makes the guarantee structural instead of hoped for; the
    script fetches its own CPython under the scratch root.
    """
    # Checked against the pins rather than the prose: this file names the two actions in its header to
    # explain why it does not call them, and a substring test would read that explanation as a step.
    used = {repo for repo, _ in USES.findall(_body())}
    for action in ("actions/setup-python", "actions/setup-node"):
        assert action not in used, f"{action} writes the shared tool cache this leg must not touch"


def test_the_workflow_asks_for_read_only_scope_and_no_credentials():
    """GIVEN a leg whose inputs are two lockfiles THEN `permissions: contents: read` at the top, no
    write scope anywhere, and `persist-credentials: false` on every checkout. An audit that could push
    is a supply chain of its own.
    """
    body = _body()
    assert re.search(r"^permissions:\s*contents:\s*read\s*$", body, re.M), \
        "workflow-level permissions must be exactly contents: read"
    assert not re.search(r"contents:\s*write|pull-requests:\s*write|deployments:\s*write", body), \
        "the clean-room leg must hold no write scope"
    assert body.count("actions/checkout@") == body.count("persist-credentials: false"), \
        "a checkout keeps its token"


def test_the_triggers_are_the_two_that_need_them():
    """GIVEN hosted minutes cost the account something THEN `push` and a cron are not free here. A
    lockfile that did not change gives the same answer it gave yesterday, so the leg runs on a pull
    request and on a dispatch, and on nothing else.
    """
    body = _body()
    on_block = body.split("on:", 1)[1].split("\npermissions:", 1)[0]
    triggers = {line.strip().rstrip(":").split(":")[0].strip()
                for line in on_block.splitlines() if re.match(r"^  \w", line)}
    assert triggers == {"pull_request", "workflow_dispatch"}, f"unexpected triggers: {sorted(triggers)}"
    assert not re.search(r"^\s*(schedule|cron):", body, re.M), "a scheduled leg spends hosted minutes on nothing"


def test_the_matrix_covers_the_interpreters_ci_tests():
    """GIVEN this leg claims a lock installs cold THEN the versions it proves must be the versions the
    test matrix runs. Comparing the two literal lists catches a leg that dropped an interpreter, which
    would otherwise read as a pass over a narrower question than the one `tests.yml` asks.
    """
    here = _versions(WORKFLOW)
    there = _versions(TESTS_WORKFLOW)
    assert here == there, f"clean-room covers {sorted(here)} while tests.yml runs {sorted(there)}"


def test_both_lockfiles_are_installed_by_the_leg():
    """GIVEN the lane asks for the Python and the JS half THEN the leg declares both targets. A leg
    that quietly narrowed to `py` would still print a verdict and still leave `app/pnpm-lock.yaml`
    unproven, and the printed skip line is the only trace.
    """
    targets = re.findall(r"EPHE_CLEAN_ROOM_TARGETS:\s*(\S+)", _body())
    assert targets, "EPHE_CLEAN_ROOM_TARGETS is no longer declared"
    for value in targets:
        assert {"py", "js"} <= set(value.split(",")), f"the leg installs only {value}"


def test_the_script_carries_the_guards_the_workflow_relies_on():
    """GIVEN the workflow delegates THEN the refusal has to live in the script, because that is the
    place a future step edit can route around. Three specific strings are the contract: the tool cache
    named in a refusal, the resolver pin that matches `tests.yml`, and the verdict line every branch
    prints before it exits.
    """
    script = SCRIPT.read_text(encoding="utf-8")
    assert "RUNNER_TOOL_CACHE" in script, "the script no longer refuses a tool-cache install root"
    assert "VERDICT fail" in script and "VERDICT pass" in script, "the script no longer prints a verdict"
    pinned = re.search(r'EPHE_UV_VERSION:-([0-9.]+)\}', script)
    assert pinned, "the resolver is no longer pinned in the script"
    tests_body = TESTS_WORKFLOW.read_text(encoding="utf-8")
    ci_pin = re.search(r'"uv==([0-9.]+)"', tests_body)
    assert ci_pin, "tests.yml no longer names a uv version to compare against"
    assert pinned.group(1) == ci_pin.group(1), \
        f"the clean-room leg resolves with uv {pinned.group(1)} while tests.yml locks with {ci_pin.group(1)}"


def test_the_script_provisions_a_pinned_node_inside_the_scratch_root():
    """GIVEN the leg must not use `actions/setup-node` THEN it fetches its own Node into
    the directory the runner wipes. A host `pnpm` is not enough: the ubuntu image that
    ran 39388942734 had no corepack, so the JS half reported `pnpm none` on all four
    Python legs. The download is version- and digest-pinned per platform, and corepack's
    home and shims live under the same scratch root so no cache survives the job.
    """
    script = SCRIPT.read_text(encoding="utf-8")
    version = re.search(r'EPHE_NODE_VERSION:-([0-9.]+)\}', script)
    assert version, "the clean-room Node version is not pinned in the script"
    assert "nodejs.org/dist" in script, "the script does not fetch Node from the official dist"
    assert "sha256" in script.lower(), "the Node download is not checksum-verified"
    for platform in ("linux-x64", "linux-arm64", "darwin-x64", "darwin-arm64"):
        assert platform in script, f"the Node provisioner does not name {platform}"
    assert 'NODE_DIR="$WORK/node"' in script, "Node does not land in the scratch root"
    assert 'COREPACK_HOME="$WORK/corepack"' in script, (
        "corepack's download home is not inside the scratch root"
    )
    assert "corepack prepare" in script, "the pinned pnpm is not activated from app/package.json"
    assert "--store-dir" in script, "the pnpm store is not confined to the scratch root"
