#!/usr/bin/env python3
"""Tauri plugin parity: the JS side and the Rust side of every shared plugin agree.

Why this exists, from 2026-10-11: `npm run tauri build` refused before compiling a single crate,
because `app/package.json` carried JS plugin packages ahead of the Rust crates in `Cargo.lock`:

    tauri-plugin-notification (v2.4.0) : @tauri-apps/plugin-notification (v2.5.1)
    tauri-plugin-updater (v2.12.0) : @tauri-apps/plugin-updater (v2.13.2)
    tauri-plugin-process (v2.3.1) : @tauri-apps/plugin-process (v2.4.0)

The npm PR merged with no Rust change beside it, and nothing between the merge and the release
build looked at the pair. Catching it here costs two file reads instead of a build attempt.

The rule is the CLI's own: a plugin that exists on both sides has to agree on major and minor.
Rust-only plugins are legitimate and are not compared — `tauri-plugin-dialog`, `-fs` and `-log`
are called through the raw `window.__TAURI__` bridge and ship no npm package in this app, and the
Tauri CLI leaves them alone too. A JS-only plugin is the one direction that cannot be legitimate:
the frontend asks the shell for a command whose crate is not in the build.

Exit codes follow the other gates in `scripts/`: 0 agree, 1 a real mismatch, 2 the guard could not
read what it was asked to judge — a silent pass is worse than the defect it watches.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS_PREFIX = "@tauri-apps/plugin-"
RS_PREFIX = "tauri-plugin-"


def js_plugins(package_json: Path) -> dict[str, str]:
    """Plugin name -> version, from dependencies and devDependencies together."""
    data = json.loads(package_json.read_text(encoding="utf-8"))
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    return {
        name[len(JS_PREFIX):]: str(spec).lstrip("^~=")
        for name, spec in deps.items()
        if name.startswith(JS_PREFIX)
    }


def rust_plugins(cargo_lock: Path) -> dict[str, str]:
    """Plugin name -> locked version. The lock is the truth of what compiles, not Cargo.toml."""
    versions: dict[str, str] = {}
    for block in cargo_lock.read_text(encoding="utf-8").split("[[package]]"):
        name = re.search(r'name = "([^"]+)"', block)
        version = re.search(r'version = "([^"]+)"', block)
        if name and version and name.group(1).startswith(RS_PREFIX):
            versions[name.group(1)[len(RS_PREFIX):]] = version.group(1)
    return versions


def _two_parts(version: str) -> tuple[int, int] | None:
    parts = re.match(r"^(\d+)\.(\d+)", version)
    if not parts:
        return None
    return int(parts.group(1)), int(parts.group(2))


def compare(js: dict[str, str], rs: dict[str, str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """(mismatches in the CLI's own wording, rust-only names that are fine, js-only names, unreadables)."""
    mismatches: list[str] = []
    unreadable: list[str] = []
    for name in sorted(set(js) & set(rs)):
        left, right = _two_parts(js[name]), _two_parts(rs[name])
        if left is None or right is None:
            unreadable.append(f"{name}: version is not a number.number pair (js={js[name]}, rust={rs[name]})")
            continue
        if left != right:
            mismatches.append(
                f"{RS_PREFIX}{name} (v{rs[name]}) : {JS_PREFIX}{name} (v{js[name]})"
            )
    js_only = [
        f"{RS_PREFIX}{name} is not locked, so {JS_PREFIX}{name} (v{js[name]}) has no crate to call"
        for name in sorted(set(js) - set(rs))
    ]
    rust_only = sorted(set(rs) - set(js))
    return mismatches, rust_only, js_only, unreadable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--app-package", type=Path, default=REPO / "app" / "package.json")
    ap.add_argument("--cargo-lock", type=Path, default=REPO / "app" / "src-tauri" / "Cargo.lock")
    args = ap.parse_args(argv)

    missing = [str(p) for p in (args.app_package, args.cargo_lock) if not p.is_file()]
    if missing:
        print(f"tauri-parity: cannot read {', '.join(missing)} — refusing to report a pass")
        return 2
    try:
        js = js_plugins(args.app_package)
        rs = rust_plugins(args.cargo_lock)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"tauri-parity: {type(exc).__name__}: {exc}")
        return 2

    if not js:
        print("tauri-parity: no @tauri-apps/plugin-* in app/package.json — nothing to compare")
        return 0

    mismatches, rust_only, js_only, unreadable = compare(js, rs)
    for line in unreadable:
        print(f"tauri-parity: {line}")
    if mismatches or js_only:
        print(
            "tauri-parity: the npm plugins and the locked Rust crates disagree on major or minor. "
            "`npm run tauri build` refuses on exactly this, before compiling:"
        )
        for line in mismatches:
            print(f"  {line}")
        for line in js_only:
            print(f"  {line}")
        print("Fix on the side that moved: either lock the matching tauri-plugin-* crate, or hold "
              "the npm package back. A coupled tauri/wry move is a dependency decision for the owner.")
        return 1

    shared = sorted(set(js) & set(rs))
    print(
        f"tauri-parity: {len(shared)} plugin pair(s) agree "
        f"({', '.join(f'{n} {js[n]}' for n in shared)}); "
        f"rust-only, not compared: {', '.join(rust_only) if rust_only else 'none'}"
    )
    return 2 if unreadable else 0


if __name__ == "__main__":
    sys.exit(main())
