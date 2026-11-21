#!/usr/bin/env python3
"""Tauri parity: the JS side and the Rust side of every shared plugin agree, and every route and
platform read in the app is declared in the shell manifest.

Why this exists, from 2026-10-11: `npm run tauri build` refused before compiling a single crate,
because `app/package.json` carried JS plugin packages ahead of the Rust crates in `Cargo.lock`:

    tauri-plugin-notification (v2.4.0) : @tauri-apps/plugin-notification (v2.5.1)
    tauri-plugin-updater (v2.12.0) : @tauri-apps/plugin-updater (v2.13.2)
    tauri-plugin-process (v2.3.1) : @tauri-apps/plugin-process (v2.4.0)

The npm PR merged with no Rust change beside it, and nothing between the merge and the release
build looked at the pair. Catching it here costs two file reads instead of a build attempt.

The rule is the CLI's own: a plugin that exists on both sides has to agree on major and minor.
Rust-only plugins are legitimate and are not compared — `tauri-plugin-dialog`, `-fs` and `-log`
are called through the raw `window.__TAURI__` bridge and ship no npm package in this app, and
the Tauri CLI leaves them alone too. A JS-only plugin is the one direction that cannot be legitimate:
the frontend asks the shell for a command whose crate is not in the build.

The second question is the same shape one level up, and it was the 5x audit's gap: the PWA and the
desktop shell drift unless both surfaces are named. `app/tests/playwright/shell-parity.manifest.json`
is that naming. Every `<Route path=…>` in `app/src/App.tsx` has an entry there, and every read of
`isTauri` / `isDesktopShell` / `window.__TAURI__` in `app/src` is counted there with what it answers
on each side. A route or a branch that is present in the code and absent from the manifest is drift
in the same sense a plugin version is; the browser spec then compares exactly the declared set, so
it cannot pass over a screen nobody listed.

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

#: The three names the frontend uses to ask whether it is inside the shell. `isTauriRuntime` in
#: taskNotify.ts is counted through its `__TAURI__` read; `\b` keeps `isTauri` from matching
#: inside it.
MARKER_RE = re.compile(r"\bisTauri\b|\bisDesktopShell\b|\b__TAURI__\b")
ROUTE_RE = re.compile(r'<Route\b[^>]*?\bpath="([^"]+)"', re.S)
TESTID_RE = re.compile(r'data-testid="([^"]+)"')
REACHES = {"route", "settings-register"}
PLATFORM_ONLY_IDS = {"window-controls", "service-worker"}


class ManifestError(ValueError):
    """The manifest is unreadable; the caller reports this as exit code 2."""


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


def route_paths(app_tsx: Path) -> list[str]:
    """Every `<Route path=…>` in App.tsx, in source order. The path attribute is first in each."""
    return ROUTE_RE.findall(app_tsx.read_text(encoding="utf-8"))


def _code_only(text: str) -> str:
    """Drop comment-only lines so a documentation sentence does not count as a platform read.

    The detector is whole-line: every marker in `app/src` sits on a code line, and a
    trailing comment is not where a branch hides. A string that starts a line with `//` or `/*`
    would be dropped too, which can only under-count — the failure mode a manifest update shows.
    """
    kept: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        starts_comment = stripped.startswith(("//", "/*", "*", "{/*"))
        if starts_comment:
            if stripped.startswith(("/*", "{/*")) and "*/" not in stripped:
                in_block = True
            continue
        kept.append(line)
    return "\n".join(kept)


def _source_files(app_src: Path) -> list[Path]:
    return [
        path
        for path in sorted(app_src.rglob("*"))
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not path.name.endswith(".d.ts")
        and ".test." not in path.name
        and ".spec." not in path.name
        and "__tests__" not in path.parts
    ]


def platform_reads(app_src: Path) -> dict[tuple[str, str], int]:
    """(repo-relative file, marker) -> occurrences in product code. Tests and declarations are out."""
    counts: dict[tuple[str, str], int] = {}
    for path in _source_files(app_src):
        code = _code_only(path.read_text(encoding="utf-8"))
        relative = path.relative_to(REPO).as_posix()
        for match in MARKER_RE.finditer(code):
            key = (relative, match.group(0))
            counts[key] = counts.get(key, 0) + 1
    return counts


def known_testids(app_src: Path) -> set[str]:
    found: set[str] = set()
    for path in _source_files(app_src):
        if path.suffix == ".tsx":
            found.update(TESTID_RE.findall(path.read_text(encoding="utf-8")))
    return found


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: the manifest is not a JSON object")
    for key in ("routes", "platform_branches", "platform_only"):
        if not isinstance(data.get(key), list):
            raise ManifestError(f"{path}: '{key}' is missing or not a list")
    mobile = data.get("mobile")
    if not isinstance(mobile, dict) or not isinstance(mobile.get("widths"), list):
        raise ManifestError(f"{path}: 'mobile.widths' is missing or not a list")
    if not isinstance(mobile.get("surfaces"), list):
        raise ManifestError(f"{path}: 'mobile.surfaces' is missing or not a list")
    for width in mobile["widths"]:
        if not isinstance(width, int) or not 320 <= width <= 1024:
            raise ManifestError(f"{path}: mobile width {width!r} is not an integer in 320..1024")
    for entry in data["platform_branches"]:
        if not isinstance(entry, dict) or not {"file", "marker", "count"}.issubset(entry):
            raise ManifestError(f"{path}: a platform_branches entry lacks file, marker or count")
        if not isinstance(entry["count"], int) or entry["count"] < 1:
            raise ManifestError(f"{path}: {entry['file']} has a non-positive count")
        if entry["marker"] not in {"isTauri", "isDesktopShell", "__TAURI__"}:
            raise ManifestError(f"{path}: {entry['marker']!r} is not a known marker")
    for entry in data["routes"]:
        if not isinstance(entry, dict) or not {"path", "probe", "page", "anchor"}.issubset(entry):
            raise ManifestError(f"{path}: a routes entry lacks path, probe, page or anchor")
    return data


def shell_drift(manifest: dict, app_tsx: Path, app_src: Path) -> list[str]:
    """Every disagreement between the app and its manifest, in one list a reader can act on."""
    drift: list[str] = []
    declared = [entry["path"] for entry in manifest["routes"]]
    for path in sorted({p for p in declared if declared.count(p) > 1}):
        drift.append(f'route "{path}" is declared more than once')
    code_routes = route_paths(app_tsx)
    for path in sorted(set(code_routes) - set(declared)):
        drift.append(f'route "{path}" is in App.tsx but not in the manifest')
    for path in sorted(set(declared) - set(code_routes)):
        drift.append(f'route "{path}" is in the manifest but not in App.tsx')

    source = app_tsx.read_text(encoding="utf-8")
    ids = known_testids(app_src)
    for entry in manifest["routes"]:
        if entry["page"] not in source:
            drift.append(f'route "{entry["path"]}" names page {entry["page"]}, which App.tsx does not mention')
        anchor = re.search(r'data-testid="([^"]+)"', str(entry["anchor"]))
        if not anchor:
            drift.append(f'route "{entry["path"]}" has no data-testid anchor')
        elif anchor.group(1) not in ids:
            drift.append(f'route "{entry["path"]}" anchors on data-testid "{anchor.group(1)}", which app/src does not render')
        probe = str(entry["probe"])
        if not probe.startswith("/") or probe.startswith("#"):
            drift.append(f'route "{entry["path"]}" has probe {probe!r}; it must be a hash path such as /chat')

    code_reads = platform_reads(app_src)
    listed = {(entry["file"], entry["marker"]): entry["count"] for entry in manifest["platform_branches"]}
    for key in sorted(set(code_reads) - set(listed)):
        drift.append(f"{key[0]} reads {key[1]} {code_reads[key]} time(s), the manifest does not list it")
    for key in sorted(set(listed) - set(code_reads)):
        drift.append(f"{key[0]} is listed for {key[1]}, but app/src no longer reads it")
    for key in sorted(set(listed) & set(code_reads)):
        if listed[key] != code_reads[key]:
            drift.append(
                f"{key[0]} reads {key[1]} {code_reads[key]} time(s), the manifest declares {listed[key]}"
            )

    declared_only = {entry["id"] for entry in manifest["platform_only"]}
    for missing in sorted(PLATFORM_ONLY_IDS - declared_only):
        drift.append(f"platform_only does not declare {missing!r}")
    for entry in manifest["platform_only"]:
        if entry.get("present_on") not in {"web", "desktop", "both"}:
            drift.append(f"platform_only {entry.get('id')!r} does not say which side it lives on")
        if entry.get("kind") == "dom" and not entry.get("selector"):
            drift.append(f"platform_only {entry.get('id')!r} is a DOM difference without a selector")

    for surface in manifest["mobile"]["surfaces"]:
        if surface.get("reach") not in REACHES:
            drift.append(f"mobile surface {surface.get('path')!r} has reach {surface.get('reach')!r}")
        if surface.get("reach") == "route" and surface.get("path") not in declared:
            drift.append(f"mobile surface {surface.get('path')!r} is not one of the declared routes")
    return drift


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--app-package", type=Path, default=REPO / "app" / "package.json")
    ap.add_argument("--cargo-lock", type=Path, default=REPO / "app" / "src-tauri" / "Cargo.lock")
    ap.add_argument(
        "--manifest",
        type=Path,
        default=REPO / "app" / "tests" / "playwright" / "shell-parity.manifest.json",
    )
    ap.add_argument("--app-tsx", type=Path, default=REPO / "app" / "src" / "App.tsx")
    ap.add_argument("--app-src", type=Path, default=REPO / "app" / "src")
    args = ap.parse_args(argv)

    missing = [
        str(p)
        for p in (args.app_package, args.cargo_lock, args.manifest, args.app_tsx, args.app_src)
        if not p.exists()
    ]
    if missing or not args.app_tsx.is_file() or not args.app_src.is_dir():
        unreadable = missing or [str(args.app_tsx), str(args.app_src)]
        print(f"tauri-parity: cannot read {', '.join(unreadable)} — refusing to report a pass")
        return 2
    try:
        js = js_plugins(args.app_package)
        rs = rust_plugins(args.cargo_lock)
        manifest = load_manifest(args.manifest)
        drift = shell_drift(manifest, args.app_tsx, args.app_src)
    except (OSError, ValueError) as exc:
        print(f"tauri-parity: {type(exc).__name__}: {exc}")
        return 2

    status = 0
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
        status = 1
    elif js:
        shared = sorted(set(js) & set(rs))
        print(
            f"tauri-parity: {len(shared)} plugin pair(s) agree "
            f"({', '.join(f'{n} {js[n]}' for n in shared)}); "
            f"rust-only, not compared: {', '.join(rust_only) if rust_only else 'none'}"
        )
    else:
        print("tauri-parity: no @tauri-apps/plugin-* in app/package.json — nothing to compare")
    if unreadable:
        status = 2

    if drift:
        print(
            "tauri-parity: the shell manifest and the app disagree. "
            f"{args.manifest.name} has to name every route and every platform read:"
        )
        for line in drift:
            print(f"  {line}")
        print("Add the entry (with what the branch answers on web and desktop) or remove the branch; "
              "then run `npx playwright test -c tests/playwright/playwright.config.ts shell-parity` "
              "in app/ to compare the declared set in both platforms.")
        status = 1
    else:
        print(
            f"tauri-parity: {len(manifest['routes'])} route(s) and "
            f"{len(manifest['platform_branches'])} platform read(s) are declared"
        )
    return status


if __name__ == "__main__":
    sys.exit(main())
