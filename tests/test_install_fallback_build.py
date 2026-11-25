"""The installer's PWA-build branch holds its promises (task-1, 2026-11-25).

Measured on ubuntu:noble containers (arm64 and amd64): with apt node 18.19.1 and
npm 9.2.0 the npm fallback installed its dependencies (rc=0) and then died at
vite's config load — `@tailwindcss/oxide` reports "Cannot find native binding
(https://github.com/npm/cli/issues/4828)" because npm silently skipped the
platform binding whose engines (node>=20) exclude the running node — and the
install ended with "PWA build failed: app/dist/index.html does not exist".
These cases pin the shape that fixed it: the pinned pnpm is fetched before any
npm fallback, the last-resort npm branch pulls the platform binding by name,
and no path ends "success" without app/dist/index.html.

install.sh is a shell script the product cannot import, so these cases read its
source for the contract — the same reason tests/test_macos_usage_strings.py and
tests/test_dev_handle_gate.py read files, and one case runs the installer's own
extraction expression against the real manifest instead of trusting a pattern.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "install.sh"
INSTALL_PS1 = ROOT / "install.ps1"
APP_PKG = ROOT / "app" / "package.json"


@pytest.fixture(scope="module")
def sh() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def test_pin_extraction_answers_for_the_real_manifest(sh: str) -> None:
    # The installer must derive the pnpm version from app/package.json — the
    # tree's only package-manager truth (tests/test_r46_pnpm_single_source.py).
    # A hardcoded version would drift the moment the pin moves, so the check is
    # the installer's own extraction run against the manifest as it is today.
    declared = json.loads(APP_PKG.read_text(encoding="utf-8"))["packageManager"]
    assert declared.startswith("pnpm@")
    wanted = declared.split("@", 1)[1]
    sed_expr = re.search(r"sed -n '(s/.*packageManager[^']*p)'", sh)
    assert sed_expr is not None, "no sed extraction of the packageManager pin"
    if shutil.which("bash") is None:
        pytest.skip("bash is the installer's shell")
    out = subprocess.run(
        ["bash", "-c", f"sed -n '{sed_expr.group(1)}' '{APP_PKG}' | head -1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == wanted


def test_pinned_pnpm_is_fetched_before_the_npm_fallback(sh: str) -> None:
    fetched = sh.find('npx --yes "pnpm@$pnpm_pin"')
    npm_build = sh.find('npm --prefix "$PROJECT_DIR/app" run build')
    assert fetched != -1, "install.sh never fetches the pinned pnpm"
    assert npm_build != -1
    assert fetched < npm_build, (
        "the pinned pnpm must be attempted before npm gets the build — on npm 9 "
        "with node 18 the npm build dies on the oxide binding (npm/cli#4828)"
    )


def test_npm_branch_pulls_the_oxide_binding_without_touching_the_manifest(sh: str) -> None:
    assert re.search(r"npm\b[^\n]*install --no-save[^\n]*--no-package-lock[\s\S]{0,90}@tailwindcss/oxide-", sh), (
        "the last-resort npm branch must pull the @tailwindcss/oxide platform "
        "binding by name with --no-save, so app/package.json and pnpm-lock.yaml "
        "stay untouched"
    )
    # --no-package-lock stays: a second lockfile is forbidden by
    # tests/test_r46_pnpm_single_source.py.
    assert "install --no-package-lock" in sh


def test_no_path_reports_success_without_dist_index(sh: str) -> None:
    gate = re.search(
        r"! -f \"\$PROJECT_DIR/app/dist/index\.html\".*\n\s*fail", sh
    )
    assert gate is not None, (
        "the dist/index.html check must fail the install; it is the proof a "
        "PWA build happened"
    )
    assert "npm/cli/issues/4828" in sh, (
        "the failing message must name the upstream npm bug so the next "
        "person is not left guessing"
    )


def test_powershell_mirror_keeps_the_same_contract() -> None:
    ps1 = INSTALL_PS1.read_text(encoding="utf-8")
    assert "packageManager" in ps1, "install.ps1 must read the same pin"
    assert "4828" in ps1, "install.ps1 must name the same upstream bug"


def test_reexec_after_clone_replays_the_callers_flags(sh: str) -> None:
    # The fresh-clone path re-enters the script from the checkout; the argument
    # loop shifts every flag away first, so a re-exec with "$@" silently loses
    # --no-start and --cli (measured: --no-start still ran `ephe start --open`
    # and held the installer, 2026-11-25). The re-exec must replay the captured
    # original arguments, and the capture must precede the loop.
    capture = re.search(r'ORIG_ARGS=\("\$@"\)', sh)
    assert capture is not None, "the script must capture its arguments up front"
    loop = sh.index("while [ $# -gt 0 ]")
    assert capture.start() < loop, "the capture must happen before the shift loop"
    reexec = re.search(r'exec bash \./install\.sh [^\n]*', sh)
    assert reexec is not None, "the clone path re-enters install.sh"
    assert "ORIG_ARGS" in reexec.group(0), (
        "the re-exec must forward the captured flags, not the post-loop $@: "
        "--no-start and --cli die silently otherwise"
    )
