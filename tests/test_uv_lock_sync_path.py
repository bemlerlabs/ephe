"""Ephe — task #91: a changed dependency constraint gets a lock and a fence verdict in one command.

The shape this pins comes from PR #37: Dependabot rewrote the `ephemora-cell` bound in
pyproject.toml and cannot regenerate uv.lock, so every `pytest-linux` leg died inside
`Verify uv.lock is fresh (supply-chain guard)` (`uv lock --check`, `.github/workflows/tests.yml:101`)
and never reached pytest — including the test whose own text says `1.0.5, measured by nobody,
falls through the bound`. The guard decided the PR before the fence could.

No test here reaches the network and no test here writes the repo's lock: the mechanism is
driven through its offline steps, and the plan it prints is checked as text.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.toml_compat import tomllib

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "uv_lock_sync.sh"
PACKAGE = "ephemora-cell"
LOCK_HEAD = 'name = "ephemora-cell"\nversion = "{version}"\nsource = {{ registry = "https://pypi.org/simple" }}\nwheels = [\n    {{ filename = "x.whl", hash = "sha256:{sha}" }},\n]\n'


REGISTER = REPO / ".github" / "cell-runtime-fence.json"


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _releases() -> dict[str, dict]:
    return json.loads(REGISTER.read_text(encoding="utf-8"))["packages"][PACKAGE]["releases"]


def _admitted(upper: str) -> list[str]:
    return sorted(v for v in _releases() if _key(v) < _key(upper))


def _unmeasured(upper: str) -> list[str]:
    return [v for v in _admitted(upper) if not _releases()[v].get("policy_measured")]


def _bound_line(src: str, spec: str) -> str:
    """The requirement string as pyproject writes it, so a test rewrite matches exactly once."""
    return f'"{PACKAGE}{spec}"'


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd or REPO)


def lock_text(pairs: list[tuple[str, str, str]], deps: dict[str, list[str]] | None = None) -> str:
    """A uv.lock stand-in: [[package]] blocks of (name, version, wheel sha), with optional
    `dependencies = [...]` lines for `deps`."""
    blocks = ['[[package]]\nname = "ephe"\nversion = "0.0.1"\n']
    for name, version, sha in pairs:
        listed = "".join(
            "dependencies = [\n" + "".join(f'    {{ name = "{d}", version = "1" }},\n' for d in inners) + "]\n"
            for d, inners in [(name, (deps or {}).get(name, []))]
            if inners
        )
        if name == "ephemora-cell":
            blocks.append("[[package]]\n" + listed + LOCK_HEAD.format(version=version, sha=sha))
        else:
            blocks.append(f'[[package]]\nname = "{name}"\nversion = "{version}"\n{listed}')
    return "\n".join(blocks)


@pytest.fixture(scope="module")
def hashes() -> dict[str, str]:
    return {
        "pyproject": hashlib.sha256((REPO / "pyproject.toml").read_bytes()).hexdigest(),
        "lock": hashlib.sha256((REPO / "uv.lock").read_bytes()).hexdigest(),
    }


def test_the_plan_uses_the_pinned_uv_for_exactly_one_package(tmp_path):
    """GIVEN a maintainer who changed a bound and wants the lock without drift
    WHEN the mechanism is asked for its plan
    THEN it names the uv version CI pins, the `--upgrade-package` form for the one package, and a
    scratch tree — never a bare `uv lock`, which is how an unrelated resolution rides along."""
    out = run("--package", PACKAGE, "--scratch", str(tmp_path), "--dry-run")
    assert out.returncode == 0, out.stdout + out.stderr
    plan = out.stdout
    pin = None
    for line in (REPO / ".github" / "workflows" / "tests.yml").read_text().splitlines():
        if 'install "uv==' in line:
            pin = line.split("uv==")[1].split('"')[0]
            break
    assert pin, "the pinned uv version disappeared from the workflow this script must agree with"
    assert f"uv=={pin}" in plan
    assert f"--upgrade-package {PACKAGE}" in plan
    assert str(tmp_path) in plan
    resolve = [ln for ln in plan.splitlines() if re.search(r"\buv lock\b", ln)]
    assert resolve, "the plan must show the resolve step"
    assert all(f"--upgrade-package {PACKAGE}" in ln for ln in resolve)


def test_the_plan_lands_the_lock_with_the_constraint_in_one_commit(tmp_path):
    """GIVEN majors are landed by a human reading the diff (the repo's cadence rule)
    WHEN the plan is printed
    THEN it hands that human a path-limited commit naming both files, so the constraint and the
    lock can never land apart — the exact state that made PR #37 unmergeable."""
    out = run("--package", PACKAGE, "--scratch", str(tmp_path), "--dry-run")
    assert "git commit -- pyproject.toml uv.lock" in out.stdout
    assert "git add -A" not in out.stdout


def test_the_drift_guard_rejects_a_second_package_moving(tmp_path):
    """GIVEN a generated lock in which the target moved and an unrelated package moved too
    WHEN the mechanism compares it against the repo lock
    THEN it exits non-zero and names the intruder, because a constraint change that carries a
    second package is an unannounced dependency change."""
    repo = tmp_path / "repo.lock"
    new = tmp_path / "new.lock"
    repo.write_text(lock_text([(PACKAGE, "1.0.4.3", "a" * 64), ("httpx", "0.27.0", "b" * 64)]))
    new.write_text(lock_text([(PACKAGE, "1.0.5", "c" * 64), ("httpx", "0.28.1", "d" * 64)]))
    out = run("--package", PACKAGE, "--diff", "--repo-lock", str(repo), "--new-lock", str(new))
    assert out.returncode == 1, out.stdout
    assert "httpx" in out.stdout

    clean = tmp_path / "clean.lock"
    clean.write_text(lock_text([(PACKAGE, "1.0.5", "c" * 64), ("httpx", "0.27.0", "b" * 64)]))
    ok = run("--package", PACKAGE, "--diff", "--repo-lock", str(repo), "--new-lock", str(clean))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert PACKAGE in ok.stdout


def test_the_verdict_names_the_unmeasured_rung_the_new_bound_admits(tmp_path):
    """GIVEN the bound PR #37 proposed, widened so the unmeasured rungs fall inside
    WHEN the fence is asked what that bound admits
    THEN the verdict is FAIL and it says which release nobody measured, quoting the register —
    this is the decision the supply-chain guard stole from the test that carries it."""
    unmeasured = _unmeasured("1.1.1")
    if not unmeasured:
        pytest.skip("every release under <1.1.1 now carries a measurement — this pin's premise "
                    "was retired by a register edit, so the rung it names is gone")
    project = tmp_path / "pyproject.toml"
    src = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    project.write_text(src.replace(_bound_line(src, ">=1.0.4.3,<1.0.5"), _bound_line(src, ">=1.0.4.3,<1.1.1")))
    assert _bound_line(src, ">=1.0.4.3,<1.1.1") in project.read_text(encoding="utf-8"), \
        "the requirement string did not match, so the bound under test would be the repo's own"
    out = run("--package", PACKAGE, "--verdict", "--pyproject", str(project),
              "--lock", str(REPO / "uv.lock"))
    assert "verdict: FAIL" in out.stdout, out.stdout + out.stderr
    for version in unmeasured:
        assert f"{PACKAGE} {version}" in out.stdout, f"the verdict did not name {version}: {out.stdout}"
    assert out.returncode == 1


def test_the_verdict_passes_the_bound_that_is_in_the_tree(tmp_path):
    """GIVEN the constraint as it stands in the repo
    WHEN the same verdict is computed
    THEN it passes, so a red verdict is about the proposed bound and not about the instrument."""
    out = run("--package", PACKAGE, "--verdict", "--pyproject", str(REPO / "pyproject.toml"),
              "--lock", str(REPO / "uv.lock"))
    assert "verdict: PASS" in out.stdout, out.stdout + out.stderr


def test_the_verdict_rejects_a_wheel_that_is_not_the_one_the_register_read(tmp_path):
    """GIVEN a lock that resolves a registered release from different bytes
    WHEN the verdict is computed
    THEN it fails on the hash: a licence or policy claim attached to another wheel proves nothing."""
    registered = [v for v in _admitted("1.1.1") if _releases()[v].get("wheel_sha256")]
    assert registered, "the register names no release with a wheel hash, so the fence has no bytes"
    version = registered[0]
    register_sha = _releases()[version]["wheel_sha256"]
    project = tmp_path / "pyproject.toml"
    src = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    project.write_text(src.replace(_bound_line(src, ">=1.0.4.3,<1.0.5"), _bound_line(src, ">=1.0.4.3,<1.1.1")))
    assert _bound_line(src, ">=1.0.4.3,<1.1.1") in project.read_text(encoding="utf-8"), \
        "the requirement string did not match, so the bound under test would be the repo's own"
    lock = tmp_path / "uv.lock"
    lock.write_text(lock_text([(PACKAGE, version, "e" * 64)]))
    out = run("--package", PACKAGE, "--verdict", "--pyproject", str(project), "--lock", str(lock))
    assert "verdict: FAIL" in out.stdout, out.stdout + out.stderr
    mismatch = [ln for ln in out.stdout.splitlines()
                if ln.startswith("reason:") and "while the register read" in ln]
    assert mismatch, f"no reason line about the wheel mismatch:\n{out.stdout}"
    assert register_sha[:12] in mismatch[0]


def test_the_mechanism_writes_nothing_in_the_repo(tmp_path, hashes):
    """GIVEN the repository pair this task is forbidden to edit
    WHEN the plan and a verdict have been produced
    THEN pyproject.toml and uv.lock are byte-identical to before, and every path the mechanism
    touches sits under the scratch directory it was given."""
    run("--package", PACKAGE, "--scratch", str(tmp_path), "--dry-run")
    run("--package", PACKAGE, "--verdict", "--pyproject", str(REPO / "pyproject.toml"),
        "--lock", str(REPO / "uv.lock"))
    assert hashlib.sha256((REPO / "pyproject.toml").read_bytes()).hexdigest() == hashes["pyproject"]
    assert hashlib.sha256((REPO / "uv.lock").read_bytes()).hexdigest() == hashes["lock"]

def test_the_drift_guard_allows_a_move_the_cone_explains(tmp_path):
    """GIVEN the target moved and, with it, a package only it depends on
    WHEN the lock is compared
    THEN the pair is accepted as one consequence, while the same run still names the cone it read.
    An unrelated mover is rejected by the test above, so both halves of the rule are pinned."""
    repo = tmp_path / "repo.lock"
    new = tmp_path / "new.lock"
    repo.write_text(lock_text([(PACKAGE, "1.0.4.3", "a" * 64), ("wasmtime", "43.0.1", "b" * 64)],
                             deps={PACKAGE: ["wasmtime"]}))
    new.write_text(lock_text([(PACKAGE, "1.0.5", "c" * 64), ("wasmtime", "44.0.0", "d" * 64)],
                            deps={PACKAGE: ["wasmtime"]}))
    out = run("--package", PACKAGE, "--diff", "--repo-lock", str(repo), "--new-lock", str(new))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "inside the cone" in out.stdout

def test_the_scratch_rewrite_stays_valid_toml(tmp_path):
    """GIVEN a bound the caller wants to ask about without editing the repository
    WHEN the mechanism prepares its scratch tree
    THEN the rewritten pyproject.toml still parses, carries exactly the asked bound, and the
    repo pair is untouched. Measured on the first run of this path: the rewrite swallowed the
    closing quote of the requirement string and uv answered `invalid basic string` — a bug the
    plan-only tests could not see. The reader is the repo's compat helper: `tomllib` is 3.11+ and
    this matrix runs 3.10, which is where the first version of this test failed."""

    out = run("--package", PACKAGE, "--bound", "1.0.4.3,<1.1.1", "--scratch", str(tmp_path), "--prepare")
    assert out.returncode == 0, out.stdout + out.stderr
    project = tmp_path / "project" / "pyproject.toml"
    raw = tomllib.loads(project.read_text(encoding="utf-8"))
    specs = [r for r in raw["project"]["optional-dependencies"]["sandbox"] if PACKAGE in r]
    assert specs == [f"{PACKAGE}>=1.0.4.3,<1.1.1"], specs
    assert "rewrote 1 bound" in out.stdout

def test_a_forked_lock_is_compared_as_the_blocks_it_carries(tmp_path):
    """GIVEN a lock where the target resolves to two versions in two blocks (a forked resolution,
    which this lock really has for six names, `numpy` among them)
    WHEN the mechanism compares or judges it
    THEN neither reading collapses to one block: the diff sees both versions and the verdict
    reports the fork and fences each rung, because a first-wins reader would let an unmeasured
    fork through unnoticed."""
    fork = "\n".join([
        '[[package]]', 'name = "ephemora-cell"', 'version = "1.0.4.3"',
        'source = { registry = "https://pypi.org/simple" }', 'wheels = [',
        '    { url = "https://pypi.org/x/ephemora_cell-1.0.4.3-py3-none-any.whl", hash = "sha256:'
        + "5" * 64 + '" },', ']',
        '[[package]]', 'name = "ephemora-cell"', 'version = "1.0.5"',
        'source = { registry = "https://pypi.org/simple" }', 'wheels = [',
        '    { url = "https://pypi.org/x/ephemora_cell-1.0.5-py3-none-any.whl", hash = "sha256:'
        + "6" * 64 + '" },', ']',
    ])
    single = lock_text([(PACKAGE, "1.0.4.3", "5" * 64)])
    repo, new = tmp_path / "repo.lock", tmp_path / "fork.lock"
    repo.write_text(single)
    new.write_text(fork)
    diff = run("--package", PACKAGE, "--diff", "--repo-lock", str(repo), "--new-lock", str(new))
    assert "1.0.4.3/1.0.5" in diff.stdout, diff.stdout

    project = tmp_path / "pyproject.toml"
    src = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    project.write_text(src.replace(f"{PACKAGE}>=1.0.4.3,<1.0.5", f"{PACKAGE}>=1.0.4.3,<1.0.6"))
    verdict = run("--package", PACKAGE, "--verdict", "--pyproject", str(project), "--lock", str(new))
    assert "lock forks: 1.0.4.3, 1.0.5" in verdict.stdout, verdict.stdout
    assert verdict.stdout.count("lock resolves:") == 2
    assert "verdict: FAIL" in verdict.stdout
