#!/usr/bin/env python3
"""Freeze the CI gates' verdicts before a wave, then attribute the reds after it.

A wave lands many commits at once, and the repository's gates (`architecture`, `language`,
`prose`) can already be red when it starts -- a file another strand owns, a ratchet line another
package moved. The post-wave run cannot tell that red from a red the wave wrote, and
`docs/DECISIONS_2026-10-10.md` records a day when both kinds stood side by side and were argued
about by hand.

`freeze` runs each gate and writes its verdict to a snapshot file. `attribute` runs the gates
again and reads the two verdicts side by side: `fail -> fail` is pre-existing and is named as the
baseline's, `pass -> fail` is a regression and is named as the wave's, and a gate that reached no
verdict on either run is reported as such rather than guessed at.

`attribute` exits 0 when no gate regressed -- a pre-existing red does not refuse, which is the
whole point of freezing first -- 1 when a gate regressed, and 3 when a gate reached no verdict,
because a check that cannot decide has told nobody anything and wins over a red one. That is the
ladder `scripts/ci_local.sh` already uses for a commit. `freeze` always exits 0 once it has
written the snapshot: freezing a red tree is what it is for.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DEFAULT = REPO_ROOT / "out" / "gate-baseline.json"

POLICY = "gate-verdict-baseline"
VERSION = 1
INSTRUMENT = "scripts/gate_baseline.py"
FREEZE_HINT = f"python3 {INSTRUMENT} freeze --out {SNAPSHOT_DEFAULT.relative_to(REPO_ROOT)}"

PASS = "pass"
FAIL = "fail"
UNDECIDED = "undecided"
VERDICTS = (PASS, FAIL, UNDECIDED)

GREEN = "green"
PRE_EXISTING = "pre-existing"
REGRESSED = "regressed"
RECOVERED = "recovered"

#: The gates a wave is judged by on every commit, in the order `CONTRIBUTING.md` names them.
DEFAULT_GATES: tuple[dict[str, object], ...] = (
    {"name": "architecture", "command": ["node", "scripts/architecture_check.mjs", "check"]},
    {"name": "language", "command": ["python3", "scripts/language_gate.py"]},
    {"name": "prose", "command": ["python3", "scripts/prose_tells.py", "--strict"]},
)


class GateError(Exception):
    """A snapshot or a gate list that cannot be trusted, so nothing may be attributed from it."""


def verdict_of(code: int) -> str:
    """The verdict a gate's exit status reached, on the ladder `ci_local.sh` uses.

    0 is a pass and 1 is a reached failing verdict. 2 is the "could not read its inputs" code the
    repository's instruments return (`language_gate.py`, `prose_tells.py`, `tauri_parity.py`), and
    128+N is a signal death; both are no verdict. Every other non-zero code is a refusal the gate
    did reach -- a usage error counts, because a check carrying a code its policy does not know is
    refused rather than excused.
    """
    if code == 0:
        return PASS
    if code == 1:
        return FAIL
    if code == 2 or code >= 128:
        return UNDECIDED
    return FAIL


def classify(before: str, after: str) -> str:
    """Which side a gate's move belongs to, given its frozen and current verdict."""
    if UNDECIDED in (before, after):
        return UNDECIDED
    if before == FAIL and after == PASS:
        return RECOVERED
    if before == FAIL:
        return PRE_EXISTING
    if after == FAIL:
        return REGRESSED
    return GREEN


