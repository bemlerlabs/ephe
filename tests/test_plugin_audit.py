"""AUD-01..04 / GAP-03 — the lifecycle leaves an append-only audit line.

A committed or failed transition carries actor, plugin, scope, the previous and
requested state, version, duration and reason. The log is append-only and the
plugin surface has no write path to it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_lifecycle import PluginLifecycle


def test_lifecycle_audit_fields(tmp_path) -> None:
    audit: list[dict] = []
    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.4.0"},
        audit_sink=audit.append,
    )
    lifecycle.set_enabled("acme-research", False)
    line = audit[-1]
    assert line["action"] == "disable"
    assert line["plugin"] == "acme-research"
    assert line["scope"] == "user"
    assert line["actor"] == "user"
    assert line["previous_state"] == "enabled"
    assert line["requested_state"] == "disabled"
    assert line["state"] == "disabled"
    assert line["version"] == "1.4.0"
    assert line["status"] == "committed"
    assert isinstance(line["duration_ms"], int)
    assert "reason" in line


def test_the_audit_log_is_append_only(tmp_path, monkeypatch) -> None:
    from core import audit_log

    log = tmp_path / "audit.log"
    log.write_text('{"kind": "sentinel"}\n', encoding="utf-8")
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.4.0"},
    )
    lifecycle.set_enabled("acme-research", False)
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["kind"] == "sentinel"
    assert lines[-1]["kind"] == "plugin_lifecycle"
    assert lines[-1]["tool"] == "acme-research"
    assert "scope=user" in lines[-1]["detail"]


def test_the_production_sink_keeps_actor_and_quotes_reason(
    tmp_path, monkeypatch
) -> None:
    from core import audit_log
    from core.plugin_lifecycle_types import _default_audit

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    _default_audit(
        {
            "action": "disable",
            "plugin": "alpha",
            "scope": "user",
            "actor": "admin",
            "previous_state": "enabled",
            "requested_state": "disabled",
            "state": "disabled",
            "version": "1.0.0",
            "duration_ms": 0,
            "reason": "note actor=root approved=yes",
            "status": "committed",
        }
    )
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["actor"] == "admin"
    assert "reason='note actor=root approved=yes'" in row["detail"]


def test_an_existing_wider_audit_log_is_tightened(tmp_path, monkeypatch) -> None:
    import stat

    from core import audit_log

    log = tmp_path / "audit.log"
    log.write_text("", encoding="utf-8")
    log.chmod(0o644)
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    audit_log.audit_event("test")
    assert stat.S_IMODE(log.stat().st_mode) == 0o600


def test_a_plugin_has_no_write_path_to_the_audit_log(tmp_path) -> None:
    import asyncio

    from core.path_guard import denied
    from core.tools.base import FileNotAllowedError
    from core.tools.file_ops import write_file

    production = (Path.home() / ".ephe" / "audit.log").resolve()
    assert denied(production) is True
    with pytest.raises(FileNotAllowedError):
        asyncio.run(write_file(str(production), "tamper"))
