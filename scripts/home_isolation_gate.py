#!/usr/bin/env python3
"""Home-isolation gate: the measuring instrument's ratchet logic, wired to a baseline.

Guard rule 2026-10-08: no test may write into the developer's real ``~/.ephe``.
``tests/test_home_isolation.py`` installs an in-process tripwire that detects such a
write; this module decides what a detection *means*: an already-recorded offender is
tolerated and counted, a new offender fails, and the committed baseline may only ever
shrink.

The policy is copied from the two ratchets this repository already ships —
``scripts/architecture_check.mjs`` (``.architecture-baseline.json``) and
``scripts/language_gate.py`` (``scripts/language-baseline.json``): recorded findings are
tolerated, growth anywhere is a regression even when the total falls, and the update
mode refuses to raise the number. The reason a *total* is not enough is the same here:
one worker makes a suite hermetic while another leaks into the home from a new file, and
only the per-offender comparison names the offender that regressed.

An offender is identified by a stable pytest test id (``tests/<file>::<test>``), never by
an absolute home path — an absolute path is different on every machine and could be
padded to hide growth. ``load_baseline`` refuses every shape that would let the number
lie: an unknown (whitelist-shaped) key, an absolute path, a path outside ``tests/``, or a
count that is not a non-negative integer.

Only the pure decision logic lives here; the measurement itself is a full-suite
run that the guard records into a report. ``main`` reads that report and either checks it
against the committed baseline or, with ``--update``, lowers the baseline to it.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DEFAULT = REPO_ROOT / "tests" / "home-isolation-baseline.json"
POLICY = "home-isolation-ratchet"
VERSION = 1
#: The only keys a baseline may carry. An unknown key is refused rather than ignored:
#: the shape of a whitelist is exactly what must not be added here.
BASELINE_KEYS = {"policy", "version", "instrument", "total", "offenders"}

#: Every offender key must be a test id under ``tests/``. Anything else (an absolute
#: home path, a bare path, an exemption entry) is refused so it cannot hide growth.
OFFENDER_PREFIX = "tests/"

UPDATE_HINT = f"python3 scripts/{Path(__file__).name} --update"


class GateError(Exception):
    """The gate cannot say anything trustworthy — exit 2, not exit 1."""


def is_offender_key(rel: object) -> bool:
    """True when ``rel`` is a stable, repo-relative pytest test id (never a home path)."""
    return isinstance(rel, str) and rel.startswith(OFFENDER_PREFIX) and not Path(rel).is_absolute()


def load_baseline(path: Path) -> dict[str, int]:
    """Read a committed baseline and refuse any shape that could hide growth."""
    if not path.exists():
        raise GateError(
            f"no baseline at {path.name} (looked in {path.parent}); create it with {UPDATE_HINT}"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"baseline {path} cannot be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise GateError(f"baseline {path} must be a JSON object")
    unknown = sorted(set(raw) - BASELINE_KEYS)
    if unknown:
        raise GateError(
            f"baseline {path} carries unknown key(s) {', '.join(unknown)}. This gate has no "
            "exemption list — remove the key, or lower the baseline with --update."
        )
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise GateError(
            f"baseline {path} is policy {raw.get('policy')!r} version {raw.get('version')!r}; "
            f"this gate speaks {POLICY!r} version {VERSION}"
        )
    offenders = raw.get("offenders")
    if not isinstance(offenders, dict):
        raise GateError(f"baseline {path} has no `offenders` mapping")
    clean: dict[str, int] = {}
    for rel, hits in offenders.items():
        if not is_offender_key(rel):
            raise GateError(
                f"baseline {path} records {rel!r}, which is not a repo-relative test id "
                f"(must start with {OFFENDER_PREFIX!r} and not be an absolute path). Offenders "
                "are named by the test that leaks, never by its home path — an absolute path "
                "differs per machine and could be padded to hide growth."
            )
        if isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
            raise GateError(f"baseline {path} entry {rel!r} is not a non-negative violation count")
        clean[rel] = hits
    return clean


def evaluate(baseline: dict[str, int], measured: dict[str, int]) -> dict[str, object]:
    """Compare two per-offender counts. Growth anywhere is a regression, even total-down."""
    regressions = []
    lowered = []
    for rel in sorted(set(baseline) | set(measured)):
        old, new = baseline.get(rel, 0), measured.get(rel, 0)
        if new > old:
            regressions.append((rel, old, new))
        elif new < old:
            lowered.append((rel, old, new))
    return {
        "regressions": regressions,
        "lowered": lowered,
        "baseline_total": sum(baseline.values()),
        "measured_total": sum(measured.values()),
        "measured_offenders": len([c for c in measured.values() if c]),
    }


def report(result: dict[str, object]) -> tuple[int, list[str]]:
    """The operator's text, and the exit code: 1 on growth, 0 otherwise."""
    regressions = result["regressions"]
    lowered = result["lowered"]
    total = result["measured_total"]
    lines: list[str] = []
    if regressions:
        grew = sum(new - old for _, old, new in regressions)
        lines.append(
            f"home-isolation gate: FAIL — tests wrote into the real home in "
            f"{len(regressions)} offender(s) beyond baseline (+{grew} writes)"
        )
        for rel, old, new in regressions:
            lines.append(f"  {rel}: {old} -> {new} (+{new - old})")
        lines.append(f"  total {result['baseline_total']} -> {total} writes")
        lines.append(
            f"Isolate the write (work root / EPHE_CONFIG_DIR in a tmp dir). Do not run "
            f"`{UPDATE_HINT}` to cover it — --update only ever lowers this baseline."
        )
        return 1, lines
    if lowered:
        lines.append("home-isolation gate: PASS — no offender grew past the baseline")
        lines.append(
            f"  total {result['baseline_total']} -> {total} writes "
            f"({result['measured_offenders']} offender(s) still leak)"
        )
        lines.append(
            f"  {len(lowered)} offender(s) sit below their baseline entry: the baseline "
            "can be lowered"
        )
        lines.append(f"  {UPDATE_HINT}")
        return 0, lines
    lines.append("home-isolation gate: PASS — the tree matches the baseline")
    lines.append(f"  total {total} writes over {result['measured_offenders']} offenders")
    return 0, lines


