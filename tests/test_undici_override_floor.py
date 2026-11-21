"""The undici floor CVE-2026-120474 asks for, held in the workspace and the lock.

The advisory's affected list names `v8.12.2` and `v8.12.3` and stops there: 8.12.4 is the
first release outside it, and npm's `latest` is 8.12.4. The frontend never asked for undici
by name — it arrives as `jsdom@30.1.2`'s own `^8.11.2` — and `app/pnpm-workspace.yaml` held
`overrides: undici: 8.12.2`, which is inside the range. So the version that decided the
exposure was a pin nobody had looked at, and an override is exactly the kind of entry a
later install quietly drops. `tests/test_minimatch_override_floor.py` is the same shape of
guard for the same reason, and pnpm 11 reads overrides from the workspace file, not from the
manifest.

Two databases were consulted before this floor was written down, and one of them is the
reason it lives in a test rather than in `.github/advisories-ignore.txt`: OSV answers for
`CVE-2026-120474` with a Git-scoped record whose `affected[].package` is empty, and
`GHSA-7xg3-fphp-28hg` 404s on both `api.osv.dev/v1/vulns` and the GitHub advisory API,
because it is published as a repository advisory under `nodejs/undici` and has not reached
the global database. `scripts/advisory_id_check.py` resolves every register line through
those two routes and refuses a line that names no package, so a row here would fail the
register's own check — the floor is held where it can be read instead. `pnpm audit` reports
0 findings on this lock for the same reason: its feed has no npm-scoped entry for this CVE.
Measured 2026-11-09: `pnpm audit --json` and `pnpm audit --prod --json` both clean at 8.12.2,
which is precisely how an exposed version passes a scan-based gate.

Scope is development: undici reaches the tree only through jsdom, which the vitest
environment uses. It is not in the shipped bundle, and it is not what the product's own
HTTP calls go through.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "app" / "pnpm-workspace.yaml"
LOCK = ROOT / "app" / "pnpm-lock.yaml"

FLOOR = (8, 12, 4)


def _semver(text: str) -> tuple[int, int, int]:
    major, minor, patch = (text.split("-")[0].split(".") + ["0", "0"])[:3]
    return int(major), int(minor), int(patch)


def _override() -> str | None:
    payload = yaml.safe_load(WORKSPACE.read_text(encoding="utf-8")) or {}
    return (payload.get("overrides") or {}).get("undici")


def _locked_versions() -> list[str]:
    return sorted(
        set(re.findall(r"^  undici@([0-9]+\.[0-9]+\.[0-9]+)", LOCK.read_text(encoding="utf-8"), re.M))
    )


def test_the_workspace_overrides_undici_to_the_patched_line():
    override = _override()
    assert override, "app/pnpm-workspace.yaml must carry overrides.undici"
    digits = re.findall(r"(\d+\.\d+\.\d+)", str(override))
    assert digits, f"the override {override!r} names no version"
    assert min(_semver(d) for d in digits) >= FLOOR, (
        f"the override {override!r} admits versions below {'.'.join(map(str, FLOOR))}, "
        "which is inside CVE-2026-120474's affected range"
    )


def test_every_locked_undici_is_at_or_above_the_floor():
    versions = _locked_versions()
    assert versions, "the lock lists no undici resolution"
    below = [v for v in versions if _semver(v) < FLOOR]
    assert not below, f"undici {below} is below the patched line {'.'.join(map(str, FLOOR))}"


def test_the_lock_and_the_override_agree_on_one_resolution():
    """One override, one copy: two locked undici versions would mean a parent still
    reaching around the override, and the advisory would stay open."""
    assert len(_locked_versions()) == 1, _locked_versions()
