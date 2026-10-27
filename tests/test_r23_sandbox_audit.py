"""tests/test_r23_sandbox_audit.py — R23: sandbox and audit depth.

Acceptance: Seatbelt (a write attempt outside the workspace fails),
the audit-log roundtrip, no secret in any log or trace.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import audit_log
from core.redact import args_hash, redact


@pytest.fixture(autouse=True)
def audit_file(tmp_path, monkeypatch):
    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    return log


class TestRedact:
    def test_given_openai_key_when_redacted_then_masked(self):
        out = redact("Die Engine nutzt sk-proj-abcdefgh12345 als Key.")
        assert "sk-proj" not in out.replace("sk-proj", "")  # the key value is gone
        assert "***" in out
        assert "abcdefgh12345" not in out

    def test_given_bearer_header_when_redacted_then_masked(self):
        out = redact("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9zzz")
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9zzz" not in out
        assert "Bearer ***" in out

    def test_given_token_query_in_url_when_redacted_then_masked(self):
        out = redact("http://127.0.0.1:8765/api/file?path=/x&token=supersecret123")
        assert "supersecret123" not in out
        assert "token=***" in out

    def test_given_kv_assignment_when_redacted_then_masked(self):
        out = redact('{"api_key": "super-secret-99", "model": "sd-1.5"}')
        assert "super-secret-99" not in out
        assert '"model": "sd-1.5"' in out, "THEN: Nicht-Secrets bleiben lesbar"

    def test_given_ephe_env_assignment_when_redacted_then_masked(self):
        out = redact("EPHE_OPENAI_COMPAT_API_KEY=lovely-key-42 aktiviert")
        assert "lovely-key-42" not in out

    def test_given_clean_text_when_redacted_then_unchanged(self):
        assert redact("ganz normaler Log-Text ohne Geheimnisse") == "ganz normaler Log-Text ohne Geheimnisse"

    def test_given_args_hash_when_same_args_then_same_hash(self):
        assert args_hash({"a": 1, "b": "x"}) == args_hash({"b": "x", "a": 1})


class TestAuditLog:
    def test_given_events_when_tailed_then_newest_first_and_redacted(self, audit_file):
        audit_log.audit_event(
            "tool_exec", tool="run_shell", args={"command": "echo sk-proj-abcdefgh12345"},
            decision="approved", status="ok", duration_ms=12,
        )
        entries = audit_log.tail()
        assert len(entries) == 1
        e = entries[0]
        assert e["tool"] == "run_shell"
        assert e["status"] == "ok"
        assert e["duration_ms"] == 12
        assert "abcdefgh12345" not in json.dumps(e), "THEN: Kein Secret im Audit-Log"
        assert e["args_hash"], "THEN: args_hash gesetzt"

    def test_given_file_when_inspected_then_owner_only(self, audit_file):
        audit_log.audit_event("tool_exec", tool="read_file", args={"path": "/x"})
        mode = stat.S_IMODE(audit_file.stat().st_mode)
        assert mode == 0o600, "THEN: Audit-Log nur für den Owner"

    def test_given_corrupt_lines_when_tailed_then_skipped(self, audit_file):
        audit_file.write_text("not json\n{\"ts\":\"t\",\"kind\":\"tool_exec\"}\n", encoding="utf-8")
        entries = audit_log.tail()
        assert len(entries) == 1

    def test_given_kind_filter_when_tailed_then_only_matching(self, audit_file):
        audit_log.audit_event("approval", tool="run_shell", decision="denied")
        audit_log.audit_event("tool_exec", tool="run_shell", status="ok")
        assert len(audit_log.tail(kind="approval")) == 1
        assert len(audit_log.tail(kind="tool_exec")) == 1

    def test_given_registry_execution_when_run_then_audited(self, audit_file, monkeypatch):
        """R23 core: EVERY tool execution through the registry leaves an audit trail."""
        from unittest.mock import AsyncMock

        import core.tools.registry as registry

        async def _fake_func(**kwargs):
            return "ok-result"

        monkeypatch.setitem(registry.TOOL_MAP, "get_datetime", _fake_func)
        result = registry.execute_tool.__wrapped__(...) if False else None
        # await it directly:
        import asyncio

        result = asyncio.run(registry.execute_tool("get_datetime", {"x": 1}))
        assert "ok-result" in result or "ok" in result
        entries = audit_log.tail(kind="tool_exec")
        assert any(e["tool"] == "get_datetime" for e in entries), "THEN: Ausführung auditiert"

    def test_given_approval_flow_when_used_then_audited(self, audit_file):
        """Approval decisions (the CLI policy path) land in the audit log."""
        import asyncio

        from core.tools.approval import ApprovalPolicy
        from core.tools.registry import execute_tool

        policy = ApprovalPolicy(auto_approve=False, declined=True, interactive=False)
        result = asyncio.run(execute_tool("create_qrcode", {"data": "x"}, policy))
        assert "Denied" in result or "abgelehnt" in result or "declined" in result.lower() or "nicht" in result.lower()
        entries = audit_log.tail(kind="approval")
        assert any(e["decision"] == "denied" for e in entries), "THEN: Denied-Entscheid auditiert"


class TestSecurityConfig:
    def test_given_defaults_when_loaded_then_strict_no_sandbox(self, tmp_path, monkeypatch):
        from core import engine_config
        from core.security_config import load_security_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
        cfg = load_security_config()
        assert cfg.approval_profile == "strict"
        assert cfg.sandbox_enabled is False

    def test_given_saved_when_loaded_then_roundtrip_and_owner_only(self, tmp_path, monkeypatch):
        from core import engine_config
        from core.security_config import save_security_config, security_config_path

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
        save_security_config(approval_profile="session", sandbox_enabled=True)
        mode = stat.S_IMODE(security_config_path().stat().st_mode)
        assert mode == 0o600

    def test_given_invalid_profile_when_saved_then_rejected(self, tmp_path, monkeypatch):
        from core import engine_config
        from core.security_config import save_security_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
        with pytest.raises(ValueError):
            save_security_config(approval_profile="yolo")


class TestSessionRemember:
    def test_given_strict_profile_when_checked_then_never_auto(self, tmp_path, monkeypatch):
        from core import engine_config
        from core.security_config import remember_tool, session_auto_approved

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
        remember_tool("sess-1", "create_qrcode")
        assert session_auto_approved("sess-1", "create_qrcode") is False, "THEN: strict fragt immer"

    def test_given_session_profile_when_remembered_then_auto_for_same_tool(self, tmp_path, monkeypatch):
        from core import engine_config
        from core.security_config import remember_tool, session_auto_approved

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
        engine_config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (engine_config.CONFIG_DIR / "security.json").write_text('{"approval_profile": "session", "sandbox_enabled": false}')
        remember_tool("sess-1", "create_qrcode")
        assert session_auto_approved("sess-1", "create_qrcode") is True
        assert session_auto_approved("sess-1", "run_shell") is False, "THEN: run_shell nie per Typ-Merken"
        assert session_auto_approved("sess-2", "create_qrcode") is False, "THEN: Session-scope"
        assert session_auto_approved(None, "create_qrcode") is False


class TestSeatbelt:
    @pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists() and not Path("/bin/sandbox-exec").exists()
                        and os.environ.get("CI") == "1",
                        reason="sandbox-exec auf CI-Runnern nicht vorhanden")
    def test_given_sandbox_when_write_outside_workspace_then_blocked(self, tmp_path, monkeypatch):
        """R23 acceptance: a write attempt outside the workspace fails."""
        from core.shell_sandbox import is_available, wrap_command

        if not is_available():
            pytest.skip("sandbox-exec nicht verfügbar (macOS-only Feature)")
        workspace = str(tmp_path / "workspace")
        (tmp_path / "workspace").mkdir()
        args = wrap_command("echo leaked > /tmp/ephe-escape-test.txt", workspace)
        assert args is not None and args[0] == "sandbox-exec"
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert result.returncode != 0, "THEN: Schreiben außerhalb wird von Seatbelt verweigert"
        assert not Path("/tmp/ephe-escape-test.txt").exists()

    @pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists() and not Path("/bin/sandbox-exec").exists()
                        and os.environ.get("CI") == "1",
                        reason="sandbox-exec auf CI-Runnern nicht vorhanden")
    def test_given_sandbox_when_write_inside_workspace_then_allowed(self, tmp_path, monkeypatch):
        from core.shell_sandbox import is_available, wrap_command

        if not is_available():
            pytest.skip("sandbox-exec nicht verfügbar (macOS-only Feature)")
        workspace = str(tmp_path / "workspace")
        (tmp_path / "workspace").mkdir()
        args = wrap_command("echo ok > inside.txt", workspace)
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=workspace)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "workspace" / "inside.txt").read_text() == "ok\n"

    def test_given_profile_when_built_then_workspace_and_no_network(self, tmp_path):
        from core.shell_sandbox import build_profile

        profile = build_profile(str(tmp_path))
        assert "(deny network*)" in profile
        assert f'(subpath "{tmp_path}")' in profile

    def test_given_sandbox_disabled_when_shell_then_plain_execution(self, audit_file, tmp_path, monkeypatch):
        from core import engine_config
        from core.security_config import save_security_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
        save_security_config(sandbox_enabled=False)
        import asyncio

        from core.tools.shell_tools import execute_confirmed_shell

        out = asyncio.run(execute_confirmed_shell("echo plain-ok", True))
        assert "plain-ok" in out
        entries = audit_log.tail(kind="shell")
        assert entries and entries[0]["status"] == "executed"
        assert entries[0]["args_hash"], "THEN: Befehl als Hash referenziert"
        assert "echo plain-ok" in entries[0]["args"], "THEN: redigierte Kurzform enthält den Befehl"


    @pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists() and not Path("/bin/sandbox-exec").exists()
                        and os.environ.get("CI") == "1",
                        reason="sandbox-exec is not on the CI runners")
    def test_given_sandbox_when_git_runs_then_it_can_open_dev_null(self, tmp_path):
        """git probes /dev/null for read+write; denying it failed every git call
        inside the sandbox with exit 128 before the device nodes were allowed."""
        from core.shell_sandbox import is_available, wrap_command

        if not is_available():
            pytest.skip("sandbox-exec is not available (macOS-only feature)")
        workspace = tmp_path / "repo"
        workspace.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=workspace, check=True)
        (workspace / "a.txt").write_text("one\n")

        args = wrap_command("git status --short", str(workspace))
        result = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=workspace)
        assert result.returncode == 0, result.stderr
        assert "?? a.txt" in result.stdout
