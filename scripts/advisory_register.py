"""The advisory register: its rows, the ID shapes they must match, and the verdicts read off them.

`.github/advisories-ignore.txt` and `.github/engine-advisories.txt` are the only place this
repository accepts a dependency risk, so every step that judges an audit report against a row
reads the register through here: the `--ignore-vuln` flags the workflow hands to `pip-audit`,
the re-check pairs, and the pip/pnpm verdicts in `.github/workflows/supply-chain.yml`. One
parser and one field vocabulary, so a step cannot decide an advisory by a row another step
would not have parsed.

No network in this half. A report on disk is compared against rows on disk; asking the
databases belongs to `scripts/advisory_id_check.py`, which owns the lookup.

ID shapes are validated per publisher before anything is trusted, and an unrecognised shape is
a failure rather than a skipped line. That rule exists because of a measured mistake: GHSA
identifiers are alphanumeric (`GHSA-j2g9-4prp-pf6h`), PYSEC and RUSTSEC ones are numeric
(`PYSEC-2026-311`), and a pattern written for the numeric form drops the other without saying so.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIP_REGISTER = ROOT / ".github" / "advisories-ignore.txt"
ENGINE_REGISTER = ROOT / ".github" / "engine-advisories.txt"
REGISTERS = (PIP_REGISTER, ENGINE_REGISTER)

#: One candidate line: an ID-shaped token at column 0 (so a comment never parses as an
#: entry) followed by the `# key=value` fields.
CANDIDATE = re.compile(
    r"^(?!#)(?P<id>[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\s+#\s+(?P<fields>\S.*?)$", re.M
)
#: Publisher-specific ID shapes. Anything else is a defect in a register, not a line to skip.
SHAPES = {
    "CVE": re.compile(r"^CVE-\d{4}-\d{4,7}$"),
    "GHSA": re.compile(r"^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$"),
    "PYSEC": re.compile(r"^PYSEC-\d{4}-\d{3,7}$"),
    "RUSTSEC": re.compile(r"^RUSTSEC-\d{4}-\d{3,4}$"),
    "ALSA": re.compile(r"^ALSA-\d{4}-\d{4}$"),
    "USN": re.compile(r"^USN-\d{4}-\d{1,2}$"),
}
FIELD = re.compile(r"(?P<key>package|ecosystem|probe|affected|scope|state|fixed_in|blocked_by|recheck)=(?P<val>\S+)")


def _shape_error(identifier: str) -> str | None:
    """None when the ID matches its publisher's published shape, else the complaint."""
    prefix = identifier.split("-", 1)[0].upper()
    rule = SHAPES.get(prefix)
    if rule is None:
        return f"unknown advisory publisher {prefix!r}"
    if not rule.match(identifier):
        return f"{prefix} does not match the published shape {rule.pattern}"
    return None


def _entries() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    problems: list[str] = []
    for path in REGISTERS:
        if not path.is_file():
            raise SystemExit(f"FATAL: register {path} is missing — the gate has no input")
        for m in CANDIDATE.finditer(path.read_text(encoding="utf-8")):
            identifier, fields = m.group("id"), m.group("fields")
            bad = _shape_error(identifier)
            if bad:
                problems.append(f"{path.name}: {identifier} — {bad}")
                continue
            row = {"id": identifier, "file": path.name}
            row.update({f.group("key"): f.group("val") for f in FIELD.finditer(fields)})
            for required in ("package", "fixed_in", "recheck"):
                if required not in row:
                    problems.append(f"{path.name}: {identifier} lacks {required}=")
            rows.append(row)
    if problems:
        print("\n".join(f"FATAL: {p}" for p in problems), file=sys.stderr)
        raise SystemExit(1)
    if not rows:
        raise SystemExit(f"FATAL: no entry parsed from {[p.name for p in REGISTERS]}")
    return rows


def _registered(rows: list[dict[str, str]], ecosystem: str) -> set[str]:
    """Every ID the PyPI register carries for one ecosystem.

    A finding whose ID (or one of its aliases) is written down here is accounted for,
    whatever state the row is in: the state says what is being done about it, and the
    row's presence says somebody has seen it.
    """
    return {r["id"] for r in rows
            if r["file"] == PIP_REGISTER.name
            and r.get("ecosystem", "PyPI") == ecosystem}


