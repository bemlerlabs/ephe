"""Ephe — the audit-log usage counter holds the traps of its own measurement.

`scripts/audit_usage.py` answers "how often is this tool used per 100 turns, and in which kind of
session" from `~/.ephe/audit.log`. The log is not a database: turn events older than the `turn_id`
field carry no key, a crashed turn leaves execs without a turn record, the same tool name can be
measured twice over (executed directly, or dispatched inside `tool_call`), and a small population
prints a rate that cannot carry a decision. Those are the failure modes this file pins, together with
the two cases that must NOT look like errors: a window with zero calls, and a missing log.

Given / When / Then, strictly. Every fixture here is a temporary file; the real log is only ever
opened for reading, which is one of the tests.
"""
from __future__ import annotations

import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO / "scripts" / "audit_usage.py"


def _load_counter():
    spec = importlib.util.spec_from_file_location("audit_usage_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


counter = _load_counter()


def _turn(turn_id: str, skill: str, when: str, *, calls: int = 0, mode: str = "full-access") -> dict:
    return {"ts": when, "kind": "turn", "tool": skill, "turn_id": turn_id,
            "detail": f"mode={mode} tools={calls}", "status": "ok", "duration_ms": 100.0}


def _exec(turn_id: str, tool: str, when: str, *, args: str = "", args_hash: str = "") -> dict:
    return {"ts": when, "kind": "tool_exec", "tool": tool, "turn_id": turn_id,
            "args": args, "args_hash": args_hash or f"h-{tool}", "status": "ok"}


def _log(tmp_path: Path, events: list[dict], *, name: str = "audit.log") -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def _read(path: Path) -> tuple[int, int, list[str]]:
    stat = path.stat()
    return stat.st_size, int(stat.st_mtime), sorted(p.name for p in path.parent.iterdir())


def test_a_turn_event_without_an_id_is_counted_but_never_enters_a_population(tmp_path):
    log = _log(tmp_path, [
        _turn("k1", "api-tester", "2026-10-10T12:00:00+00:00"),
        {"ts": "2026-10-09T12:00:00+00:00", "kind": "turn", "tool": "api-tester",
         "detail": "mode=full-access tools=3"},
    ])
    ledger = counter.Ledger()
    ledger.read(log)

    assert ledger.unattributed_turns == 1
    assert list(ledger.populations(None, None)) == ["whitelisted"]
    assert ledger.populations(None, None)["whitelisted"] == ["k1"]


def test_a_repeated_turn_event_and_a_repeated_execution_are_counted_once(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    events = [
        _turn("k1", "api-tester", when, calls=2),
        _turn("k1", "api-tester", when, calls=2),
        _exec("k1", "tool_search", when),
        _exec("k1", "tool_search", when),
        _exec("k1", "tool_search", "2026-10-10T12:00:05+00:00"),
    ]
    ledger = counter.Ledger()
    ledger.read(_log(tmp_path, events))
    calls, touched = ledger.count(ledger.populations(None, None)["whitelisted"], "tool_search", "any")

    assert ledger.duplicate_turns == 1
    assert ledger.duplicate_execs == 1
    assert (calls, touched) == (2, 1)


def test_the_same_tool_name_under_two_routes_stays_two_measurements(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    events = [
        _turn("k1", "api-tester", when),
        _exec("k1", "read_file", when),
        _exec("k1", "tool_call", when, args='arguments={"path": "a.json"}; name=read_file',
              args_hash="h-target"),
    ]
    ledger = counter.Ledger()
    ledger.read(_log(tmp_path, events))
    turns = ledger.populations(None, None)["whitelisted"]

    assert ledger.count(turns, "read_file", "direct") == (1, 1)
    assert ledger.count(turns, "read_file", "via-tool-call") == (1, 1)
    assert ledger.count(turns, "read_file", "any") == (2, 1)


def test_execs_whose_turn_record_never_arrived_are_reported_not_silently_dropped(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    events = [_turn("k1", "api-tester", when), _exec("crashed-turn", "read_file", when)]
    ledger = counter.Ledger()
    ledger.read(_log(tmp_path, events))
    data = counter.report(ledger, [], None, None)

    assert data["unattributable"]["turn_ids_with_execs_but_no_turn_record"] == 1
    assert sum(e["turns"] for e in data["populations"].values()) == 1


def test_a_window_with_no_calls_of_the_tool_is_a_number_and_not_an_error(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    log = _log(tmp_path, [_turn("k1", "api-tester", when, calls=1), _exec("k1", "read_file", when)])

    assert counter.main(["--log", str(log), "--tools", "tool_search"]) == 0
    data = counter.report(_reload(log), [("tool_search", "any")], None, None)
    entry = data["populations"]["whitelisted"]["tools"]["tool_search@any"]

    assert entry["calls"] == 0
    assert entry["calls_per_100_turns"] == 0.0
    assert entry["turns_with_call_pct"] == 0.0


def test_a_small_population_prints_the_width_of_its_own_interval(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    events = []
    for i in range(48):
        events.append(_turn(f"k{i}", "api-tester", when))
    for i in (3, 17):
        events.append(_exec(f"k{i}", "tool_search", when))
    log = _log(tmp_path, events)

    assert counter.main(["--log", str(log), "--tools", "tool_search"]) == 0
    entry = counter.report(_reload(log), [("tool_search", "any")], None, None)
    tool = entry["populations"]["whitelisted"]["tools"]["tool_search@any"]

    width = 2 * 1.96 / (1 + 1.96 ** 2 / 48) * math.sqrt(
        (2 / 48) * (1 - 2 / 48) / 48 + 1.96 ** 2 / (4 * 48 * 48)) * 100
    assert tool["turns_with_call_pct"] == 4.2
    assert tool["wilson95_width_pts"] == round(width, 1) == 12.8
    assert 48 < counter.MIN_POPULATION


def test_a_missing_log_is_a_precondition_and_a_zero_window_is_a_result(tmp_path):
    assert counter.main(["--log", str(tmp_path / "absent.log")]) == 2

    when = "2026-10-10T12:00:00+00:00"
    empty = _log(tmp_path, [_turn("k1", "api-tester", when)], name="empty.log")
    assert counter.main(["--log", str(empty), "--since", "2027-01-01T00:00"]) == 0


def test_the_reader_writes_nothing_to_the_log_and_creates_no_file(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    log = _log(tmp_path, [_turn("k1", "api-tester", when, calls=1), _exec("k1", "tool_search", when)])
    before = _read(log)

    counter.main(["--log", str(log)])
    counter.main(["--log", str(log), "--json"])

    assert _read(log) == before


def test_the_named_groups_are_the_ones_the_product_ships(tmp_path):
    from core.tools.discovery import FILE_PRIMITIVE_TOOLS, META_TOOL_NAMES

    assert set(counter.GROUPS["meta"]) == set(META_TOOL_NAMES)
    assert set(counter.GROUPS["file-primitives"]) == set(FILE_PRIMITIVE_TOOLS)


def test_an_ask_mode_turn_is_not_counted_as_a_core_array_turn(tmp_path):
    when = "2026-10-10T12:00:00+00:00"
    ledger = counter.Ledger()
    ledger.read(_log(tmp_path, [
        _turn("k1", "", when, mode="ask"),
        _turn("k2", "", when, mode="full-access"),
    ]))

    assert set(ledger.populations(None, None)) == {"ask mode (no array)", "no-skill (CORE array)"}


def test_a_date_only_until_bound_covers_the_whole_local_day(tmp_path):
    log = _log(tmp_path, [
        _turn("early", "api-tester", "2026-10-10T04:00:00+10:00"),
        _turn("late", "api-tester", "2026-10-11T04:00:00+10:00"),
    ])
    ledger = _reload(log)
    data = counter.report(ledger, [], counter._ts("2026-10-10"),
                          counter._ts("2026-10-10", end_of_day=True))

    # 2026-10-11T04:00+10:00 is 20:00 local on the 10th: a midnight bound would have dropped it.
    until = datetime.fromisoformat(data["window"]["until"]).astimezone()
    assert (until.hour, until.minute, until.second) == (23, 59, 59)
    assert until.date().isoformat() == "2026-10-10"
    assert sum(e["turns"] for e in data["populations"].values()) == 1


def _reload(path: Path) -> counter.Ledger:
    ledger = counter.Ledger()
    ledger.read(path)
    return ledger
