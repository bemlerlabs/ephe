#!/usr/bin/env python3
"""The six files that carry one version, read and written from one list.

`pyproject.toml` declares the number. `app/package.json`,
`app/src-tauri/tauri.conf.json` and `app/src-tauri/Cargo.toml` repeat it for a build tool
that cannot read the manifest, and `uv.lock` and `app/src-tauri/Cargo.lock` record it for
the two package managers. A release that edits one carrier and misses another ships a
bundle whose label disagrees with the version its health endpoint reports, so the cut,
the checklist, the post-release bump and the release workflow's version guard all read
this list instead of keeping their own.

The lock files spell a prerelease in PEP 440 (`0.7.0b1`) where the manifests keep the
semver form (`0.7.0-beta.1`). `set` writes each spelling its own format expects and
`check` compares the two normalised, so a bump changes no file it did not have to.

  scripts/version_carriers.py                print the verdict
  scripts/version_carriers.py --print        print the declared version only
  scripts/version_carriers.py --tag v0.7.0   judge a release tag against all six
  scripts/version_carriers.py --set 0.7.0    write all six, then check them

Exit codes: 0 every carrier agrees, 1 a carrier disagrees or the set failed, 2 an input
could not be read. Only `--set` writes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The carriers in the order the runbook names them. Paths are repository-relative.
CARRIERS = (
    "pyproject.toml",
    "app/package.json",
    "app/src-tauri/tauri.conf.json",
    "app/src-tauri/Cargo.toml",
    "app/src-tauri/Cargo.lock",
    "uv.lock",
)
PYPROJECT = "pyproject.toml"
PACKAGE_JSON = "app/package.json"
TAURI_CONF = "app/src-tauri/tauri.conf.json"
CARGO_MANIFEST = "app/src-tauri/Cargo.toml"
CARGO_LOCK = "app/src-tauri/Cargo.lock"
UV_LOCK = "uv.lock"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")
TAG = re.compile(r"^v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)$")
PEP440_PRE = {"alpha": "a", "beta": "b", "rc": "rc"}

try:  # the release box installs the project, the gates also run on a bare interpreter
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover - exercised only without the project's extras
    InvalidVersion = ValueError  # type: ignore[assignment]
    Version = None  # type: ignore[assignment]


def normalized(value: str) -> str:
    """One order for both spellings: `0.7.0-beta.1` and `0.7.0b1` name the same release."""
    if Version is not None:
        try:
            return str(Version(value))
        except InvalidVersion:
            return value
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-([A-Za-z]+)\.?(\d+)?)?", value)
    if not match:
        return value
    suffix = PEP440_PRE.get((match.group(2) or "").lower(), match.group(2) or "")
    return match.group(1) + suffix + (match.group(3) or "")


def pep440(value: str) -> str:
    """The lockfile spelling of a manifest version."""
    return normalized(value)


def _section(text: str, name: str) -> tuple[int, int]:
    match = re.search(rf"(?ms)^\[{re.escape(name)}\]\s*$(.*?)(?=^\[[^\]]+\]|\Z)", text)
    if not match:
        raise ValueError(f"no [{name}] section")
    return match.span(1)


def _toml_value(text: str, section: str, key: str) -> str:
    start, end = _section(text, section)
    match = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*["\']([^"\']+)["\']', text[start:end])
    if not match:
        raise ValueError(f"no {section}.{key}")
    return match.group(1)


def _set_toml_value(text: str, section: str, key: str, value: str) -> str:
    start, end = _section(text, section)
    body, count = re.subn(
        rf'(?m)^(\s*{re.escape(key)}\s*=\s*)["\'][^"\']*["\']',
        rf'\g<1>"{value}"',
        text[start:end],
        count=1,
    )
    if count != 1:
        raise ValueError(f"no {section}.{key}")
    return text[:start] + body + text[end:]


def _json_value(text: str, key: str) -> str:
    return str(json.loads(text)[key])


def _set_json_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf'("{re.escape(key)}"\s*:\s*)"[^"]*"')
    new, count = pattern.subn(rf'\g<1>"{value}"', text, count=1)
    if count != 1:
        raise ValueError(f"no JSON key {key}")
    return new


def _lock_value(text: str, package: str) -> str:
    for block in re.split(r"(?m)(?=^\[\[package\]\])", text):
        if re.search(rf'(?m)^name = "{re.escape(package)}"$', block):
            match = re.search(r'(?m)^version = "([^"]+)"', block)
            if not match:
                raise ValueError(f"the lock entry for {package} has no version")
            return match.group(1)
    raise ValueError(f"the lock lists no package named {package}")


def _set_lock_value(text: str, package: str, value: str) -> str:
    blocks = re.split(r"(?m)(?=^\[\[package\]\])", text)
    for index, block in enumerate(blocks):
        if re.search(rf'(?m)^name = "{re.escape(package)}"$', block):
            new, count = re.subn(r'(?m)^(version = )"[^"]*"', rf'\g<1>"{value}"', block, count=1)
            if count != 1:
                raise ValueError(f"the lock entry for {package} has no version")
            blocks[index] = new
            return "".join(blocks)
    raise ValueError(f"the lock lists no package named {package}")


def _project_name(root: Path) -> str:
    return _toml_value((root / PYPROJECT).read_text(encoding="utf-8"), "project", "name")


def _crate_name(root: Path) -> str:
    return _toml_value((root / CARGO_MANIFEST).read_text(encoding="utf-8"), "package", "name")


def declared_version(root: Path = REPO) -> str:
    return _toml_value((root / PYPROJECT).read_text(encoding="utf-8"), "project", "version")


def read_versions(root: Path = REPO) -> dict[str, str]:
    """The number each carrier exposes, keyed by repository path."""
    return {
        PYPROJECT: declared_version(root),
        PACKAGE_JSON: _json_value((root / PACKAGE_JSON).read_text(encoding="utf-8"), "version"),
        TAURI_CONF: _json_value((root / TAURI_CONF).read_text(encoding="utf-8"), "version"),
        CARGO_MANIFEST: _toml_value(
            (root / CARGO_MANIFEST).read_text(encoding="utf-8"), "package", "version"
        ),
        CARGO_LOCK: _lock_value(
            (root / CARGO_LOCK).read_text(encoding="utf-8"), _crate_name(root)
        ),
        UV_LOCK: _lock_value(
            (root / UV_LOCK).read_text(encoding="utf-8"), _project_name(root)
        ),
    }


def check(root: Path = REPO, expected: str | None = None) -> tuple[str, dict[str, str], list[str]]:
    """(declared, versions, problems); an empty problem list is the only passing state."""
    declared = declared_version(root)
    versions = read_versions(root)
    problems: list[str] = []
    if expected is not None and normalized(expected) != normalized(declared):
        problems.append(f"pyproject.toml declares {declared}, the release is {expected}")
    for rel in CARRIERS:
        if normalized(versions[rel]) != normalized(declared):
            problems.append(f"{rel} says {versions[rel]}, pyproject.toml declares {declared}")
    return declared, versions, problems


def tag_version(tag: str) -> str:
    match = TAG.fullmatch(tag.strip())
    if not match:
        raise ValueError(f"{tag!r} is not a release tag (expected vX.Y.Z)")
    return match.group(1)


def set_versions(root: Path, version: str) -> dict[str, str]:
    """Write all six carriers to `version`, then re-read them; a drift raises."""
    if not SEMVER.fullmatch(version):
        raise ValueError(f"{version!r} is not X.Y.Z (an optional -suffix is allowed)")
    lock_version = pep440(version)
    crate = _crate_name(root)
    project = _project_name(root)
    edits = {
        PYPROJECT: lambda text: _set_toml_value(text, "project", "version", version),
        PACKAGE_JSON: lambda text: _set_json_value(text, "version", version),
        TAURI_CONF: lambda text: _set_json_value(text, "version", version),
        CARGO_MANIFEST: lambda text: _set_toml_value(text, "package", "version", version),
        CARGO_LOCK: lambda text: _set_lock_value(text, crate, version),
        UV_LOCK: lambda text: _set_lock_value(text, project, lock_version),
    }
    # Read and rewrite every carrier in memory first, so a file that cannot be parsed
    # stops the bump before any other carrier has changed.
    updated = {rel: edits[rel]((root / rel).read_text(encoding="utf-8")) for rel in CARRIERS}
    for rel, text in updated.items():
        (root / rel).write_text(text, encoding="utf-8")
    _declared, versions, problems = check(root)
    if problems:
        raise ValueError("; ".join(problems))
    return versions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO, help="checkout to read or write")
    parser.add_argument("--print", action="store_true", help="print the declared version and exit")
    parser.add_argument("--check", action="store_true", help="judge the carriers (the default)")
    parser.add_argument("--tag", help="judge this release tag (vX.Y.Z) against all six carriers")
    parser.add_argument("--set", metavar="VERSION", help="write all six carriers, then check them")
    args = parser.parse_args(argv)

    try:
        if args.print:
            print(declared_version(args.root))
            return 0
        if args.set:
            versions = set_versions(args.root, args.set)
            print(f"version-carriers: wrote {len(versions)} carriers at {args.set}")
            return 0
        expected = tag_version(args.tag) if args.tag else None
        declared, _versions, problems = check(args.root, expected)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"version-carriers: cannot read or write a carrier: {exc}")
        return 2

    if problems:
        for problem in problems:
            print(f"version-carriers: FAIL {problem}")
        print(f"version-carriers: FAIL {len(problems)} carrier(s) disagree with {declared}")
        return 1
    if expected is not None:
        print(f"version-carriers: PASS tag v{expected} and all six carriers name {declared}")
    else:
        print(f"version-carriers: PASS all six carriers agree on {declared}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