def run_gate(command: list[str], root: Path, timeout: float) -> tuple[str, int | None]:
    """Run one gate and return its verdict and the status it came from.

    A gate that never exits -- a killed instrument, a command not on PATH, a hang past `timeout` --
    reaches no verdict, and the status is `None` so the caller can say that rather than invent a
    pass.
    """
    try:
        done = subprocess.run(
            command, cwd=str(root), capture_output=True, text=True,
            timeout=timeout or None, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return UNDECIDED, None
    return verdict_of(done.returncode), done.returncode


def run_all(
    gates: list[dict[str, object]], root: Path, timeout: float
) -> dict[str, tuple[str, int | None]]:
    """Every gate's verdict and status, keyed by name, in the registry's order."""
    results: dict[str, tuple[str, int | None]] = {}
    for gate in gates:
        name = str(gate["name"])
        command = [str(part) for part in gate["command"]]  # type: ignore[union-attr]
        results[name] = run_gate(command, root, timeout)
    return results


def check_gate(entry: object, source: str) -> dict[str, object]:
    """One gate from a gates file, refused unless it names a command this helper can run."""
    if not isinstance(entry, dict):
        raise GateError(f"{source}: each gate must be an object")
    name = entry.get("name")
    command = entry.get("command")
    if not isinstance(name, str) or not name:
        raise GateError(f"{source}: a gate entry has no `name`")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise GateError(f"{source}: gate {name!r} has no `command` list of non-empty strings")
    return {"name": name, "command": list(command)}


def load_gates(path: Path | None) -> list[dict[str, object]]:
    """The gate registry: the built-in trio, or a gates file that overrides it wholesale."""
    if path is None:
        return [dict(gate) for gate in DEFAULT_GATES]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"gates file {path} cannot be read: {exc}") from exc
    entries = raw.get("gates") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not entries:
        raise GateError(f"gates file {path} must hold a non-empty list under `gates`")
    return [check_gate(entry, str(path)) for entry in entries]


def head_of(root: Path) -> str | None:
    """The commit the snapshot was frozen at, so a later run can say what it is compared against."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip() or None


def snapshot_payload(
    verdicts: dict[str, str], head: str | None, label: str | None
) -> dict[str, object]:
    """The frozen file's shape. A timestamp and a commit are provenance here, not a diff hazard:
    the snapshot is a point in time, and attribution needs to know which one."""
    return {
        "policy": POLICY,
        "version": VERSION,
        "instrument": INSTRUMENT,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": head,
        "label": label,
        "gates": dict(verdicts),
    }


def write_snapshot(path: Path, data: dict[str, object]) -> None:
    """Atomic `tmp -> replace`, so a reader never sees half a snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_snapshot(path: Path) -> dict[str, object]:
    """Read a frozen snapshot, refusing any shape that could hide a verdict from the comparison."""
    if not path.exists():
        raise GateError(f"no snapshot at {path}; freeze one before the wave with `{FREEZE_HINT}`")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"snapshot {path} cannot be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise GateError(f"snapshot {path} must be a JSON object")
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise GateError(
            f"snapshot {path} is policy {raw.get('policy')!r} version {raw.get('version')!r}; "
            f"this helper speaks {POLICY!r} version {VERSION}"
        )
    gates = raw.get("gates")
    if not isinstance(gates, dict) or not gates:
        raise GateError(f"snapshot {path} has no `gates` mapping")
    for name, verdict in gates.items():
        if not isinstance(name, str) or verdict not in VERDICTS:
            raise GateError(f"snapshot {path} entry {name!r} is not one of {VERDICTS}")
    return raw


def compare(
    frozen: dict[str, str], current: dict[str, tuple[str, int | None]]
) -> tuple[dict[str, str], list[str], list[str]]:
    """Classify every gate both runs carried, and name the ones only one of them had.

    A gate present on one side only has nothing to compare, so it is reported uncompared rather
    than folded into a class -- never silently green, and never a regression the wave did not make.
    """
    classes = {name: classify(frozen[name], current[name][0]) for name in frozen if name in current}
    added = sorted(set(current) - set(frozen))
    dropped = sorted(set(frozen) - set(current))
    return classes, added, dropped


def cmd_freeze(args: argparse.Namespace, gates: list[dict[str, object]]) -> int:
    results = run_all(gates, args.root, args.timeout)
    for name, (verdict, code) in results.items():
        shown = "no exit" if code is None else f"exit {code}"
        print(f"gate-baseline: {name} {verdict} ({shown})")
    verdicts = {name: verdict for name, (verdict, _code) in results.items()}
    data = snapshot_payload(verdicts, head_of(args.root), args.label)
    write_snapshot(args.out, data)
    print(
        f"gate-baseline: froze {len(verdicts)} verdict(s) to {args.out} "
        f"(head {data['head'] or 'unknown'}, label {args.label or 'none'})"
    )
    if any(verdict == UNDECIDED for verdict in verdicts.values()):
        print("gate-baseline: WARNING — a gate reached no verdict; the snapshot records that, not a pass")
    return 0


