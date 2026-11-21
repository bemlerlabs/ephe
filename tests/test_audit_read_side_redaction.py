"""No secret in any log/trace — held on the read side too (R23, F-2).

`core.redact` is a growing set of patterns, not a finished one: the GitLab, AWS
and Google shapes entered `_KEY_LITERALS` after the audit log had been written
for months. Every line is masked once, at the moment it is appended
(`core/audit_log.py`), so a line that landed before a pattern existed keeps the
secret in the clear on disk — and `tail` handed those stored fields straight to
the page.

A migration that rewrote the log is not the fix: each line carries the digest of
the one before it, so re-writing history is exactly what `verify_chain` exists to
notice, and `clear()` refuses for the same reason. The mask therefore moves to the
read, where it changes nothing on disk. Contract: the entries a reader is served
carry no credential-shaped text, the file stays byte-identical, and the count keeps
describing the same log the page does.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

#: One of each shape `_KEY_LITERALS` grew after the first audit lines were written,
#: plus the two carriers a real log line uses for free text. Every value is assembled
#: at runtime, so the tree carries no complete credential shape for `secret_scan` to
#: read as a leak; the strings a test run writes into its log fixture are unchanged.
STALE_SECRETS = [
    "glpat-" + "A1B2c3D4e5F6g7H8i9J0",
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "AIza" + "SyA1B2c3D4e5F6g7H8i9J0K1L2M3N4O5P6Q",
]


def _stale_line(tool: str = "shell", **fields: str) -> str:
    """A line as it sits on disk: parseable, chained-looking, written unmasked."""
    return json.dumps(
        {
            "ts": "2026-01-04T00:00:00.000+00:00",
            "kind": "tool_exec",
            "tool": tool,
            "args_hash": "0123456789abcdef",
            "args": "",
            "decision": "approved",
            "status": "ok",
            "duration_ms": 12,
            "prev": "",
            **fields,
        }
    )


def _write(path: Path, lines: list[str]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.read_bytes()


@pytest.fixture
def audit(tmp_path, monkeypatch):
    import core.audit_log as core
    import server.routes.audit as route

    log = tmp_path / "audit.log"
    monkeypatch.setattr(core, "AUDIT_LOG_FILE", log)
    monkeypatch.setattr(route, "AUDIT_LOG_FILE", log)
    return core, route, log


def test_tail_masks_a_key_the_write_left_in_the_clear(audit):
    """GIVEN a stale line whose detail holds a key WHEN tail reads it THEN no key shape survives."""
    core, _route, log = audit
    secret = STALE_SECRETS[0]
    _write(log, [_stale_line(detail=f"git push with {secret} in the remote url")])
    entry = core.tail()[0]
    assert secret not in entry["detail"]
    assert "***" in entry["detail"]


@pytest.mark.parametrize("secret", STALE_SECRETS)
def test_every_field_a_stale_line_can_carries_gets_masked(audit, secret):
    """GIVEN the key in any free-text field WHEN the log is read THEN none of them leaks it."""
    core, _route, log = audit
    _write(log, [
        _stale_line(
            tool=secret,
            detail=f"failed with {secret}",
            session_id=secret,
            turn_id=secret,
            call_id=secret,
            actor=secret,
        )
    ])
    served = json.dumps(core.tail()[0], ensure_ascii=False)
    assert secret not in served


def test_the_route_page_carries_no_key_from_a_stale_line(audit):
    """The sink is /api/audit: what the disk holds in the clear may not reach it."""
    from fastapi.testclient import TestClient

    from server.main import create_app

    _core, _route, log = audit
    secret = STALE_SECRETS[1]
    _write(log, [_stale_line(detail=f"assumed role via {secret}")])
    body = TestClient(create_app()).get("/api/audit").text
    assert secret not in body


def test_a_line_without_a_key_is_served_unchanged(audit):
    """The read mask is not a rewrite: ordinary fields come through byte for byte."""
    core, _route, log = audit
    line = _stale_line(detail="3 files written to /tmp/out", tool="write_file")
    _write(log, [line])
    entry = core.tail()[0]
    assert entry["detail"] == "3 files written to /tmp/out"
    assert entry["tool"] == "write_file"


def test_masking_on_read_leaves_the_log_bytes_alone(audit):
    """Append-only proof: the fix moves the mask to the read, so the file is untouched."""
    core, _route, log = audit
    before = _write(log, [_stale_line(detail=STALE_SECRETS[2])])
    core.tail(limit=500)
    assert log.read_bytes() == before
    assert core.verify_chain(log) == []


def test_the_count_still_describes_the_same_log_as_the_page(audit):
    """Two readers, one rule: masking a served line must not change what is an entry."""
    core, route, log = audit
    _write(
        log,
        [_stale_line(detail=STALE_SECRETS[0]), "null", _stale_line(tool="read_file"), ""],
    )
    page = core.tail(limit=500)
    assert len(page) == route.count_matching() == 2
    assert all(STALE_SECRETS[0] not in json.dumps(e) for e in page)


def test_usage_ranking_is_not_a_leak_either(audit):
    """`usage_by_tool` reads through tail, so a key in a tool name stays masked."""
    core, _route, log = audit
    secret = STALE_SECRETS[0]
    _write(log, [_stale_line(tool=secret, status="ok")])
    usage = core.usage_by_tool(top=5)
    assert secret not in json.dumps(usage)