def _audit_pip_report(path: Path, rows: list[dict[str, str]]) -> int:
    """Judge the `pip-audit --format json` report against the register's rows.

    The audit step is deliberately soft — its summary has to be written whether or not it
    found anything — and that softness used to be the whole verdict: an unaccepted Python
    finding printed a warning, the run stayed green, and the only thing that could ever
    fail the job was a re-check date passing. A finding that arrived today then waited for
    a date in the register instead of failing where it appeared, which is the same silence
    in a slower form.
    """
    if not path.is_file():
        raise SystemExit(f"FATAL: {path} is missing — the audit produced no report to judge")
    try:
        report = json.loads(path.read_text(encoding="utf-8") or "")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {path} is not the JSON pip-audit writes: {exc}") from exc
    # `pip-audit --format json` writes a top-level array of {name, version, vulns}; a report
    # wrapped in an object is what `--fix` produces, so both shapes are read rather than one
    # guessed at. `vulns` is present and empty for a distribution with nothing reported.
    audited = report if isinstance(report, list) else report.get("dependencies")
    if not isinstance(audited, list) or not audited:
        raise SystemExit(f"FATAL: {path} audits no distribution — an empty report is not a "
                         "clean report, and pip-audit writes one entry per audited package")
    registered = _registered(rows, "PyPI")
    findings: list[str] = []
    for dep in audited:
        for vuln in dep.get("vulns") or []:
            identifiers = ({vuln.get("id", "")} | set(vuln.get("aliases") or [])) - {""}
            if identifiers & registered:
                continue
            fixes = sorted(vuln.get("fix_versions") or [])
            findings.append(f"{dep.get('name')}@{dep.get('version')}")
            print(f"::error::{dep.get('name')}@{dep.get('version')} carries "
                  f"{', '.join(sorted(identifiers))} and no register row decides it "
                  f"(fixed in {', '.join(fixes) or 'no release'})")
    print(f"\n{sum(len(d.get('vulns') or []) for d in audited)} finding(s) across "
          f"{len(audited)} audited distribution(s); {len(findings)} undecided.")
    if findings:
        print("Add a line to .github/advisories-ignore.txt with the exposure you measured, "
              "or move the package: an advisory nobody wrote down is the state this register "
              "exists to end.")
        return 1
    return 0


def _audit_pnpm_report(path: Path, rows: list[dict[str, str]]) -> int:
    """Judge `pnpm audit --json` by the register, the JS half of the same chain.

    The JS audit already errors on an advisory reachable from a runtime dependency, and an
    annotation does not stop a job: the step is soft, so the finding it names still ships
    while the run stays green. This reads the same report and fails on an advisory the
    register does not carry, whatever its scope.
    """
    if not path.is_file():
        raise SystemExit(f"FATAL: {path} is missing — the JS audit wrote no report to judge")
    try:
        report = json.loads(path.read_text(encoding="utf-8") or "")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {path} is not the JSON `pnpm audit --json` writes: {exc}") from exc
    advisories = report.get("advisories")
    if not isinstance(advisories, dict):
        # An audit that answers nothing is not an empty audit: `pnpm audit` writes this key on
        # every run that reached the registry, so a missing key means the route failed.
        raise SystemExit(f"FATAL: {path} carries no `advisories` object — the registry "
                         "route produced no verdict, and an absence is not a clean result")
    registered = _registered(rows, "npm")
    findings: list[str] = []
    for key, advisory in sorted(advisories.items()):
        identifiers = {advisory.get("github_advisory_id", "")} | set(advisory.get("cves") or [])
        identifiers -= {""}
        if identifiers & registered:
            continue
        name = advisory.get("module_name") or key
        findings.append(f"{name}: {sorted(identifiers) or [key]}")
        print(f"::error::npm advisory {', '.join(sorted(identifiers)) or key} on {name} "
              f"({advisory.get('severity')}, vulnerable {advisory.get('vulnerable_versions')}, "
              f"patched {advisory.get('patched_versions')}) is in no register row")
    print(f"\n{len(advisories)} npm advisory record(s); {len(findings)} with no written decision.")
    if findings:
        print("Add a line to .github/advisories-ignore.txt with ecosystem=npm and the scope you "
              "measured, or move the dependency: a dev-only advisory ships nowhere, a runtime "
              "one ships to the user.")
        return 1
    return 0
