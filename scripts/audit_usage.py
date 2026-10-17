#!/usr/bin/env python3
"""Read-only counter for tool use per 100 turns, split by session type.

The product audit log keys every tool execution to a turn, and the turn event names the skill that
was active, so a session's array type and its tool use are readable without a session id:
`kind=turn` carries `tool=<skill name>` and `detail="mode=… tools=<calls in the turn>"`, and every
`kind=tool_exec` carries the same `turn_id`. See docs/TOOL_ARRAY_COST_2026-10-10.md §8.

Nothing is ever written to the log: it is opened for reading, and the only outputs are stdout and
the exit code. Exit 2 means the log could not be read, which is a precondition failure, not a
measurement of zero.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

META_GROUP = ("tool_call", "tool_describe", "tool_search")
FILE_PRIMITIVE_GROUP = (
    "read_file", "write_file", "edit_file", "delete_file", "list_directory", "file_search",
)
GROUPS = {"meta": META_GROUP, "file-primitives": FILE_PRIMITIVE_GROUP}

#: A rate over fewer turns than this is printed with its interval and a caution, because at n=48 a
#: 4.2% use rate (2 turns) carries a 95% Wilson interval 12.8 points wide — wider than the decision
#: it would feed. tests/test_audit_usage_counter.py pins that width against the textbook formula.
MIN_POPULATION = 100

_TARGET_RE = re.compile(r"(?:^|[;,\s])name=([A-Za-z0-9_]+)")
_TOOLS_RE = re.compile(r"tools=(\d+)")
_MODE_RE = re.compile(r"mode=(\S+)")


def _ts(raw: str | None, *, end_of_day: bool = False) -> datetime | None:
    """ISO in, aware UTC datetime out. A naive bound means local time, the reader's clock."""
    if not raw:
        return None
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        if end_of_day and len(raw) == 10:
            value = value.replace(hour=23, minute=59, second=59)
        value = value.astimezone()
    return value.astimezone(timezone.utc)


def _parse(line: str) -> dict | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _wilson95_width(successes: int, trials: int, z: float = 1.96) -> float | None:
    """Width of the Wilson score interval, in points of percentage. None when there is no rate."""
    if trials <= 0:
        return None
    p = successes / trials
    z2 = z * z
    denom = 1 + z2 / trials
    centre = (p + z2 / (2 * trials)) / denom
    spread = (z / denom) * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials))
    return 2 * spread * 100


class Ledger:
    """Turn populations and per-tool counts, keyed by session type."""

    def __init__(self) -> None:
        self.turns: dict[str, dict] = {}
        self.execs: dict[str, list[tuple[str, str]]] = {}
        self.unattributed_turns = 0
        self.unattributed_execs = 0
        self.duplicate_turns = 0
        self.duplicate_execs = 0
        self.bad_lines = 0
        self.lines = 0

    def read(self, path: Path) -> None:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                self.lines += 1
                event = _parse(line)
                if event is None:
                    if line.strip():
                        self.bad_lines += 1
                    continue
                kind = event.get("kind")
                if kind == "turn":
                    self._turn(event)
                elif kind == "tool_exec":
                    self._exec(event)

    def _turn(self, event: dict) -> None:
        detail = event.get("detail") or ""
        ts = event.get("ts")
        try:
            when = datetime.fromisoformat(ts).astimezone(timezone.utc) if ts else None
        except (TypeError, ValueError):
            when = None
        turn_id = event.get("turn_id") or ""
        if not turn_id:
            self.unattributed_turns += 1
            return
        mode = _MODE_RE.search(detail)
        tools = _TOOLS_RE.search(detail)
        record = {
            "ts": when,
            "skill": event.get("tool") or "",
            "mode": mode.group(1) if mode else "",
            "calls": int(tools.group(1)) if tools else 0,
        }
        if turn_id in self.turns:
            self.duplicate_turns += 1
            return
        self.turns[turn_id] = record

    def _exec(self, event: dict) -> None:
        turn_id = event.get("turn_id") or ""
        tool = event.get("tool") or ""
        if not turn_id:
            self.unattributed_execs += 1
            return
        target = ""
        if tool == "tool_call":
            match = _TARGET_RE.search(event.get("args") or "")
            target = match.group(1) if match else ""
        key = (turn_id, tool, target, event.get("args_hash") or "", event.get("ts") or "")
        bucket = self.execs.setdefault(turn_id, [])
        if key in bucket:
            self.duplicate_execs += 1
            return
        bucket.append(key)

    def populations(self, since: datetime | None, until: datetime | None) -> dict[str, list[str]]:
        """turn_ids per session type, restricted to the window by the turn's own timestamp."""
        out: dict[str, list[str]] = {}
        for turn_id, record in self.turns.items():
            when = record["ts"]
            if since and (when is None or when < since):
                continue
            if until and (when is None or when > until):
                continue
            out.setdefault(self.session_type(record), []).append(turn_id)
        return out

    @staticmethod
    def session_type(record: dict) -> str:
        if record["skill"]:
            return "whitelisted"
        return "no-skill (CORE array)" if record["mode"] != "ask" else "ask mode (no array)"

    def count(self, turn_ids: list[str], name: str, route: str) -> tuple[int, int]:
        """(calls, turns with at least one call) for one tool over one population."""
        calls = 0
        touched = 0
        for turn_id in turn_ids:
            hit = 0
            for _tid, tool, target, _hash, _ts in self.execs.get(turn_id, []):
                if route == "direct" and tool == name and name != "tool_call":
                    hit += 1
                elif route == "via-tool-call" and tool == "tool_call" and target == name:
                    hit += 1
                elif route == "any" and (tool == name or (tool == "tool_call" and target == name)):
                    hit += 1
            calls += hit
            touched += 1 if hit else 0
        return calls, touched


