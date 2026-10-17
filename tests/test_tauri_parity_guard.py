"""The Tauri plugin parity guard: two sides of one plugin, one version.

`npm run tauri build` cost an attempt on 2026-10-11 to an error that appeared before a single crate
compiled — the npm PR moved `@tauri-apps/plugin-*` and nothing moved `tauri-plugin-*` in
`Cargo.lock`. The guard in `scripts/tauri_parity.py` reads the same two files and decides the same
question in milliseconds, so it runs from `.husky/pre-commit` through `scripts/ci_local.sh` on the
commits that can create the drift, and from the hygiene leg on every push.

The subprocess discipline is the one the CI legs learned: `sys.executable`, a
`tests/subprocess_env.hermetic_env` base carrying the loader variables, and no host `EPHE_*` state.
A from-scratch child that cannot load its interpreter dies with code 127 on the self-hosted legs,
and a guard that dies reads as a pass to everything above it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "tauri_parity.py"

#: what the Tauri CLI printed at 04:51 on 2026-10-11, before compiling anything
CLI_LINES_2026_10_11 = [
    "tauri-plugin-notification (v2.4.0) : @tauri-apps/plugin-notification (v2.5.1)",
    "tauri-plugin-process (v2.3.1) : @tauri-apps/plugin-process (v2.4.0)",
    "tauri-plugin-updater (v2.12.0) : @tauri-apps/plugin-updater (v2.13.2)",
]

LOCK_TEMPLATE = """[[package]]
name = "tauri-plugin-{name}"
version = "{version}"
"""


def run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        check=False,
        env=hermetic_child_env(),
    )


def hermetic_child_env() -> dict[str, str]:
    from tests.subprocess_env import hermetic_env

    return hermetic_env(PATH=os.environ.get("PATH", ""))


def write_pair(tmp_path: Path, js: dict[str, str], rs: dict[str, str]) -> tuple[str, str]:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {f"@tauri-apps/plugin-{k}": v for k, v in js.items()}}),
        encoding="utf-8",
    )
    (tmp_path / "Cargo.lock").write_text(
        "".join(LOCK_TEMPLATE.format(name=k, version=v) for k, v in rs.items()), encoding="utf-8"
    )
    return str(tmp_path / "package.json"), str(tmp_path / "Cargo.lock")


def test_the_committed_pair_agrees():
    """The tree as landed: three shared plugins, all on the same major and minor."""
    result = run_guard()
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("notification 2.5.1", "process 2.4.0", "updater 2.13.2"):
        assert name in result.stdout
    assert "dialog" in result.stdout, "the rust-only plugins have to be named, not silently skipped"


def test_the_npm_pr_without_a_rust_change_fails_with_the_cli_lines(tmp_path):
    """The regression case, in the CLI's own words.

    app/package.json ahead of Cargo.lock on all three plugins is what merged on 2026-10-11 and what
    the release build then refused on. The guard quotes the same pairs so a rename of either side
    shows up here rather than in a build log an hour later.
    """
    pkg, lock = write_pair(
        tmp_path,
        {"notification": "^2.5.1", "process": "^2.4.0", "updater": "^2.13.2"},
        {"notification": "2.4.0", "process": "2.3.1", "updater": "2.12.0"},
    )
    result = run_guard("--app-package", pkg, "--cargo-lock", lock)
    assert result.returncode == 1, result.stdout
    for line in CLI_LINES_2026_10_11:
        assert line in result.stdout, f"the guard no longer reproduces: {line}"
    assert "dependency decision for the owner" in result.stdout


def test_a_rust_only_plugin_is_not_compared(tmp_path):
    """dialog, fs and log ship no npm package here; the CLI leaves them alone and so does this."""
    pkg, lock = write_pair(
        tmp_path,
        {"notification": "^2.5.1"},
        {"notification": "2.5.1", "dialog": "2.7.3", "fs": "2.5.2", "log": "2.9.0"},
    )
    result = run_guard("--app-package", pkg, "--cargo-lock", lock)
    assert result.returncode == 0, result.stdout


def test_a_plugin_the_shell_does_not_have_is_refused(tmp_path):
    """JS-only is the one direction that cannot work: the page asks for a crate that is not built."""
    pkg, lock = write_pair(tmp_path, {"sql": "^1.2.3"}, {"notification": "2.5.1"})
    result = run_guard("--app-package", pkg, "--cargo-lock", lock)
    assert result.returncode == 1, result.stdout
    assert "tauri-plugin-sql is not locked" in result.stdout, result.stdout


def test_a_side_that_cannot_be_read_refuses_a_pass(tmp_path):
    """Exit 2, not exit 0: an unreadable input is the guard's own failure, not a clean tree."""
    pkg, _lock = write_pair(tmp_path, {"notification": "^2.5.1"}, {"notification": "2.5.1"})
    missing = str(tmp_path / "no-such.lock")
    result = run_guard("--app-package", pkg, "--cargo-lock", missing)
    assert result.returncode == 2, result.stdout
    assert "refusing to report a pass" in result.stdout

    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    real_lock = str(ROOT / "app" / "src-tauri" / "Cargo.lock")
    result = run_guard("--app-package", str(broken), "--cargo-lock", real_lock)
    assert result.returncode == 2, result.stdout


@pytest.mark.parametrize(
    ("workflow", "hook"),
    [(".github/workflows/hygiene.yml", "scripts/ci_local.sh")],
)
def test_both_places_that_run_the_guard_name_it(workflow: str, hook: str):
    """Both call sites have to name the script, or the guard is only written, never run."""
    wf = (ROOT / workflow).read_text(encoding="utf-8")
    hk = (ROOT / hook).read_text(encoding="utf-8")
    assert "tauri_parity.py" in wf, f"{workflow} does not run the guard"
    assert "tauri_parity.py" in hk, f"{hook} does not run the guard"
    for trigger in ("app/package.json", "Cargo.lock"):
        assert trigger in hk, f"{hook} does not judge the guard on {trigger}"
