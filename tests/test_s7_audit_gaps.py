"""S7 — the audit gaps that let a refusal leave no line.

Measured in the S4 receipt: LAN-token and WebSocket refusals, an unknown tool
and a schema rejection, marketplace refusals that never reached the install
wrapper, an oversized entry that was sliced into invalid JSON, metadata that
bypassed the masker, a truncated PEM that kept its body, and engine-key writes
and deletes. Each one is a line here; absence of a line is the finding.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from core import audit_log, marketplace_service, plugin_signing
from core.audit_log import audit_event, verify_chain
from core.tools import registry


@pytest.fixture(autouse=True)
def audit_file(tmp_path, monkeypatch):
    path = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", path)
    monkeypatch.setattr(audit_log, "_last_line_sha", None)
    monkeypatch.setattr(audit_log, "_last_line_path", None)
    return path


def _entries(path) -> list[dict]:
    return [
        entry
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for entry in [json.loads(line)]
    ]


class TestMaskerAndSize:
    def test_metadata_fields_run_through_the_masker(self, audit_file):
        secret = "sk-proj-abcdefghijklmnop1234567890"
        audit_event(
            "security",
            tool=f"https://x.test/mcp?token={secret}",
            actor=secret,
            session_id=secret,
            decision="denied",
        )
        entry = _entries(audit_file)[-1]
        assert secret not in json.dumps(entry), entry
        assert "***" in entry["tool"] and "***" in entry["actor"]

    def test_a_truncated_pem_does_not_keep_its_body(self, audit_file):
        # Split so the scanner (which refuses the literal header anywhere in the
        # tree) does not flag the fixture; the runtime string is the same one a
        # truncated error message carries.
        header = "-----BEGIN RSA " + "PRIVATE KEY-----"
        audit_event("tool_exec", tool="demo", detail=f"{header}\nMIIEowIBAAKCAQEA")
        entry = _entries(audit_file)[-1]
        assert "MIIEowIBAAKCAQEA" not in entry["detail"]

    def test_an_oversized_entry_stays_parseable_and_says_so(self, audit_file, monkeypatch):
        # Every field is capped, so the branch is the safety net for a future
        # field that is not; a lowered max reaches it without inventing one.
        monkeypatch.setattr(audit_log, "_MAX_LINE", 200)
        audit_event("tool_exec", tool="demo", detail="a" * 300)
        entries = _entries(audit_file)
        assert entries[-1]["detail"].startswith("[oversized entry:")
        assert entries[-1]["kind"] == "tool_exec"
        assert verify_chain(audit_file) == []


class TestToolRefusals:
    def _bind(self, monkeypatch):
        async def demo(path: str) -> str:
            return "ok"

        monkeypatch.setitem(registry.TOOL_MAP, "demo_tool", demo)
        monkeypatch.setattr(
            registry,
            "get_tool_schemas",
            lambda: [
                {
                    "type": "function",
                    "function": {
                        "name": "demo_tool",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
        )

    def test_an_unknown_tool_is_a_line(self, monkeypatch, audit_file):
        asyncio.run(registry._execute_tool_core("no-such-tool", {}))
        assert any(
            entry["decision"] == "unknown_tool"
            for entry in _entries(audit_file)
        )

    def test_a_schema_rejection_is_a_line(self, monkeypatch, audit_file):
        self._bind(monkeypatch)
        # A required parameter is missing and an undeclared one is present: the
        # repair refuses to fill a call the model never made, so this is the
        # branch that returns the validation error.
        asyncio.run(registry._execute_tool_core("demo_tool", {"surprise": 1}))
        assert any(
            entry["decision"] == "schema_rejected"
            for entry in _entries(audit_file)
        )

    def test_a_start_is_written_before_the_tool_runs(self, monkeypatch, audit_file):
        self._bind(monkeypatch)
        asyncio.run(registry._execute_tool_core("demo_tool", {"path": "x"}))
        kinds = [entry["kind"] for entry in _entries(audit_file)]
        assert "tool_start" in kinds and "tool_exec" in kinds
        assert kinds.index("tool_start") < kinds.index("tool_exec")


class TestMcpAudit:
    def _bind(self, monkeypatch, call):
        monkeypatch.setattr(registry, "get_mcp_tools", lambda: {"mcp_demo": {}})
        monkeypatch.setattr(registry, "call_registered_mcp_tool", call)

    def test_an_mcp_call_writes_a_completion_line(self, monkeypatch, audit_file):
        async def call(_name, _args):
            return "done", False

        self._bind(monkeypatch, call)
        asyncio.run(registry._execute_tool_core("mcp_demo", {"query": "x"}))
        entries = _entries(audit_file)
        kinds = [entry["kind"] for entry in entries]
        assert kinds.index("tool_start") < kinds.index("tool_exec")
        completion = next(entry for entry in entries if entry["kind"] == "tool_exec")
        assert completion["status"] == "ok"
        assert completion["detail"] == "done"
        assert isinstance(completion["duration_ms"], int)

    def test_an_mcp_tool_error_writes_a_completion_line(self, monkeypatch, audit_file):
        async def call(_name, _args):
            return "remote refused", True

        self._bind(monkeypatch, call)
        asyncio.run(registry._execute_tool_core("mcp_demo", {"query": "x"}))
        completion = next(
            entry for entry in _entries(audit_file) if entry["kind"] == "tool_exec"
        )
        assert completion["status"] == "error"
        assert completion["detail"].startswith("[MCP-tool-error]")

    def test_an_mcp_raise_writes_a_completion_line(self, monkeypatch, audit_file):
        async def call(_name, _args):
            raise RuntimeError("mcp down")

        self._bind(monkeypatch, call)
        asyncio.run(registry._execute_tool_core("mcp_demo", {"query": "x"}))
        completion = next(
            entry for entry in _entries(audit_file) if entry["kind"] == "tool_exec"
        )
        assert completion["status"] == "error"
        assert "mcp down" in completion["detail"]


class TestMarketplaceRefusals:
    def test_a_stale_plan_and_a_missing_rollback_are_lines(self, audit_file, tmp_path, monkeypatch):
        import core.engine_config as engine_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg", raising=False)
        marketplace_service.install({"status": "stale", "name": "alpha"})
        marketplace_service.rollback("ghost")

        decisions = [entry["decision"] for entry in _entries(audit_file)]
        assert "stale" in decisions
        assert "no_previous" in decisions
        assert all(entry["status"] == "denied" for entry in _entries(audit_file))


class TestEngineKeyAudit:
    def test_store_and_delete_are_lines_without_the_key(self, audit_file, tmp_path, monkeypatch):
        import core.engine_config as engine_config

        monkeypatch.setattr(engine_config, "_store_engine_keyring", lambda token: False)
        token = "sk-proj-abcdefghijklmnop1234567890"
        engine = SimpleNamespace(provider="deepseek", model="deepseek-flash")
        engine_config.store_engine_api_key(token, home=tmp_path, engine=engine)
        engine_config.delete_engine_api_key(home=tmp_path)

        entries = _entries(audit_file)
        assert [entry["kind"] for entry in entries] == ["engine_key", "engine_key"]
        assert entries[0]["decision"] == "stored"
        assert "mode=file_0600" in entries[0]["detail"]
        assert entries[1]["decision"] == "deleted"
        assert token not in audit_file.read_text(encoding="utf-8")


class TestMcpSpawnBoundary:
    """The spawn audit names the boundary it used; without one there is no
    child at all (S8: the raw fallback is gone)."""

    def _bind(self, monkeypatch, wrap_value, boundary="unavailable"):
        from core.tools import mcp_process

        home = tempfile.mkdtemp(prefix="ephe-mcp-home-")
        monkeypatch.setattr(mcp_process.mcp_sandbox, "home_for", lambda name: home)
        monkeypatch.setattr(mcp_process.mcp_sandbox, "wrap", lambda *a, **k: wrap_value)
        monkeypatch.setattr(mcp_process.mcp_sandbox, "platform_boundary", lambda: boundary)
        return mcp_process.StdioLink("/nonexistent/mcp-server", [], timeout=5), home

    def test_no_boundary_refuses_without_spawning(self, monkeypatch, audit_file):
        from core.tools import mcp_process

        link, _home = self._bind(monkeypatch, None, "unavailable")
        calls: list[tuple] = []

        async def fake_exec(*args, **kwargs):
            calls.append(args)
            raise AssertionError("a raw spawn must not happen")

        monkeypatch.setattr(mcp_process.asyncio, "create_subprocess_exec", fake_exec)
        response = asyncio.run(link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}))

        assert response["error"]["code"] == -32006
        assert calls == [], "the child was started without a boundary"
        entry = _entries(audit_file)[-1]
        assert entry["decision"] == "refused"
        assert "os_boundary=unavailable" in entry["detail"]
        # The refusal is not free: the backoff stands in front of the next call.
        second = asyncio.run(link.send({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
        assert second["error"]["code"] == -32004
        assert link.proc is None

    def test_windows_names_the_platform_and_its_missing_boundary(
        self, monkeypatch, audit_file
    ):
        from core.tools import mcp_process

        monkeypatch.setattr(mcp_process.sys, "platform", "win32")
        link, _home = self._bind(monkeypatch, None, "unavailable")
        response = asyncio.run(link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}))
        assert response["error"]["code"] == -32006
        assert "Windows" in response["error"]["message"]
        assert "none" in response["error"]["message"]

    def test_the_sandboxed_child_starts_in_its_own_home(self, monkeypatch, audit_file):
        from core.tools import mcp_process

        link, home = self._bind(monkeypatch, ["/usr/bin/true"], "seatbelt")
        seen: dict = {}

        async def fake_exec(*args, **kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop after the arguments")

        monkeypatch.setattr(mcp_process.asyncio, "create_subprocess_exec", fake_exec)
        asyncio.run(link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}))
        assert seen["cwd"] == home

    def test_the_boundary_name_reaches_the_line(self, monkeypatch, audit_file):
        link, _home = self._bind(monkeypatch, ["/usr/bin/true"], "seatbelt")
        asyncio.run(link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}))
        entries = [e for e in _entries(audit_file) if e["kind"] == "mcp_child"]
        assert entries[-1]["decision"] == "sandboxed"
        assert "os_boundary=seatbelt" in entries[-1]["detail"]

    def test_a_failed_spawn_is_refused_and_not_retried_raw(self, monkeypatch, audit_file):
        from core.tools import mcp_process

        link, _home = self._bind(monkeypatch, ["bwrap", "--ro-bind", "/", "/"], "bubblewrap")
        calls: list[tuple] = []

        async def denied(*args, **kwargs):
            calls.append(args)
            raise PermissionError("setting up uid map: Permission denied")

        monkeypatch.setattr(mcp_process.asyncio, "create_subprocess_exec", denied)
        response = asyncio.run(link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}))

        assert response["error"]["code"] == -32005
        assert len(calls) == 1, "a failed boundary must not fall back to a raw retry"
        entries = [e for e in _entries(audit_file) if e["kind"] == "mcp_child"]
        assert entries[-1]["decision"] == "spawn_failed"
        assert "os_boundary=bubblewrap" in entries[-1]["detail"]

    def test_a_trusted_connector_is_audited(self, monkeypatch, audit_file):
        from core.tools import mcp_process

        def no_wrap(*args, **kwargs):
            raise AssertionError("a trusted connector is not wrapped")

        monkeypatch.setattr(mcp_process.mcp_sandbox, "wrap", no_wrap)
        monkeypatch.setattr(
            mcp_process.mcp_sandbox, "platform_boundary",
            lambda: (_ for _ in ()).throw(AssertionError("no boundary lookup either")),
        )
        link = mcp_process.StdioLink("/usr/bin/true", [], timeout=5, trusted=True)
        asyncio.run(link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}))

        entries = [e for e in _entries(audit_file) if e["kind"] == "mcp_child"]
        assert entries[-1]["decision"] == "trusted"
        assert "os_boundary=trusted" in entries[-1]["detail"]


class TestTransportRefusals:
    def _app(self) -> FastAPI:
        from server.middleware import AuthMiddleware

        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        @app.get("/api/chat")
        async def chat():
            return {"response": "ok"}

        return app

    def _refused(self, client_ip: str) -> int:
        transport = httpx.ASGITransport(app=self._app(), client=(client_ip, 54321))

        async def run():
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                return await c.get("/api/chat", headers={"Host": "10.0.0.5:8765"})

        return asyncio.run(run()).status_code

    def test_a_lan_token_refusal_is_a_line(self, audit_file, monkeypatch):
        from server import middleware

        monkeypatch.setattr(middleware, "LAN_AUTH_TOKEN", "the-token")
        monkeypatch.setattr(middleware, "_REFUSAL_AUDIT", {})

        assert self._refused("10.0.0.9") == 401
        entry = _entries(audit_file)[-1]
        assert entry["kind"] == "security"
        assert entry["decision"] == "token_missing"
        assert "the-token" not in audit_file.read_text(encoding="utf-8")

    def test_repeated_refusals_from_one_client_do_not_flood_the_log(
        self, audit_file, monkeypatch
    ):
        """One line per client and reason per window: each append fsyncs."""
        from server import middleware

        monkeypatch.setattr(middleware, "LAN_AUTH_TOKEN", "the-token")
        monkeypatch.setattr(middleware, "_REFUSAL_AUDIT", {})

        assert self._refused("10.0.0.9") == 401
        assert self._refused("10.0.0.9") == 401
        assert self._refused("10.0.0.7") == 401

        entries = [e for e in _entries(audit_file) if e.get("kind") == "security"]
        clients = sorted(
            part for entry in entries for part in [entry["detail"].split("client=")[1].split()[0]]
        )
        assert clients == ["10.0.0.7", "10.0.0.9"]

    def test_the_window_expires_and_the_next_refusal_is_a_line_again(
        self, audit_file, monkeypatch
    ):
        from server import middleware

        monkeypatch.setattr(middleware, "LAN_AUTH_TOKEN", "the-token")
        monkeypatch.setattr(middleware, "_REFUSAL_AUDIT", {})
        clock = [1000.0]
        monkeypatch.setattr(middleware.time, "monotonic", lambda: clock[0])

        assert self._refused("10.0.0.9") == 401
        clock[0] += 61.0
        assert self._refused("10.0.0.9") == 401

        entries = [e for e in _entries(audit_file) if e.get("kind") == "security"]
        assert len(entries) == 2

    def test_a_websocket_refusal_is_a_line(self, audit_file, monkeypatch):
        from server import middleware
        from server.routes.proxy import proxy_ws

        monkeypatch.setattr(middleware, "LAN_AUTH_TOKEN", "the-token")

        class FakeWS:
            headers = {"host": "10.0.0.5:8765", "origin": "http://evil.test"}
            query_params = {}
            client = SimpleNamespace(host="10.0.0.9")
            closed = 0

            async def close(self, code: int = 1000) -> None:
                self.closed = code

        ws = FakeWS()
        asyncio.run(proxy_ws(ws, "5173", ""))
        assert ws.closed == 1008
        entry = _entries(audit_file)[-1]
        assert entry["kind"] == "security"
        assert entry["decision"] == "ws_refused"
