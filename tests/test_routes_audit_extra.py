"""server/routes/audit.py — the audit-log surface (R23, WA-4).

The route module had no instrumentation: `count_matching` and the `get_audit`
body were both unexercised. Two contracts carry the coverage here:

- The count is a real count of entries, with the same read rule as `tail`
  (blank and broken lines are not entries), and `kind` filters it. `None` means
  "the file exists but cannot be read" and must not collapse into 0, which a
  surface would read as "the log is empty" (the module docstring says so).
- The route puts the delivered page against `total_matching`, clamps
  `total_limit` to 1..500, and answers 500 with `reason_code=audit_log_unreadable`
  when the log cannot be read instead of an empty list.

`audit.py` binds `AUDIT_LOG_FILE` by `from core.audit_log import ...`, so the
module's own attribute is patched as well as `core.audit_log`'s (the latter for
the `tail` call the route makes).

The later tests close the two edges that first cut left: a page read against a
log larger than one page (the "100 of 120" the route exists to say), and a log
file that exists but holds nothing (0, distinct from the missing-file 0).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _entry(kind: str, tool: str = "shell") -> str:
    return json.dumps({"ts": "2026-10-11T00:00:00.000+00:00", "kind": kind, "tool": tool})


def _numbered(n: int, kind: str = "tool_exec") -> list[str]:
    """`n` entries whose `tool` names its position: t000 oldest ... t{n-1} newest."""
    return [_entry(kind, tool=f"t{i:03d}") for i in range(n)]


@pytest.fixture
def audit(tmp_path, monkeypatch):
    """Point both the route module and core.audit_log at one tmp log file."""
    import core.audit_log as core
    import server.routes.audit as route

    log = tmp_path / "audit.log"
    monkeypatch.setattr(route, "AUDIT_LOG_FILE", log)
    monkeypatch.setattr(core, "AUDIT_LOG_FILE", log)
    return route, log


def test_count_matching_zero_when_file_missing(audit):
    route, _ = audit
    assert route.count_matching() == 0


def test_count_matching_counts_valid_entries(audit):
    route, log = audit
    _write(log, [_entry("tool_exec"), _entry("approval"), _entry("tool_exec")])
    assert route.count_matching() == 3


def test_count_matching_skips_blank_broken_and_non_dict_lines(audit):
    route, log = audit
    _write(
        log,
        [
            _entry("tool_exec"),
            "",
            "   ",
            "{not json",
            "[1, 2, 3]",  # valid JSON array (an entry is an object)
            '"a string"',  # valid JSON string (an entry is an object)
            _entry("approval"),
        ],
    )
    assert route.count_matching() == 2


def test_count_matching_filters_by_kind(audit):
    route, log = audit
    _write(log, [_entry("tool_exec"), _entry("approval"), _entry("tool_exec")])
    assert route.count_matching("tool_exec") == 2
    assert route.count_matching("approval") == 1
    assert route.count_matching("never") == 0


def test_count_matching_unreadable_returns_none(audit):
    route, log = audit
    # A directory exists but cannot be opened as a file: the read rule that
    # "cannot read" must not become 0 lives here.
    log.mkdir()
    assert route.count_matching() is None


@pytest.fixture
def client():
    from server.main import create_app

    return TestClient(create_app())


def test_route_returns_page_and_total(audit, client):
    _, log = audit
    _write(log, [_entry("tool_exec"), _entry("approval"), _entry("tool_exec")])
    r = client.get("/api/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["total_matching"] == 3
    assert body["total_limit"] == 100
    # newest first: the last written entry leads
    assert [e["kind"] for e in body["entries"]] == ["tool_exec", "approval", "tool_exec"]


def test_route_kind_filter_flows_through(audit, client):
    _, log = audit
    _write(log, [_entry("tool_exec"), _entry("approval"), _entry("tool_exec")])
    body = client.get("/api/audit", params={"kind": "approval"}).json()
    assert body["total_matching"] == 1
    assert [e["kind"] for e in body["entries"]] == ["approval"]


@pytest.mark.parametrize("limit,expected", [(1000, 500), (0, 1), (-5, 1), (80, 80)])
def test_route_clamps_total_limit(audit, client, limit, expected):
    body = client.get("/api/audit", params={"limit": limit}).json()
    assert body["total_limit"] == expected


def test_route_unreadable_answers_500_with_reason(audit, client):
    _, log = audit
    log.mkdir()
    r = client.get("/api/audit")
    assert r.status_code == 500
    assert r.json()["error"]["reason_code"] == "audit_log_unreadable"


def test_route_page_is_a_slice_against_the_total(audit, client):
    """GIVEN 120 entries WHEN the default page is read THEN 100 lead and 120 is the total.

    The surface has to be able to say "100 of 120": the page carries the newest
    `limit` entries while `total_matching` counts the whole log. A slice that
    reads like the whole log is exactly what the module docstring warns against,
    and the older test left `total_matching` pinned only for a log that fit one
    page.
    """
    _, log = audit
    _write(log, _numbered(120))
    body = client.get("/api/audit").json()
    assert len(body["entries"]) == 100
    assert body["total_matching"] == 120
    assert body["total_limit"] == 100
    # newest first, and the page is the newest slice (t020..t119), not t000..t099
    assert [e["tool"] for e in body["entries"][:2]] == ["t119", "t118"]
    assert {e["tool"] for e in body["entries"]} == {f"t{i:03d}" for i in range(20, 120)}


def test_route_small_limit_still_reports_the_whole_total(audit, client):
    """GIVEN 120 entries WHEN limit=5 THEN the five newest lead against a total of 120."""
    _, log = audit
    _write(log, _numbered(120))
    body = client.get("/api/audit", params={"limit": 5}).json()
    assert [e["tool"] for e in body["entries"]] == ["t119", "t118", "t117", "t116", "t115"]
    assert body["total_matching"] == 120
    assert body["total_limit"] == 5


def test_route_kind_filter_counts_past_the_page(audit, client):
    """GIVEN 150 tool_exec and 3 approval WHEN each kind is read THEN the total is the whole kind."""
    _, log = audit
    _write(log, _numbered(150) + _numbered(3, kind="approval"))
    tool = client.get("/api/audit", params={"kind": "tool_exec"}).json()
    assert len(tool["entries"]) == 100
    assert tool["total_matching"] == 150
    approval = client.get("/api/audit", params={"kind": "approval"}).json()
    assert len(approval["entries"]) == 3
    assert approval["total_matching"] == 3


def test_count_matching_empty_existing_file_is_zero(audit):
    """GIVEN a log that exists but holds no entry THEN the count is zero.

    The missing-file path (`L27`) already returns 0; this pins the other return,
    the read loop that runs over a file with nothing in it.
    """
    route, log = audit
    _write(log, [])
    assert log.exists()
    assert route.count_matching() == 0


def test_count_matching_skips_json_scalars(audit):
    """GIVEN valid JSON that is not an object (null/number/bool) THEN none counts as an entry.

    The read rule is "an entry is a JSON object". The array and string cases are
    covered above; `null`, a bare number and a bare bool parse cleanly and must
    still be skipped rather than counted.
    """
    route, log = audit
    _write(log, [_entry("tool_exec"), "null", "42", "true", "3.14", _entry("approval")])
    assert route.count_matching() == 2
