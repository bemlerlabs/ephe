#!/usr/bin/env python3
"""Resolve every accepted advisory ID against the databases that publish it.

The register files are the only place this repository accepts a dependency risk, so a
line there carries two claims: the ID names a real advisory, and it is an advisory
about the package the line names. Nothing in the tree checked either one — and an ID
that resolves to nothing is the worst case, because `pip-audit --ignore-vuln` shrugs at
it and the gate stays green while the register claims a decision was made.

ID shapes are validated per publisher before a row is trusted; that parser, the field vocabulary
and the pip/pnpm verdicts live in `scripts/advisory_register.py`. This file owns the half that
needs a database: the OSV lookup, the engine and Cargo audits, and the walk over every ID.

The lookup is two-routed for the same reason. A direct `/v1/vulns/<id>` answer is not
the whole truth: some advisories are published under one database's ID and appear in
another only as an *alias* — a crates.io/RustSec entry whose GitHub string is an alias.
Reading that 404 as "invented" is wrong in the other direction, so an unresolved ID is
retried as a package-scoped query and matched against `id` *and* `aliases`. Only when
both routes miss does this exit 1.

Network on purpose: this is a claim about an external database, and an offline test of
it would assert nothing. CI runs it in `.github/workflows/supply-chain.yml`; the same
line is what a developer runs: `python3 scripts/advisory_id_check.py`.

    --ignore-flags   print the `--ignore-vuln` arguments for the Python register, so the
                     workflow and this check cannot disagree about which IDs exist. Rows
                     whose ecosystem is not PyPI, and rows whose state is `pending-fix`,
                     are left out: a release is within reach for those, so they stay
                     visible in the audit rather than being silenced by a flag.
    --recheck-pairs  print `<id> <recheck>` for every entry, so the expiry step reads its
                     dates from this parser instead of carrying a second ID regex.
    --pip-verdict    read the `pip-audit --format json` report and exit 1 when it holds a
                     finding no register row decides, matched on the ID *or* any alias. The
                     audit step's own exit code is not the verdict: it is soft so its summary
                     is always written, and a finding that reached no register line used to
                     announce itself as nothing more than a warning.
    --audit-cargo    ask the crates.io database about every crate `app/src-tauri/Cargo.lock`
                     pins, and exit 1 when one carries an advisory no register row decides.
                     That lockfile was audited by no workflow at all: `hygiene.yml` reads it
                     only to compare Tauri plugin versions, so the Rust half of the desktop
                     shell was covered by Dependabot's alerts and by nothing that can fail.
    --pnpm-verdict   the same judgement for `pnpm audit --json`: exit 1 when an npm advisory
                     is in no register row, whatever its scope. The JS step already annotates
                     a runtime-reachable finding, and an annotation does not stop a job.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from advisory_register import (  # noqa: E402  (a sibling module, loaded by path like this file)
    ENGINE_REGISTER,
    ROOT,
    _audit_pip_report,
    _audit_pnpm_report,
    _entries,
    _registered,
)

#: The Tauri shell's resolved crate set. No workflow read it for advisories before this
#: check existed; `hygiene.yml` reads the same file for plugin version parity only.
CARGO_LOCK = ROOT / "app" / "src-tauri" / "Cargo.lock"
#: `querybatch` takes a bounded query list; 512 crates fit in one call today and the chunking
#: is what keeps that true.
OSV_BATCH = 500
OSV = "https://api.osv.dev/v1"


def _get(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"content-type": "application/json", "user-agent": "ephe-supply-chain-gate"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read() or b"{}"
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {}
    except OSError as exc:  # DNS, TLS, timeout — a database we cannot reach proves nothing
        raise SystemExit(f"FATAL: cannot reach {url}: {exc}") from exc


def _resolves(row: dict[str, str]) -> tuple[bool, str]:
    """(does the ID exist, and does it speak about the package the line names?)"""
    status, doc = _get(f"{OSV}/vulns/{row['id']}")
    if status == 200:
        named = {a.get("package", {}).get("name", "") for a in doc.get("affected", [])}
        if row["package"] not in named:
            return False, f"resolves, but affects {sorted(n for n in named if n)} — not the " \
                f"declared package {row['package']!r}"
        return True, f"direct hit (packages: {', '.join(sorted(n for n in named if n))})"

    eco, pkg, probe = row.get("ecosystem", "PyPI"), row["package"], row.get("probe")
    if not probe:
        return False, f"direct lookup HTTP {status} and no probe= version to search by"
    status2, found = _get(
        f"{OSV}/query", {"package": {"name": pkg, "ecosystem": eco}, "version": probe}
    )
    if status2 == 200:
        for vuln in found.get("vulns", []):
            if row["id"] == vuln.get("id") or row["id"] in (vuln.get("aliases") or []):
                return True, f"alias of {vuln.get('id')} for {pkg}@{probe} in {eco}"
        hit = sorted(v.get("id", "") for v in found.get("vulns", []))
        return False, f"no record: direct HTTP {status}, and {pkg}@{probe} ({eco}) reports " \
            f"{hit or 'nothing'} — none of them is {row['id']} or lists it as an alias"
    return False, f"no record: direct HTTP {status}, package lookup HTTP {status2}"


def _audit_engine(rows: list[dict[str, str]]) -> int:
    """Ask the databases what they say about the engine versions we lock, and name
    anything the register has not decided yet.

    This is the half the pip audit cannot do: `pip-audit` asks the PyPI ecosystem about
    the pip package, and the execution engine inside that wheel is a Rust crate with
    its own advisories. Report-only by design, like the audits in the workflow — a
    finding here becomes a register line with a written exposure, never a red X on
    somebody else's day.
    """
    wanted: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        if row["file"] != ENGINE_REGISTER.name:
            continue
        key = (row["package"], row.get("ecosystem", "PyPI"), row["probe"])
        wanted.setdefault(key, set()).add(row["id"])
    if not wanted:
        print("No engine register entry to audit: the check ran against nothing.")
        return 1

    leaked = 0
    for (pkg, eco, probe), registered in sorted(wanted.items()):
        status, found = _get(f"{OSV}/query", {"package": {"name": pkg, "ecosystem": eco},
                                             "version": probe})
        if status != 200:
            print(f"::error::{pkg}@{probe} ({eco}): advisory lookup HTTP {status} — no verdict")
            return 1
        seen = found.get("vulns", [])
        print(f"{pkg}@{probe} ({eco}): {len(seen)} advisory record(s)")
        for vuln in seen:
            identifiers = {vuln.get("id", "")} | set(vuln.get("aliases") or [])
            if identifiers & registered:
                continue
            leaked += 1
            fixes = sorted({
                event.get("fixed", "")
                for aff in vuln.get("affected", [])
                for rng in aff.get("ranges", [])
                for event in rng.get("events", [])
                if "fixed" in event
            })
            print(
                f"::warning::{vuln.get('id')} affects {pkg}@{probe} and is in no register — "
                f"aliases {', '.join(sorted(identifiers - {vuln.get('id', '')})) or 'none'}, "
                f"fixed in {', '.join(fixes) or 'no release'}: "
                f"{(vuln.get('summary') or '')[:110]}"
            )
    if leaked:
        print(
            f"\n{leaked} advisory record(s) reach a locked engine version with no written "
            "decision. Add a line to .github/engine-advisories.txt (with the exposure you "
            "measured and what is missing from it), or move the version."
        )
    else:
        print("\nEvery advisory the databases report for a locked engine version is registered.")
    return 0


def _aliases_of(identifier: str) -> tuple[set[str], list[str], str]:
    """(the ID with its aliases, the versions it is fixed in, its summary).

    The advisory records this repository's own findings live in are split across
    databases: the crates.io record for glib is published as `RUSTSEC-2024-0429` and
    the register cites the GitHub string `GHSA-wrw7-89jp-8q8g` as an alias, so a
    comparison that reads only the primary ID would report a decided finding as
    undecided and a note that nothing was written down would be wrong.
    """
    status, doc = _get(f"{OSV}/vulns/{identifier}")
    if status != 200:
        return {identifier}, [], ""
    aliases = {identifier} | set(doc.get("aliases") or [])
    fixes = sorted({
        event.get("fixed", "")
        for aff in doc.get("affected", [])
        for rng in aff.get("ranges", [])
        for event in rng.get("events", [])
        if "fixed" in event and event.get("fixed")
    })
    return aliases, fixes, doc.get("summary") or ""


def _cargo_packages() -> list[tuple[str, str]]:
    """(name, version) for every `[[package]]` in the Tauri shell's lockfile.

    Read as the lock writes it rather than through a TOML parser, so the check runs on
    the interpreter this repository already pins (`tests.yml` uses 3.12, the development
    interpreter is older, and `tomllib` exists in neither half of that pair).
    """
    if not CARGO_LOCK.is_file():
        raise SystemExit(f"FATAL: {CARGO_LOCK} is missing — the Cargo audit has no input")
    out: list[tuple[str, str]] = []
    name: str | None = None
    version: str | None = None
    inside = False
    for line in CARGO_LOCK.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s == "[[package]]":
            if inside and name and version:
                out.append((name, version))
            name = version = None
            inside = True
            continue
        if not inside:
            continue
        if name is None and (m := re.match(r'name = "([^"]+)"$', s)):
            name = m.group(1)
        elif version is None and (m := re.match(r'version = "([^"]+)"$', s)):
            version = m.group(1)
    if inside and name and version:
        out.append((name, version))
    if not out:
        raise SystemExit(f"FATAL: no [[package]] parsed from {CARGO_LOCK} — a set that "
                         "resolves to nothing is not a clean audit")
    return out


def _osv_batch(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], list[str]]:
    """{(name, version): [advisory ID]} for the crates that carry a record.

    One request per 500 crates: the per-package route would be 512 round trips, and a
    gate that takes minutes to answer gets switched off.
    """
    hit: dict[tuple[str, str], list[str]] = {}
    for start in range(0, len(pairs), OSV_BATCH):
        chunk = pairs[start:start + OSV_BATCH]
        status, doc = _get(f"{OSV}/querybatch", {"queries": [
            {"package": {"name": name, "ecosystem": "crates.io"}, "version": version}
            for name, version in chunk]})
        if status != 200:
            raise SystemExit(f"FATAL: the crates.io batch lookup answered HTTP {status} — "
                             f"no verdict for {len(chunk)} crate(s)")
        results = doc.get("results")
        if not isinstance(results, list) or len(results) != len(chunk):
            raise SystemExit(f"FATAL: the batch lookup returned {len(results) if isinstance(results, list) else 'no'} "
                             f"result(s) for {len(chunk)} crate(s) — a short answer is not a clean one")
        for (name, version), result in zip(chunk, results):
            ids = sorted({v.get("id", "") for v in (result.get("vulns") or [])} - {""})
            if ids:
                hit[(name, version)] = ids
    return hit


def _audit_cargo(rows: list[dict[str, str]]) -> int:
    """The leg `app/src-tauri/Cargo.lock` had none of.

    Dependabot's crates.io alerts are the only thing that ever looked at this file, and an
    alert is a notification: it arrives on GitHub, it has no exit code, and a repository
    with nobody watching the alert page ships the advisory. Measured 2026-10-14 the
    register held one crates.io row (glib) and no workflow could have produced it.
    """
    registered = _registered(rows, "crates.io")
    packages = _cargo_packages()
    hit = _osv_batch(packages)
    print(f"Cargo lock: {len(packages)} crate(s) pinned in {CARGO_LOCK.relative_to(ROOT)}, "
          f"{len(hit)} with an advisory record.")
    undecided: list[str] = []
    for (name, version), ids in sorted(hit.items()):
        identifiers: set[str] = set()
        fixes: list[str] = []
        for identifier in ids:
            aliases, vuln_fixes, _ = _aliases_of(identifier)
            identifiers |= aliases
            fixes = sorted(set(fixes) | set(vuln_fixes))
        if identifiers & registered:
            print(f"  decided  {name}@{version}: {', '.join(sorted(identifiers))}")
            continue
        undecided.append(f"{name}@{version}")
        print(f"::error::{name}@{version} carries {', '.join(sorted(identifiers))} and no "
              f"register row decides it (fixed in {', '.join(fixes) or 'no release'})")
    if undecided:
        print(f"\n{len(undecided)} crate(s) carry an advisory with no written decision: "
              f"{', '.join(undecided)}. Add a line to .github/advisories-ignore.txt with "
              "ecosystem=crates.io, the exposure you measured and what is missing from it, "
              "or move the crate.")
        return 1
    print("\nEvery crates.io advisory on a pinned crate is a written decision.")
    return 0


def main(argv: list[str]) -> int:
    rows = _entries()
    if "--ignore-flags" in argv:
        pip_ids = [r["id"] for r in rows
                   if r.get("ecosystem", "PyPI") == "PyPI"
                   and r.get("state", "accepted") == "accepted"]
        print(" ".join(f"--ignore-vuln {i}" for i in pip_ids))
        return 0
    if "--recheck-pairs" in argv:
        for row in rows:
            print(f"{row['id']} {row['recheck']}")
        return 0
    if "--audit-engine" in argv:
        return _audit_engine(rows)
    if "--audit-cargo" in argv:
        return _audit_cargo(rows)
    if "--pip-verdict" in argv:
        try:
            report = Path(argv[argv.index("--pip-verdict") + 1])
        except IndexError:
            raise SystemExit("FATAL: --pip-verdict needs the path to a pip-audit JSON report") from None
        return _audit_pip_report(report, rows)
    if "--pnpm-verdict" in argv:
        try:
            report = Path(argv[argv.index("--pnpm-verdict") + 1])
        except IndexError:
            raise SystemExit("FATAL: --pnpm-verdict needs the path to a pnpm-audit JSON report") from None
        return _audit_pnpm_report(report, rows)

    bad: list[str] = []
    for row in rows:
        ok, note = _resolves(row)
        print(f"{'ok   ' if ok else 'FAIL '} {row['id']:<22} {row['file']:<24} {note}")
        if not ok:
            bad.append(f"{row['id']} ({row['file']}): {note}")
    print(f"\n{len(rows) - len(bad)}/{len(rows)} accepted advisory IDs resolve.")
    if bad:
        print("::error::" + "; ".join(bad)
              + " — an accepted risk that names no advisory is not an accepted risk. Point the line "
                "at the advisory's real ID (check its aliases), or retire the entry in writing; "
                "leaving the ID in place keeps pip-audit ignoring nothing while the register claims "
                "a decision was made.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