def _names(values: list[str]) -> list[tuple[str, str]]:
    """Tool names plus their route: a name that appears both top-level and as a tool_call target
    is two different measurements and is never summed."""
    out: list[tuple[str, str]] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if part.startswith("group:"):
                for name in GROUPS.get(part[6:], ()):
                    out.append((name, "any"))
            elif ":" in part:
                name, route = part.split(":", 1)
                out.append((name, route))
            else:
                out.append((part, "any"))
    return out


def report(ledger: Ledger, names: list[tuple[str, str]], since: datetime | None,
           until: datetime | None) -> dict:
    populations = ledger.populations(since, until)
    result = {
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "lines_read": ledger.lines,
        "unattributable": {
            "turn_events_without_turn_id": ledger.unattributed_turns,
            "tool_exec_without_turn_id": ledger.unattributed_execs,
            "turn_ids_with_execs_but_no_turn_record": len(
                {tid for tid in ledger.execs if tid not in ledger.turns}),
            "duplicate_turn_events": ledger.duplicate_turns,
            "duplicate_execs": ledger.duplicate_execs,
            "unparsable_lines": ledger.bad_lines,
        },
        "populations": {},
    }
    for session_type, turn_ids in sorted(populations.items()):
        n = len(turn_ids)
        entry: dict = {"turns": n, "turns_with_any_exec": sum(
            1 for t in turn_ids if ledger.execs.get(t)), "tools": {}}
        for name, route in names:
            calls, touched = ledger.count(turn_ids, name, route)
            rate = 100 * touched / n if n else 0.0
            width = _wilson95_width(touched, n)
            entry["tools"][f"{name}@{route}"] = {
                "calls": calls,
                "calls_per_100_turns": round(100 * calls / n, 1) if n else 0.0,
                "turns_with_call": touched,
                "turns_with_call_pct": round(rate, 1),
                "wilson95_width_pts": round(width, 1) if width is not None else None,
            }
        result["populations"][session_type] = entry
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", default=os.environ.get(
        "EPHE_AUDIT_LOG", str(Path.home() / ".ephe" / "audit.log")))
    ap.add_argument("--since", help="ISO timestamp, naive means local time")
    ap.add_argument("--until", help="ISO timestamp, a date-only value ends at 23:59:59")
    ap.add_argument("--tools", default="group:meta",
                    help="comma-separated names, optional group:meta or group:file-primitives, "
                         "and name:direct|via-tool-call to pin the route")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.log)
    if not path.is_file():
        print(f"[audit-usage] no log at {path} — nothing measured, this is a precondition",
              file=sys.stderr)
        return 2
    ledger = Ledger()
    ledger.read(path)
    names = _names(args.tools.split())
    data = report(ledger, names, _ts(args.since), _ts(args.until, end_of_day=True))

    if args.json:
        print(json.dumps(data, indent=1, sort_keys=True))
        return 0

    window = data["window"]
    print(f"window: {window['since'] or 'oldest'} .. {window['until'] or 'newest'}   "
          f"log: {path} ({data['lines_read']} lines)")
    unatt = data["unattributable"]
    print(f"not attributable to a turn: {unatt['turn_events_without_turn_id']} turn events, "
          f"{unatt['tool_exec_without_turn_id']} tool_exec, "
          f"{unatt['turn_ids_with_execs_but_no_turn_record']} turn_ids with execs but no turn record; "
          f"duplicates dropped: {unatt['duplicate_turn_events']} turns, "
          f"{unatt['duplicate_execs']} execs; unparsable lines: {unatt['unparsable_lines']}")
    if not data["populations"]:
        print("population = 0 turns in this window — no rate exists, this is not a zero result")
        return 0
    for session_type, entry in data["populations"].items():
        n = entry["turns"]
        print(f"\n{session_type}: population = {n} turns, "
              f"{entry['turns_with_any_exec']} of them executed at least one tool")
        width = _wilson95_width(entry["turns_with_any_exec"], n)
        if n < MIN_POPULATION:
            print(f"  CAUTION: n < {MIN_POPULATION}; a rate here carries a 95% interval "
                  f"up to {width:.1f} points wide")
        for key, tool in sorted(entry["tools"].items()):
            print(f"  {key:34} calls={tool['calls']:6} "
                  f"per 100 turns={tool['calls_per_100_turns']:7} "
                  f"turns with call={tool['turns_with_call_pct']:5.1f}% "
                  f"(Wilson width {tool['wilson95_width_pts']} pts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
