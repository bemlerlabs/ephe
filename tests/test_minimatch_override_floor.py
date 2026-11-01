"""The minimatch floor GHSA-g3hv-75wg-m249 asks for, held in the workspace and the lock.

The advisory covers `minimatch < 11.0.1`, and the two copies this frontend resolved sat far
below it on ranges their parents allow: 3.1.5 under `@eslint/config-array` and
`@eslint/eslintrc`, 10.2.6 under `@typescript-eslint/typescript-estree`. No release of any of
those parents asks for 11, so the only way to reach the patched line is an override across two
majors — and an override is exactly the kind of entry a later install quietly drops. The
wasmtime floor in `tests/test_cell_runtime_floor.py` is the same shape of guard for the same
reason. pnpm 11 reads overrides from `pnpm-workspace.yaml`, not from `package.json`; the file
says so in a warning, and a row placed in the manifest would be ignored rather than obeyed.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "app" / "pnpm-workspace.yaml"
LOCK = ROOT / "app" / "pnpm-lock.yaml"

FLOOR = (11, 0, 1)


def _semver(text: str) -> tuple[int, int, int]:
    major, minor, patch = (text.split("-")[0].split(".") + ["0", "0"])[:3]
    return int(major), int(minor), int(patch)


def _override() -> str | None:
    payload = yaml.safe_load(WORKSPACE.read_text(encoding="utf-8")) or {}
    return (payload.get("overrides") or {}).get("minimatch")


def _locked_versions() -> list[str]:
    return sorted(set(re.findall(r"^  minimatch@([0-9]+\.[0-9]+\.[0-9]+)", LOCK.read_text(encoding="utf-8"), re.M)))


def test_the_workspace_overrides_minimatch_to_the_patched_line():
    override = _override()
    assert override, "app/pnpm-workspace.yaml must carry overrides.minimatch"
    digits = re.findall(r"(\d+\.\d+\.\d+)", str(override))
    assert digits, f"the override {override!r} names no version"
    assert min(_semver(d) for d in digits) >= FLOOR, (
        f"the override {override!r} admits versions below {'.'.join(map(str, FLOOR))}"
    )


def test_every_locked_minimatch_is_at_or_above_the_floor():
    versions = _locked_versions()
    assert versions, "the lock lists no minimatch resolution"
    below = [v for v in versions if _semver(v) < FLOOR]
    assert not below, f"minimatch {below} is below the patched line {'.'.join(map(str, FLOOR))}"


def test_the_lock_and_the_override_agree_on_one_resolution():
    """One override, one copy: two locked minimatch versions would mean a parent still
    reaching around the override, and the advisory would stay open."""
    assert len(_locked_versions()) == 1, _locked_versions()
