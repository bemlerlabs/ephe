#!/usr/bin/env python3
"""Refuse an open Dependabot alert that no register row decides.

Owner rule 2026-11-24: an open security alert without a registered, checkable decision
is a defect on the product. This check compares the open alert list against the ID
lines of .github/advisories-ignore.txt and then reads the register back against the
lockfiles: a row that claims `state=fixed` has to match the lock its ecosystem names,
so an advisory cannot be retired in prose while the locked version still carries it.

The alert list arrives from the Dependabot alerts API (`--fetch`, the CI route, needs
the token to hold a read on the alerts) or from a JSON file (`--alerts`, the local
route the tests drive). Exit codes: 0 every alert carries a row and every fixed row
matches its lock; 1 a comparison failed; 2 nothing was checked — no token, an API
refusal, an unreadable input. 2 is a refusal to render a verdict, and CI must show it
as one: the step propagates it instead of green.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"
# The register names ecosystems the way its own audits do; the alert API names them
# the way the package managers do. One map, both directions agree on the lockfile.
ALERT_ECOSYSTEMS = {"rust": "crates.io", "pip": "PyPI", "npm": "npm"}
LOCKFILES = {
    "crates.io": Path("app") / "src-tauri" / "Cargo.lock",
    "PyPI": Path("uv.lock"),
    "npm": Path("app") / "pnpm-lock.yaml",
}
ROW = re.compile(r"^(?P<id>\S+)\s+#\s+(?P<fields>\S.*)$")
FIELD = re.compile(r"(?P<key>[a-z_]+)=(?P<value>\S+)")
CARGO_BLOCK = re.compile(
    r'\[\[package\]\]\nname = "(?P<name>[^"]+)"\nversion = "(?P<version>[^"]+)"'
)
PNPM_ENTRY = re.compile(r"(?m)^\s{2}/?(?P<name>[^\s@(/][^@(/]*)@(?P<version>[0-9][^:(\s]*)")
GIT_SOURCE = re.compile(r'^source = "git\+(?P<url>[^"]+)"', re.MULTILINE)
BLOCK_NAME = re.compile(r'^name = "(?P<name>[^"]+)"', re.MULTILINE)
BLOCK_VERSION = re.compile(r'^version = "(?P<version>[^"]+)"', re.MULTILINE)


class Refused(Exception):
    """No verdict may be rendered: an input cannot be read or the API said no."""


def parse_register(path: Path) -> list[dict[str, str]]:
    """Read the ID lines of the register. Comments and blanks are format, not entries."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"register unreadable: {exc}") from exc
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = ROW.match(stripped)
        if not m:
            continue
        row = {"id": m["id"]}
        row.update(dict(FIELD.findall(m["fields"])))
        rows.append(row)
    return rows


def parse_lock_versions(path: Path) -> dict[str, list[str]]:
    """Every name→versions a lockfile carries, per its own format."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, list[str]] = {}
    if path.name.endswith(".yaml"):
        pairs = ((m["name"], m["version"]) for m in PNPM_ENTRY.finditer(text))
    else:
        pairs = ((m["name"], m["version"]) for m in CARGO_BLOCK.finditer(text))
    for name, version in pairs:
        found.setdefault(name, []).append(version)
    return found


def version_key(version: str) -> tuple[int, ...]:
    """Numeric prefix of a version, so 0.20.0-rc.1 orders under 0.20.0."""
    parts: list[int] = []
    for chunk in version.split("."):
        digits = re.match(r"\d+", chunk)
        if not digits:
            break
        parts.append(int(digits.group(0)))
    return tuple(parts)


def alert_ids(alert: dict) -> set[str]:
    ids = set()
    advisory = alert.get("security_advisory") or {}
    for key in ("ghsa_id", "cve_id"):
        value = advisory.get(key)
        if isinstance(value, str) and value:
            ids.add(value.lower())
    return ids


def git_sourced_packages(path: Path) -> list[tuple[str, str, str]]:
    """(name, version, url) for every lock entry resolved from a git repository.

    `scripts/lockfile_check.py` compares declared crates against locked versions and
    never reads a `source` line, so a lock entry repointed to a foreign git fork —
    the form a supply-chain attacker prefers because it keeps the version string —
    is invisible to every other gate in this repository. A shipped crate sourced from
    a git repository needs a written decision naming the repository owner and a
    re-fetch plan; the register has no field for that yet, so any git source here
    surfaces as a finding.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    found: list[tuple[str, str, str]] = []
    for block in text.split("[[package]]")[1:]:
        source = GIT_SOURCE.search(block)
        if not source:
            continue
        name = BLOCK_NAME.search(block)
        version = BLOCK_VERSION.search(block)
        found.append((name["name"] if name else "?",
                      version["version"] if version else "?",
                      source["url"]))
    return found


