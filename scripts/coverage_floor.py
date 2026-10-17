#!/usr/bin/env python3
"""Coverage floor per module: the measuring instrument, wired to a committed baseline.

The Python suite is measured in CI (`coverage.py --cov-report=json`). A run reports
one number per file; nothing stops the next commit from dropping a package a few
points while the *total* still reads green, because a total hides the module that
regressed. This script reads the report, groups it into modules, and compares each
module against a committed floor in `scripts/coverage-floor-baseline.json` — so a
test that stops covering a package is named, not averaged away.

Per module, exactly like the prose ratchet is per file. `prose-tells-baseline.json`
carries one count per file and only ever lowers; this baseline carries one floor per
module and only ever rises. The direction is inverted because more coverage is
better: `--update` raises a floor to what the tree now measures and refuses to lower
it, so a failing tree cannot be made to pass by re-measuring it.

The floor is a whole percent, floored from the measured value (82.9% -> 82). The
rounding is the point: it leaves under a point of slack under every floor, so a
snapshot taken while the tree was being edited cannot pin a module above what an
idle run measures. A module's coverage is the statement-weighted rate over its
files (`sum(covered) / sum(statements)`); the mean of the file rates would weigh
a 100-line file the same as a 3-line `__init__`.

There is no exemption list. A module may not appear in the baseline unless the
report holds it (an entry for a module the tree no longer carries is an allowance
for whoever recreates it), and the only keys a baseline may hold are the five the
instrument writes. Anything else — an `exempt` key, an ignored path, a floor above
100 — is refused rather than ignored, because each would silently make the number
lie.

Exit codes: 0 no module fell below its floor, 1 a module did (the modules are
named), 2 the gate cannot be trusted (missing or malformed baseline or report, an
entry for a module the report no longer holds).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DEFAULT = Path(__file__).resolve().parent / "coverage-floor-baseline.json"
POLICY = "coverage-floor-ratchet"
VERSION = 1
INSTRUMENT = "coverage.py --cov-report=json"
#: The only keys a baseline may carry. An unknown key is refused rather than
#: ignored: the shape of a whitelist is exactly what must not be added here.
BASELINE_KEYS = {"policy", "version", "instrument", "total", "modules"}
#: The report path `coverage.py --cov-report=json:...` writes by default.
REPORT_DEFAULT = REPO_ROOT / "coverage.json"

UPDATE_HINT = f"python3 scripts/{Path(__file__).name} --update"


class GateError(Exception):
    """An untrustworthy gate exits 2; a refusal that means something exits 1."""


def module_of(rel: str) -> str:
    """The module a file belongs to, at the same depth the prose census groups.

    `core/chat.py` -> `core`; `core/tools/registry.py` -> `core/tools`;
    `ephe_cli.py` -> `ephe_cli.py`. Two levels keep a top-level module together
    while splitting a package big enough that one floor would hide a regressed
    subpackage.
    """
    parts = Path(rel).parts
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def validated_report(raw: object, *, where: str = "report") -> dict:
    """Reject a report body that could hide a drop, whether read from disk or injected."""
    if not isinstance(raw, dict):
        raise GateError(f"{where} must be a JSON object")
    files = raw.get("files")
    if not isinstance(files, dict) or not files:
        raise GateError(f"{where} has no `files` mapping; run coverage over the package")
    return raw


def read_report(path: Path) -> dict:
    """Load a coverage.py JSON report. A shape that could hide a drop is refused."""
    if not path.exists():
        raise GateError(
            f"no coverage report at {path}; produce one with "
            f"`python3 -m coverage run -m pytest && python3 -m coverage json -o {path.name}`"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"report {path} cannot be read: {exc}") from exc
    return validated_report(raw, where=f"report {path}")


def measure(report: dict) -> dict[str, tuple[int, int]]:
    """Covered and total statements per module, summed over the module's files.

    Injectable report body, so a fixture scores through the same path the CI leg
    does. A file whose `summary` is missing the two counts is refused: a report
    that half-answers would score that file as zero covered, which reads as a
    regression the source never produced.
    """
    agg: dict[str, list[int]] = {}
    for rel, info in report["files"].items():
        if not isinstance(rel, str) or not isinstance(info, dict):
            raise GateError(f"report entry {rel!r} is not a file object")
        summary = info.get("summary")
        if not isinstance(summary, dict):
            raise GateError(f"report entry {rel!r} has no `summary`")
        covered = summary.get("covered_lines")
        statements = summary.get("num_statements")
        if isinstance(covered, bool) or not isinstance(covered, int) or covered < 0:
            raise GateError(f"report entry {rel!r} has a non-integer covered_lines")
        if isinstance(statements, bool) or not isinstance(statements, int) or statements < 0:
            raise GateError(f"report entry {rel!r} has a non-integer num_statements")
        if covered > statements:
            raise GateError(f"report entry {rel!r} covers more lines than it holds")
        cell = agg.setdefault(module_of(rel), [0, 0])
        cell[0] += covered
        cell[1] += statements
    return {module: (covered, statements) for module, (covered, statements) in agg.items()}


def percents(measured: dict[str, tuple[int, int]]) -> dict[str, float]:
    """Statement-weighted coverage rate per module. A module with no statements is full."""
    return {
        module: (100.0 * covered / statements if statements else 100.0)
        for module, (covered, statements) in measured.items()
    }


def floors(percent: dict[str, float]) -> dict[str, int]:
    """The whole-percent floor a measurement earns: floored, never rounded up."""
    return {module: math.floor(rate) for module, rate in percent.items()}


def total_floor(measured: dict[str, tuple[int, int]]) -> int:
    """The whole-percent floor over every module together, for the report line only."""
    covered = sum(c for c, _ in measured.values())
    statements = sum(s for _, s in measured.values())
    return math.floor(100.0 * covered / statements) if statements else 100


class Verdict(TypedDict):
    """The comparison's shape, typed so `report` iterates lists rather than `object`."""

    regressions: list[tuple[str, int, int]]
    room: list[tuple[str, int, int]]
    baseline_total: int
    measured_total: int
    measured_modules: int


