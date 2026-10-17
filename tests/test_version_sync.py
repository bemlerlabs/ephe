"""One number, five carriers: this file pins every copy to the manifest that declares it.

`pyproject.toml` `[project].version` is the declared source. `app/package.json`,
`app/src-tauri/tauri.conf.json` and `app/src-tauri/Cargo.toml` each repeat it for a
build tool that cannot read the manifest, and `core/_version.py` reads it back for the
running program. A release that edits one carrier and misses another ships a bundle
whose label disagrees with the version its own health endpoint reports.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core import __version__ as core_version
from core import _version as version_module
from tests.toml_compat import tomllib

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CARRIERS = {
    "app/package.json": ROOT / "app" / "package.json",
    "app/src-tauri/tauri.conf.json": ROOT / "app" / "src-tauri" / "tauri.conf.json",
    "app/src-tauri/Cargo.toml": ROOT / "app" / "src-tauri" / "Cargo.toml",
}
# Locks carry the number too, and a stale one is not a cosmetic problem: the release
# workflow refuses to build on it (`uv lock --check`) and the Rust build refuses a
# Cargo.lock that disagrees with its manifest. Both were missed while these two files
# were absent from the list above, and both failures surfaced only in CI because the
# local uv is not the pinned one and its check skips with a pass verdict.
UV_LOCK = ROOT / "uv.lock"
CARGO_LOCK = ROOT / "app" / "src-tauri" / "Cargo.lock"
CARGO_MANIFEST = ROOT / "app" / "src-tauri" / "Cargo.toml"


def declared_version() -> str:
    """`[project].version` of the root pyproject.toml, the one declared source."""
    with PYPROJECT.open("rb") as fh:
        return str(tomllib.load(fh)["project"]["version"])


def carrier_version(path: Path) -> str:
    """The number `path` exposes: a JSON `version` key, or TOML `[package].version`."""
    if path.suffix == ".json":
        return str(json.loads(path.read_text(encoding="utf-8"))["version"])
    return str(tomllib.loads(path.read_text(encoding="utf-8"))["package"]["version"])


def lock_package_version(path: Path, package: str) -> str | None:
    """The `version` a lockfile records for `package`, or None when it lists no such
    entry. Both locks are TOML arrays of tables, a shape `carrier_version` does not read.
    """
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    for entry in data.get("package", []):
        if entry.get("name") == package:
            return str(entry.get("version"))
    return None


def normalized(value: str):
    """One order for both spellings: a manifest writes `0.1.0-beta.2`, a lock file
    writes the PEP 440 form `0.1.0b2`, and they name the same release."""
    from packaging.version import Version

    return Version(value)


def test_declared_source_is_a_concrete_release_number():
    """GIVEN the manifest that declares the version
    WHEN its value is read
    THEN it is a three-part release number a package manager accepts."""
    value = declared_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", value), value


@pytest.mark.parametrize("rel", sorted(CARRIERS))
def test_each_carrier_equals_the_declared_source(rel: str):
    """GIVEN a build tool that keeps its own copy of the number
    WHEN the copy is compared with the declared source
    THEN the two agree, so the bundle and the manifest label the same release."""
    got = carrier_version(CARRIERS[rel])
    source = declared_version()
    assert got == source, f"{rel} says {got}, pyproject.toml declares {source}"


def test_the_uv_lock_carries_the_declared_version():
    """GIVEN uv.lock, which the release workflow verifies before it builds
    WHEN its entry for this project is compared with the declared source
    THEN they name the same release, so the supply-chain guard has nothing to refuse."""
    got = lock_package_version(UV_LOCK, "ephe")
    assert got is not None, "uv.lock lists no entry for this project"
    assert normalized(got) == normalized(declared_version()), (
        f"uv.lock says {got}, pyproject.toml declares {declared_version()}"
    )


def test_the_cargo_lock_carries_the_crate_version():
    """GIVEN Cargo.lock, which the desktop build reads with --locked
    WHEN its entry for the app crate is compared with the crate manifest
    THEN they agree, so the bundle build can resolve its own dependency graph."""
    with CARGO_MANIFEST.open("rb") as fh:
        crate = str(tomllib.load(fh)["package"]["name"])
    got = lock_package_version(CARGO_LOCK, crate)
    assert got is not None, f"Cargo.lock lists no entry for the crate {crate}"
    assert normalized(got) == normalized(declared_version()), (
        f"Cargo.lock says {got} for {crate}, pyproject.toml declares {declared_version()}"
    )


def test_python_reader_derives_from_the_declared_source():
    """GIVEN the runtime reader in core/_version.py
    WHEN it resolves the number without a packaged install
    THEN the manifest is read back and no second literal is held."""
    source = declared_version()
    assert version_module.source_tree_version() == source
    assert version_module.version_string() == source
    assert core_version == source


def test_python_core_carries_no_version_literal():
    """GIVEN every Python module under core/
    WHEN each source file is scanned for the declared number
    THEN none of them holds it as a literal, so the manifest stays the one home."""
    source = declared_version()
    pattern = re.compile(rf"(?<![\d.]){re.escape(source)}(?![\d.])")
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "core").rglob("*.py"))
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"the version literal also lives in {offenders}"
