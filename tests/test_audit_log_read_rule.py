"""The one read rule every reader of the audit log follows (W4-22).

Wave 3 found the divergence while pinning coverage: the route's `count_matching`
skipped a line of valid JSON that is not an object, and `core.audit_log.tail`
did not. Two readers over one log, two answers — a page that lists a line the
count denies, or, under a `kind`/`turn_id` filter, a page that returns nothing
at all because `entry.get(...)` raised on the first stray scalar and the whole
read fell back to `[]`.

The rule both now hold, stated in the module docstring: an entry is a JSON
object on its own line. A blank line, a line that does not parse, and a line
whose JSON is a scalar or an array are the same to both readers — left out of
the listing and left out of the total. These tests pin it from the `tail` side
and assert the two readers agree; `tests/test_routes_audit_extra.py` pins the
count side.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

#: Lines that are not entries: blank, unparseable, and valid JSON that is not an
#: object. Every one of them parsed cleanly enough to reach the filters below,
#: which is where the old `tail` and `count_matching` parted ways.
NOT_ENTRIES = ["", "   ", "{not json", "[1, 2, 3]", '"a string"', "null", "42", "true", "3.14"]


def _entry(kind: str = "tool_exec", tool: str = "shell", **extra: object) -> str:
    return json.dumps({"ts": "2026-10-11T00:00:00.000+00:00", "kind": kind, "tool": tool, **extra})


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def audit(tmp_path, monkeypatch):
    """One tmp log file, seen by `tail` (core) and `count_matching` (route)."""
    import core.audit_log as core
    import server.routes.audit as route

    log = tmp_path / "audit.log"
    monkeypatch.setattr(core, "AUDIT_LOG_FILE", log)
    monkeypatch.setattr(route, "AUDIT_LOG_FILE", log)
    return core, route, log


def test_tail_returns_only_json_objects(audit):
    core, _route, log = audit
    _write(log, [_entry(tool="a"), *NOT_ENTRIES, _entry(tool="b")])
    entries = core.tail(limit=500)
    assert [e["tool"] for e in entries] == ["b", "a"]
    assert all(isinstance(e, dict) for e in entries)


def test_tail_and_count_agree_over_the_same_log(audit):
    core, route, log = audit
    _write(log, [_entry(tool="a"), *NOT_ENTRIES, _entry(kind="approval", tool="b"), "", _entry(tool="c")])
    listing = core.tail(limit=500)
    assert len(listing) == route.count_matching() == 3


def test_kind_filter_is_not_wiped_by_a_junk_line(audit):
    """GIVEN junk between entries WHEN the page filters by kind THEN the matches survive.

    Before the fix `entry.get("kind")` raised on the first scalar, the outer
    `except` swallowed it, and `tail` answered [] while `count_matching` reported
    the real total: the page and the "N of M" total described different logs.
    """
    core, route, log = audit
    _write(log, [_entry(tool="a"), "[1, 2, 3]", _entry(tool="b"), _entry(kind="approval", tool="x")])
    assert [e["tool"] for e in core.tail(kind="tool_exec")] == ["b", "a"]
    assert route.count_matching("tool_exec") == 2


def test_turn_id_filter_is_not_wiped_by_a_junk_line(audit):
    core, _route, log = audit
    _write(
        log,
        [
            _entry(tool="a", turn_id="T1"),
            "null",
            _entry(tool="b", turn_id="T1"),
            _entry(tool="c", turn_id="T2"),
        ],
    )
    assert [e["tool"] for e in core.tail(turn_id="T1")] == ["b", "a"]


def test_an_empty_object_is_an_entry_for_both(audit):
    """GIVEN a bare {} line THEN both readers count it — the rule is membership in JSON objects."""
    core, route, log = audit
    _write(log, ["{}", _entry(tool="a")])
    assert len(core.tail(limit=500)) == route.count_matching() == 2


def test_route_page_and_total_describe_the_same_log(audit):
    """GIVEN a log with junk WHEN /api/audit is read THEN the page and the total agree."""
    from fastapi.testclient import TestClient

    from server.main import create_app

    _core, _route, log = audit
    _write(log, [_entry(tool="a"), "null", "[9]", _entry(kind="approval", tool="b")])
    body = TestClient(create_app()).get("/api/audit").json()
    assert body["total_matching"] == 2
    assert [e["tool"] for e in body["entries"]] == ["b", "a"]
    assert all(isinstance(e, dict) for e in body["entries"])