def evaluate(
    baseline: dict[str, int],
    measured_floors: dict[str, int],
    *,
    baseline_total: int = 0,
    measured_total: int = 0,
) -> Verdict:
    """Compare two per-module floors. A drop in any module is a regression, even if the total rose."""
    regressions: list[tuple[str, int, int]] = []
    room: list[tuple[str, int, int]] = []
    for module in sorted(baseline):
        old = baseline[module]
        new = measured_floors.get(module, 0)
        if new < old:
            regressions.append((module, old, new))
        elif new > old:
            room.append((module, old, new))
    return {
        "regressions": regressions,
        "room": room,
        "baseline_total": baseline_total,
        "measured_total": measured_total,
        "measured_modules": len(measured_floors),
    }


def report(result: Verdict) -> tuple[int, list[str]]:
    """The operator's text, and the exit code: 1 on a drop, 0 otherwise."""
    regressions = result["regressions"]
    room = result["room"]
    lines: list[str] = []
    if regressions:
        lines.append(
            f"coverage floor: FAIL — coverage fell below the baseline floor in "
            f"{len(regressions)} module(s)"
        )
        for module, floor, measured in regressions:
            lines.append(f"  {module}: floor {floor}%, measured {measured}%")
        lines.append(f"  total {result['baseline_total']}% -> {result['measured_total']}%")
        lines.append(
            "Add tests for the uncovered lines those modules gained. Do not run "
            f"`{UPDATE_HINT}` to cover them — --update only ever raises this baseline."
        )
        return 1, lines
    if room:
        lines.append("coverage floor: PASS — no module fell below the baseline floor")
        lines.append(
            f"  total {result['baseline_total']}% -> {result['measured_total']}% "
            f"over {result['measured_modules']} module(s)"
        )
        lines.append(
            f"  {len(room)} module(s) sit above their floor: the baseline can be raised"
        )
        lines.append(f"  {UPDATE_HINT}")
        return 0, lines
    lines.append("coverage floor: PASS — the tree matches the baseline")
    lines.append(f"  total {result['measured_total']}% over {result['measured_modules']} module(s)")
    return 0, lines


