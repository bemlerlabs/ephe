#!/usr/bin/env python3
"""Lockfile agreement: what the manifest declares, what the lock recorded, and which tool ran.

Wave II of `docs/CI_HYBRID_CAPACITY_2026-10-11.md`, rows 6 and 36 of the residue. The npm group merge
`c10b9a99` moved 16 packages in `app/pnpm-lock.yaml` and it moved through `origin/main` without a
frozen-install check on the path, which is the class this file exists to close: a lock that no longer
agrees with its manifest installs something other than what the developer resolved, and
`pnpm install --frozen-lockfile` is the only command that says so.

Four checks, each with the unit it is stated in:

* **manifest to lock** -- every dependency in `app/package.json` has an importer entry in
  `app/pnpm-lock.yaml` whose `specifier` equals the declared range, and every importer entry is
  declared. This is the equality pnpm checks before it resolves anything, so it runs without a network
  or a `node_modules`.
* **the package manager pin** -- `packageManager` in `app/package.json` names `pnpm@<exact version>`,
  and the pnpm that answers `--version` in this job is that version. A listener resolving a different
  pnpm than the pin would regenerate the lock in a different shape and the diff would be a lie about
  what changed.
* **`lockfileVersion`** -- recorded, and compared against the value the pinned pnpm writes. Measured
  2026-10-11: `pnpm@11.10.0` and `lockfileVersion: '9.0'`.
* **Cargo manifest to lock** -- every dependency `app/src-tauri/Cargo.toml` declares is in
  `app/src-tauri/Cargo.lock`, at a version the declaration admits. Added 2026-10-14: the Tauri
  manifest pair was compared by nothing (`hygiene.yml` reads both only for plugin major/minor),
  so a crate bumped in the manifest with no `cargo update` left a lock that builds a different set
  than the manifest names. Read as text, so no Rust toolchain and no network are needed.

The Python half delegates to `uv lock --check` under the pinned `uv==0.13.5` that `tests.yml` already
names. `--require-uv` turns a missing uv into a refusal, so the leg cannot pass by never having had it.

`--diff` is a report rather than a fifth check, and both it and the two parsers it reads out of git
live in `scripts/lockfile_report.py`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lockfile_report import (  # noqa: E402,F401  (a sibling module; describe_diff is drawn on below)
    LOCK_SECTIONS,
    ROOT,
    CheckError,
    check_diff,
    describe_diff,
)

APP = ROOT / "app"  # the --app default, so a test can point the check at a planted pair
#: pnpm 11 writes lockfile version 9.0; the pair is what `pnpm@11.10.0` was observed producing on
#: 2026-10-11 in `c10b9a99`'s merge, and a bump must move both numbers in one commit.
EXPECTED_LOCKFILE_VERSION = "9.0"
#: The uv that generates `uv.lock` here. `tests.yml` names this exact number on its freshness step for
#: the reason written there -- a lock checked by a different resolver is a verdict about that resolver.
EXPECTED_UV_VERSION = "0.13.5"


def read_manifest(app: Path) -> dict:
    return json.loads((app / "package.json").read_text(encoding="utf-8"))


def read_lock(app: Path):
    try:
        import yaml  # noqa: PLC0415  (the only reader that speaks lockfile v9's YAML)
    except ImportError as exc:
        raise CheckError("PyYAML is not importable, so pnpm-lock.yaml cannot be read") from exc
    return yaml.safe_load((app / "pnpm-lock.yaml").read_text(encoding="utf-8"))


def manifest_ranges(manifest: dict) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for section in LOCK_SECTIONS:
        for name, spec in (manifest.get(section) or {}).items():
            out[name] = (section, str(spec))
    return out


def lock_entries(lock: dict) -> dict[str, tuple[str, str]]:
    importers = lock.get("importers") or {}
    root = importers.get(".")
    if root is None:
        raise CheckError("pnpm-lock.yaml carries no `importers: .` entry; the lock is not for this layout")
    out: dict[str, tuple[str, str]] = {}
    for section in LOCK_SECTIONS:
        for name, meta in (root.get(section) or {}).items():
            out[name] = (section, str((meta or {}).get("specifier")))
    return out


def check_agreement(manifest: dict, lock: dict) -> tuple[list[str], int]:
    declared = manifest_ranges(manifest)
    recorded = lock_entries(lock)
    problems = []
    for name, (section, spec) in sorted(declared.items()):
        entry = recorded.get(name)
        if entry is None:
            problems.append(f"{name}: declared in package.json `{section}` as {spec!r}, absent from the lock")
        elif entry[1] != spec:
            problems.append(f"{name}: the lock recorded specifier {entry[1]!r}, the manifest says {spec!r}")
    for name, (section, spec) in sorted(recorded.items()):
        if name not in declared:
            problems.append(f"{name}: importer entry in `{section}` ({spec!r}) with nothing declaring it")
    return problems, len(declared)


def check_package_manager(manifest: dict) -> tuple[list[str], str]:
    pin = manifest.get("packageManager")
    problems = []
    if not isinstance(pin, str) or not pin:
        return [f"packageManager is {pin!r}; expected the form pnpm@<exact version>"], ""
    match = re.fullmatch(r"pnpm@(\d+\.\d+\.\d+)(?:\+sha512\.[0-9a-f]+)?", pin)
    if not match:
        problems.append(f"packageManager {pin!r} is not an exact pnpm@major.minor.patch pin")
        return problems, ""
    return problems, match.group(1)


def resolved_pnpm_version() -> str | None:
    """The pnpm that answers on this PATH, or None when there is none there.

    A runner that never installed pnpm — the coverage leg pins node but not pnpm —
    resolves nothing, and `FileNotFoundError` is not a version: the caller reports
    the documented skip, or (`--require-pnpm`) the refusal, from the None return,
    exactly as it already does for a pnpm that answers non-zero.
    """
    try:
        done = subprocess.run(["pnpm", "--version"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    if done.returncode != 0:
        return None
    match = re.search(r"\d+\.\d+\.\d+", done.stdout)
    return match.group(0) if match else None


#: The Tauri shell's manifest pair. Nothing checked that these two agree: `hygiene.yml`
#: compares Tauri plugin versions between them, and a crate bumped in Cargo.toml with no
#: `cargo update` leaves a lock whose resolved set is not what the manifest declares.
CARGO_MANIFEST = ROOT / "app" / "src-tauri" / "Cargo.toml"
CARGO_LOCK = ROOT / "app" / "src-tauri" / "Cargo.lock"
CARGO_DEP_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def cargo_manifest_requirements(text: str) -> dict[str, str]:
    """{crate: requirement} for the dependency tables of a Cargo manifest.

    `version = "1.2"` and `name = { version = "1.2", features = [...] }` are both read; a
    path or git dependency carries no registry version and is skipped, because there is no
    entry in a lock's `[[package]]` set to compare it against.
    """
    out: dict[str, str] = {}
    table = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        header = re.fullmatch(r"\[([^\]]+)\]", line)
        if header:
            table = header.group(1)
            continue
        if table not in CARGO_DEP_TABLES:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+)\s*=\s*(.+)", line)
        if not match:
            continue
        name, value = match.group(1), match.group(2).strip()
        if value.startswith("{"):
            inner = re.search(r'version\s*=\s*"([^"]+)"', value)
            if inner:
                out[name] = inner.group(1)
            continue
        out[name] = value.strip().strip('"')
    return out


def cargo_lock_packages(text: str) -> dict[str, list[str]]:
    """{crate: [version]} for every `[[package]]` in a Cargo lock. A crate can appear more
    than once (one block per platform or feature resolution), so all of them are returned."""
    out: dict[str, list[str]] = {}
    name: str | None = None
    version: str | None = None
    inside = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "[[package]]":
            if inside and name and version:
                out.setdefault(name, []).append(version)
            name = version = None
            inside = True
            continue
        if not inside:
            continue
        if name is None and (match := re.fullmatch(r'name = "([^"]+)"', line)):
            name = match.group(1)
        elif version is None and (match := re.fullmatch(r'version = "([^"]+)"', line)):
            version = match.group(1)
    if inside and name and version:
        out.setdefault(name, []).append(version)
    return out


def _numbers(value: str) -> tuple[int, ...]:
    core = re.split(r"[-+]", value, maxsplit=1)[0]
    return tuple(int(part) if part.isdigit() else 0 for part in core.split("."))


def _satisfies(locked: str, requirement: str) -> bool:
    """Whether a locked version reaches the requirement's minimum.

    A bare `1.2.3` means `^1.2.3` in Cargo, and the minimum is the only half this check can
    compute: a lock below what the manifest asks for is the disagreement, while a lock above
    it is the legal outcome of a caret range. Anything that is not a single comparand (a
    comma range, a wildcard) answers True — this must not report a verdict it cannot read.
    """
    requirement = requirement.strip()
    if not requirement or requirement == "*" or "," in requirement or requirement.endswith(".*"):
        return True
    match = re.fullmatch(r"(?P<op>\^|~|=|>=|>|<=|<)?\s*(?P<version>\d+(?:\.\d+)*)", requirement)
    if not match:
        return True
    if (match.group("op") or "^") in ("<", "<="):
        return True
    return _numbers(locked) >= _numbers(match.group("version"))


def check_cargo_lock(require: bool) -> tuple[list[str], str]:
    """The manifest-to-lock equality for the Tauri shell, read without a Rust toolchain.

    `cargo update` would be the authority; a job that has to install Rust to ask a question
    about two committed text files is a job that stops being run. The equality that matters
    is the one a stale lock breaks: every crate the manifest declares is in the lock, at a
    version the declaration admits.
    """
    if not (CARGO_MANIFEST.is_file() and CARGO_LOCK.is_file()):
        line = "Cargo.toml and Cargo.lock are not both present under app/src-tauri"
        return ([f"{line}; this leg expects the Tauri manifest pair"] if require else []), line
    requirements = cargo_manifest_requirements(CARGO_MANIFEST.read_text(encoding="utf-8"))
    if not requirements:
        raise CheckError("no dependency parsed from app/src-tauri/Cargo.toml — "
                         "a check with no input is not a clean check")
    packages = cargo_lock_packages(CARGO_LOCK.read_text(encoding="utf-8"))
    if not packages:
        raise CheckError("no [[package]] parsed from app/src-tauri/Cargo.lock — "
                         "a lock with no packages is not a clean lock")
    lock_version = re.search(r"^version = (\d+)$", CARGO_LOCK.read_text(encoding="utf-8"), re.M)
    problems: list[str] = []
    for name, requirement in sorted(requirements.items()):
        versions = packages.get(name)
        if not versions:
            problems.append(f"{name}: declared in Cargo.toml as {requirement!r}, absent from "
                            "Cargo.lock — the lock was not re-resolved after the manifest moved")
            continue
        below = [version for version in versions if not _satisfies(version, requirement)]
        if below:
            problems.append(f"{name}: Cargo.toml asks for {requirement!r}, Cargo.lock pins "
                            f"{below}")
    return problems, (f"{len(requirements)} declared crate(s) against {len(packages)} locked, "
                      f"lockfile version {lock_version.group(1) if lock_version else '?'}")


def check_uv_lock(require: bool) -> tuple[list[str], str]:
    """`uv lock --check`, only under the resolver that wrote the lock.

    A dev machine carrying an older uv gets a loud skip rather than a red that belongs to the tool:
    uv 0.8.0 on this MacBook is two majors behind the pin and its `--check` verdict measures nothing
    about the committed lockfile.
    """
    try:
        done = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False)
    except OSError:
        # No uv on this PATH is the same verdict as a uv that is not the pin: a loud
        # skip, not a crash. Under `--require-uv` it is the refusal the leg installed
        # it for, so the check can never pass by never having had uv.
        done = None
    if done is None or done.returncode != 0:
        message = (f"uv did not resolve, so uv.lock was not checked (the leg pins "
                   f"{EXPECTED_UV_VERSION})")
        return ([message] if require else []), f"skipped: {message}"
    found = re.search(r"\d+\.\d+\.\d+", done.stdout)
    version = found.group(0) if found else "?"
    if version != EXPECTED_UV_VERSION:
        message = f"uv {version} ran where the leg pins {EXPECTED_UV_VERSION}"
        return ([message] if require else []), f"skipped: uv {version}, the leg pins {EXPECTED_UV_VERSION}"
    probe = subprocess.run(["uv", "lock", "--check"], capture_output=True, text=True,
                           check=False, cwd=ROOT)
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip().splitlines()
        return (["uv.lock is not what the pinned uv generates: "
                 + (detail[-1] if detail else "")]), f"refused by uv {version}"
    return [], f"agrees, uv {version}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require-pnpm", action="store_true",
                        help="fail when pnpm does not resolve, for a leg that installed it")
    parser.add_argument("--require-uv", action="store_true", help="same for uv")
    parser.add_argument("--require-cargo", action="store_true",
                        help="fail when the Tauri manifest pair is not both present")
    parser.add_argument("--app", type=Path, default=APP,
                        help="the directory holding package.json and pnpm-lock.yaml")
    parser.add_argument("--skip-uv", action="store_true", help="do not look at uv.lock at all")
    parser.add_argument("--diff", metavar="REV..REV",
                        help="print what moved between two revisions instead of checking the tree")
    args = parser.parse_args(argv)

    if args.diff:
        return check_diff(args.diff)

    manifest = read_manifest(args.app)
    lock = read_lock(args.app)
    failures: list[str] = []

    problems, count = check_agreement(manifest, lock)
    failures += problems
    print(f"lockfile: manifest to lock -- {count} declared entries compared, {len(problems)} disagreement(s)")

    pin_problems, pinned = check_package_manager(manifest)
    failures += pin_problems
    actual = resolved_pnpm_version()
    if actual is None:
        line = "pnpm did not resolve on this PATH"
        if args.require_pnpm:
            failures.append(f"{line}; the leg installed it and expected it to answer")
        print(f"lockfile: package manager pin -- {line} (pin {manifest.get('packageManager')!r})")
    else:
        print(f"lockfile: package manager pin -- pin says pnpm@{pinned or '?'}, `pnpm --version` says {actual}")
        if pinned and actual != pinned:
            failures.append(f"pnpm {actual} ran where packageManager pins {pinned}")

    recorded_version = str(lock.get("lockfileVersion"))
    print(f"lockfile: lockfileVersion {recorded_version!r}, this repository expects "
          f"{EXPECTED_LOCKFILE_VERSION!r}")
    if recorded_version != EXPECTED_LOCKFILE_VERSION:
        failures.append(f"lockfileVersion {recorded_version!r} is not the {EXPECTED_LOCKFILE_VERSION!r} "
                        "the pinned pnpm writes")

    uv_problems, uv_version = ([], "not run") if args.skip_uv else check_uv_lock(args.require_uv)
    failures += uv_problems
    print(f"lockfile: uv lock --check -- {uv_version}")

    cargo_problems, cargo_summary = check_cargo_lock(args.require_cargo)
    failures += cargo_problems
    print(f"lockfile: Cargo manifest to lock -- {cargo_summary}")

    for failure in failures:
        print(f"lockfile: FAIL {failure}")
    if failures:
        return 1
    print("lockfile: pass")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (CheckError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"lockfile: FAIL {exc}")
        sys.exit(2)