def cmd_attribute(args: argparse.Namespace, gates: list[dict[str, object]]) -> int:
    frozen = load_snapshot(args.baseline)
    frozen_gates = frozen["gates"]
    assert isinstance(frozen_gates, dict)
    current = run_all(gates, args.root, args.timeout)
    classes, added, dropped = compare(frozen_gates, current)

    lines = [
        f"gate-baseline: compared against the snapshot frozen {frozen.get('created')} "
        f"(head {frozen.get('head') or 'unknown'}, label {frozen.get('label') or 'none'})"
    ]
    for name in sorted(classes):
        before = frozen_gates[name]
        after = current[name][0]
        move = f"{before} -> {after}"
        cls = classes[name]
        if cls == PRE_EXISTING:
            lines.append(f"gate-baseline: pre-existing {name}: {move} (the baseline's red, not this wave)")
        elif cls == REGRESSED:
            lines.append(f"gate-baseline: REGRESSED {name}: {move} (this wave)")
        elif cls == RECOVERED:
            lines.append(f"gate-baseline: recovered {name}: {move}")
        elif cls == UNDECIDED:
            lines.append(f"gate-baseline: NO VERDICT {name}: {move} (a gate that did not decide is unattributable)")
        else:
            lines.append(f"gate-baseline: green {name}: {move}")
    for name in added:
        lines.append(f"gate-baseline: uncompared {name}: not in the snapshot (added after the freeze)")
    for name in dropped:
        lines.append(f"gate-baseline: uncompared {name}: the snapshot carries it, this run does not")

    counts = Counter(classes.values())
    lines.append(
        f"gate-baseline: attribution — {counts[REGRESSED]} regressed, {counts[PRE_EXISTING]} "
        f"pre-existing, {counts[RECOVERED]} recovered, {counts[UNDECIDED]} undecided, "
        f"{counts[GREEN]} green"
    )
    if counts[UNDECIDED]:
        lines.append("gate-baseline: NO VERDICT — a gate reached no verdict, so nothing it guards is attributed")
    elif counts[REGRESSED]:
        lines.append(f"gate-baseline: FAIL — {counts[REGRESSED]} gate(s) regressed against the frozen snapshot")
    else:
        lines.append(
            f"gate-baseline: pass — no gate regressed; {counts[PRE_EXISTING]} pre-existing red(s) "
            "stay the baseline's"
        )
    print("\n".join(lines))
    if counts[UNDECIDED]:
        return 3
    if counts[REGRESSED]:
        return 1
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    frozen = load_snapshot(args.baseline)
    frozen_gates = frozen["gates"]
    assert isinstance(frozen_gates, dict)
    print(
        f"gate-baseline: snapshot {args.baseline} frozen {frozen.get('created')} "
        f"(head {frozen.get('head') or 'unknown'}, label {frozen.get('label') or 'none'})"
    )
    for name, verdict in frozen_gates.items():
        print(f"  {name:<16} {verdict}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    subs = parser.add_subparsers(dest="cmd", required=True)

    freeze = subs.add_parser("freeze", help="run the gates and write their verdicts to a snapshot")
    freeze.add_argument("--out", type=Path, default=SNAPSHOT_DEFAULT, help="snapshot to write")
    freeze.add_argument("--label", default=None, help="the wave this snapshot precedes")

    attribute = subs.add_parser("attribute", help="run the gates and attribute each move to a side")
    attribute.add_argument("--baseline", type=Path, default=SNAPSHOT_DEFAULT, help="frozen snapshot")

    show = subs.add_parser("show", help="print a frozen snapshot without running the gates")
    show.add_argument("--baseline", type=Path, default=SNAPSHOT_DEFAULT, help="frozen snapshot")

    for sub in (freeze, attribute):
        sub.add_argument("--gates-file", type=Path, default=None, help="override the gate registry")
        sub.add_argument("--root", type=Path, default=REPO_ROOT, help="tree the gates run in")
        sub.add_argument("--timeout", type=float, default=900.0, help="seconds one gate may run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "show":
            return cmd_show(args)
        gates = load_gates(args.gates_file)
        if args.cmd == "freeze":
            return cmd_freeze(args, gates)
        return cmd_attribute(args, gates)
    except GateError as exc:
        print(f"gate-baseline: ERROR — {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"gate-baseline: ERROR — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