def write_baseline(path: Path, measured: dict[str, int]) -> None:
    """Freeze a measurement. Sorted keys, no timestamp: the file must diff cleanly."""
    payload = {
        "policy": POLICY,
        "version": VERSION,
        "instrument": "tests/test_home_isolation.py",
        "total": sum(measured.values()),
        "offenders": measured,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_baseline(path: Path, measured: dict[str, int]) -> int:
    """Tighten the baseline to the current tree — never loosen it."""
    if not path.exists():
        write_baseline(path, measured)
        print(
            f"home-isolation gate: baseline created — {sum(measured.values())} tolerated "
            f"writes over {len(measured)} offenders ({path.name})"
        )
        return 0
    before = load_baseline(path)
    higher = [
        (rel, before[rel], measured[rel])
        for rel in measured
        if measured[rel] > before.get(rel, 0)
    ]
    if higher:
        print(
            f"home-isolation gate: FAIL — baseline was not written; --update only lowers it "
            f"({len(higher)} offender(s) would rise)",
            file=sys.stderr,
        )
        for rel, old, new in sorted(higher):
            print(f"  {rel}: {old} -> {new} (+{new - old})", file=sys.stderr)
        print(
            f"  isolate those writes first, then run {UPDATE_HINT} again",
            file=sys.stderr,
        )
        return 1
    write_baseline(path, measured)
    freed = len(set(before) - set(measured))
    dropped = sum(before.values()) - sum(measured.values())
    print(
        f"home-isolation gate: baseline lowered — {sum(before.values())} -> "
        f"{sum(measured.values())} tolerated writes ({dropped} fewer, {freed} offender(s) "
        "now clean)"
    )
    return 0


def main(
    argv: list[str] | None = None,
    *,
    read_measured: Callable[[], dict[str, int]] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT, help="committed baseline")
    parser.add_argument(
        "--report", type=Path, default=None,
        help="offender report JSON recorded by a guarded suite run (EPHE_HOME_ISOLATION_REPORT)",
    )
    parser.add_argument(
        "--update", action="store_true",
        help="lower the baseline to the recorded report (refuses to raise it)",
    )
    args = parser.parse_args(argv)
    try:
        if read_measured is not None:
            measured = read_measured()
        else:
            if args.report is None:
                raise GateError(
                    "no --report given: run the suite once with EPHE_HOME_ISOLATION_REPORT set "
                    "so the guard records the offenders, then point --report at that file"
                )
            measured = json.loads(args.report.read_text(encoding="utf-8"))
        if args.update:
            return update_baseline(args.baseline, measured)
        result = evaluate(load_baseline(args.baseline), measured)
    except GateError as exc:
        print(f"home-isolation gate: ERROR — {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"home-isolation gate: ERROR — {exc}", file=sys.stderr)
        return 2
    code, lines = report(result)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