def load_baseline(path: Path) -> tuple[dict[str, int], int]:
    """Read the coverage baseline; a shape that could hide a drop is refused outright.

    Returns the per-module floors and the recorded total, so the report line can
    name both sides of the move without a second read.
    """
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
            "exemption list — remove the key, or raise the baseline with --update."
        )
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise GateError(
            f"baseline {path} is policy {raw.get('policy')!r} version {raw.get('version')!r}; "
            f"this gate speaks {POLICY!r} version {VERSION}"
        )
    total = raw.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 100:
        raise GateError(f"baseline {path} has no `total` floor between 0 and 100")
    modules = raw.get("modules")
    if not isinstance(modules, dict):
        raise GateError(f"baseline {path} has no `modules` mapping")
    clean: dict[str, int] = {}
    for module, floor in modules.items():
        if not isinstance(module, str) or not module:
            raise GateError(f"baseline {path} entry {module!r} is not a module name")
        if isinstance(floor, bool) or not isinstance(floor, int) or not 0 <= floor <= 100:
            raise GateError(
                f"baseline {path} entry {module!r} is not a floor between 0 and 100"
            )
        clean[module] = floor
    return clean, total


def refuse_orphan_entries(baseline: dict[str, int], measured: dict[str, tuple[int, int]]) -> None:
    """A baseline entry has to name a module the report still holds.

    `evaluate` compares the baseline's modules alone, so an entry for a module the
    report no longer carries would never be judged — it is an allowance for whoever
    recreates the package. Refusing the pass (exit 2, the same verdict as an
    unreadable baseline) forces the entry to be pruned with a real --update.
    """
    absent = sorted(module for module in baseline if module not in measured)
    if absent:
        raise GateError(
            f"baseline names {len(absent)} module(s) the report does not hold: "
            + ", ".join(absent[:5])
            + ("…" if len(absent) > 5 else "")
            + " — prune them with --update; an entry for a vanished module is an allowance "
            "for whoever recreates it"
        )


def write_baseline(path: Path, measured_floors: dict[str, int], total: int) -> None:
    """Freeze a measurement. Sorted keys, no timestamp: the file must diff cleanly."""
    payload = {
        "policy": POLICY,
        "version": VERSION,
        "instrument": INSTRUMENT,
        "total": total,
        "modules": measured_floors,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_baseline(path: Path, measured_floors: dict[str, int], total: int) -> int:
    """Raise the floors to the current tree — never lower them."""
    if not path.exists():
        write_baseline(path, measured_floors, total)
        print(
            f"coverage floor: baseline created — {len(measured_floors)} module(s) at "
            f"{total}% total ({path.name})"
        )
        return 0
    before, _ = load_baseline(path)
    lower = [
        (module, before[module], measured_floors[module])
        for module in measured_floors
        if measured_floors[module] < before.get(module, 0)
    ]
    if lower:
        print(
            f"coverage floor: FAIL — baseline was not written; --update only raises it "
            f"({len(lower)} module(s) would fall)",
            file=sys.stderr,
        )
        for module, old, new in sorted(lower):
            print(f"  {module}: {old}% -> {new}% ({new - old})", file=sys.stderr)
        print(
            "  add tests for those modules first, then run --update again",
            file=sys.stderr,
        )
        return 1
    write_baseline(path, measured_floors, total)
    raised = sum(1 for module in measured_floors if measured_floors[module] > before.get(module, 0))
    seeded = sum(1 for module in measured_floors if module not in before)
    pruned = len(set(before) - set(measured_floors))
    print(
        f"coverage floor: baseline raised — {total}% total "
        f"({raised} module(s) raised, {seeded} new, {pruned} pruned)"
    )
    return 0


def main(
    argv: list[str] | None = None,
    *,
    read_report_fn: Callable[[], dict] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT, help="committed baseline")
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT, help="coverage.py JSON report")
    parser.add_argument(
        "--update", action="store_true",
        help="raise the baseline to the current tree (refuses to lower it)",
    )
    args = parser.parse_args(argv)
    try:
        raw = read_report_fn() if read_report_fn is not None else read_report(args.report)
        measured = measure(validated_report(raw))
        measured_floors = floors(percents(measured))
        total = total_floor(measured)
        if args.update:
            return update_baseline(args.baseline, measured_floors, total)
        baseline, baseline_total = load_baseline(args.baseline)
        refuse_orphan_entries(baseline, measured)
        result = evaluate(
            baseline,
            measured_floors,
            baseline_total=baseline_total,
            measured_total=total,
        )
    except GateError as exc:
        print(f"coverage floor: ERROR — {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"coverage floor: ERROR — {exc}", file=sys.stderr)
        return 2
    code, lines = report(result)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