def evaluate(alerts: list[dict], rows: list[dict[str, str]], root: Path,
             register_name: str) -> list[str]:
    """The two comparisons. Each finding is one line a human can act on."""
    findings: list[str] = []
    for name, version, url in git_sourced_packages(
            root / "app" / "src-tauri" / "Cargo.lock"):
        findings.append(
            f"Cargo.lock resolves {name} v{version} from git source {url} — a shipped "
            "crate sourced from a git repository needs a written decision naming the "
            "repository owner and a re-fetch plan, which this register cannot hold yet"
        )
    row_ids = {row["id"].lower() for row in rows}
    for alert in alerts:
        ids = alert_ids(alert)
        if ids and not (ids & row_ids):
            package = ((alert.get("dependency") or {}).get("package") or {})
            findings.append(
                f"open alert #{alert.get('number')} {'/'.join(sorted(ids))} for "
                f"{package.get('name', '?')} ({package.get('ecosystem', '?')}) has no "
                f"row in {register_name}"
            )
    for row in rows:
        if row.get("state") != "fixed":
            continue
        package, fixed_in = row.get("package"), row.get("fixed_in", "none")
        ecosystem = row.get("ecosystem")
        if not package or fixed_in in (None, "", "none") or ecosystem not in LOCKFILES:
            continue
        lock = root / LOCKFILES[ecosystem]
        versions = parse_lock_versions(lock)
        locked = versions.get(package)
        if locked is None:
            locked = versions.get(package.replace("_", "-"))
            locked = (locked or []) + versions.get(package.replace("-", "_"), [])
        if not locked:
            # A development-scoped PyPI row can legitimately name tooling no lockfile
            # carries — `uv` and `pip` are held by installer pins, and
            # tests/test_supply_chain_gate.py asserts uv is absent from uv.lock on
            # purpose. A runtime row claiming a fix the lock never heard of is a finding.
            if ecosystem == "PyPI" and row.get("scope") == "development":
                continue
            findings.append(
                f"row {row['id']} claims state=fixed for {package}, but {lock.name} "
                f"does not carry the package at all"
            )
            continue
        highest = max(locked, key=version_key)
        if version_key(highest) < version_key(fixed_in):
            findings.append(
                f"row {row['id']} claims state=fixed fixed_in={fixed_in} for {package}, "
                f"but {lock.name} resolves it at {highest}"
            )
    return findings


def alerts_from_file(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"alert list unreadable: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("alerts", [])
    if not isinstance(payload, list):
        raise Refused("alert list is neither a JSON array nor an object with 'alerts'")
    return payload


def fetch_alerts(repo: str, token: str) -> list[dict]:
    url = f"{API_ROOT}/repos/{repo}/dependabot/alerts?state=open&per_page=100"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ephe-supply-chain-register-check",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise Refused(
            f"the alerts API answered HTTP {exc.code} for {repo}: the token cannot "
            "read dependabot alerts (the job needs security-events: read)"
        ) from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise Refused(f"the alerts API could not be read: {exc}") from exc
    if not isinstance(payload, list):
        raise Refused("the alerts API answered something that is not a list")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--alerts", type=Path, help="JSON alert list from the API")
    source.add_argument("--fetch", action="store_true",
                        help="read open alerts from the API with $GITHUB_TOKEN")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                        help="owner/name; defaults to $GITHUB_REPOSITORY")
    parser.add_argument("--register", type=Path,
                        default=Path(".github/advisories-ignore.txt"))
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="repository root the lockfile paths are read from")
    args = parser.parse_args(argv)

    def announce(line: str) -> None:
        prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") == "true" else ""
        print(f"{prefix}{line}")

    try:
        if args.fetch:
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token:
                raise Refused(
                    "no GITHUB_TOKEN in this run, so the alert list was never read"
                )
            if not args.repo:
                raise Refused("no repository name: --repo or GITHUB_REPOSITORY is needed")
            alerts = fetch_alerts(args.repo, token)
        else:
            alerts = alerts_from_file(args.alerts)
        rows = parse_register(args.register)
    except Refused as exc:
        announce(f"dependabot register check: nothing was checked — {exc}. "
                 "This is not a pass.")
        return 2

    findings = evaluate(alerts, rows, args.root, str(args.register))
    if findings:
        for line in findings:
            announce(line)
        print(f"{len(findings)} finding(s): every open alert needs a register row and "
              "every fixed row must match its lock.")
        return 1
    print(f"{len(alerts)} open alert(s) covered, {len(rows)} register row(s) read: "
          "every open alert carries a row and every fixed row matches its lock.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
