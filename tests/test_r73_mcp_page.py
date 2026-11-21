"""
◑ Ephe – r73 (E3c): the MCP page backend — health probe + curated catalog.
tests/test_r73_mcp_page.py

Pins:
1. POST /api/mcp/health takes NO parameters (no SSRF playing field) and
   probes only the server-side configured specs; per server:
   status ok/unreachable + tool_count + transport.
2. Fail-soft: an unreachable server stays status=unreachable, never 500.
3. GET /api/mcp/catalog returns curated entries (id/name/description/
   category); when a spec is set it starts with http://, https:// or
   stdio: (the PUT contract is anticipated) — never any secret fields.
4. Both routes also answer without configured servers (empty, 200).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRET = "sk-SUPERSECRET-r73"


@pytest.fixture
def clean_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("EPHE_MCP_SERVERS", raising=False)
    return tmp_path / "cfg"


def _boot():
    from fastapi.testclient import TestClient
    from server.main import create_app

    return TestClient(create_app())


def _patch_servers(monkeypatch: pytest.MonkeyPatch, servers: list[str]) -> None:
    """Set the configured specs deterministically (isolated from the real
    developer machine — mcp.json under CONFIG_DIR is never read)."""
    import core.mcp_config as cfg

    monkeypatch.setattr(
        cfg, "load_mcp_servers",
        lambda: (list(servers), ("env" if servers else "none")),
    )


class TestHealthRoute:

    def test_no_params_probes_configured_only(self, clean_mcp: Path, monkeypatch: pytest.MonkeyPatch):
        _patch_servers(monkeypatch, ["http://127.0.0.1:9/v1"])
        from core.tools import mcp_client as mc

        async def fake_list_tools(self):  # noqa: ANN001
            return [{"name": "echo"}]

        async def fake_initialize(self):  # noqa: ANN001
            return {"jsonrpc": "2.0", "id": 1, "result": {}}

        monkeypatch.setattr(mc.MCPClient, "list_tools", fake_list_tools)
        monkeypatch.setattr(mc.MCPClient, "initialize", fake_initialize)
        with _boot() as client:
            r = client.post("/api/mcp/health", json={"url": "http://evil.example"})
            assert r.status_code == 200
            body = r.json()
            assert [s["spec"] for s in body["servers"]] == ["http://127.0.0.1:9/v1"]
            assert body["servers"][0]["status"] == "ok"
            assert body["servers"][0]["tool_count"] == 1
            assert body["servers"][0]["transport"] == "http"

    def test_unreachable_is_fail_soft(self, clean_mcp: Path, monkeypatch: pytest.MonkeyPatch):
        _patch_servers(monkeypatch, ["http://127.0.0.1:1/v1"])
        with _boot() as client:
            r = client.post("/api/mcp/health")
            assert r.status_code == 200
            s = r.json()["servers"][0]
            assert s["status"] == "unreachable"
            assert s["tool_count"] == 0

    def test_empty_config_ok(self, clean_mcp: Path, monkeypatch: pytest.MonkeyPatch):
        _patch_servers(monkeypatch, [])
        with _boot() as client:
            r = client.post("/api/mcp/health")
            assert r.status_code == 200
            assert r.json() == {"servers": []}

    def test_stdio_probe_forwards_command_args(self, clean_mcp: Path, monkeypatch: pytest.MonkeyPatch):
        """Regression: the health probe must pass spec.args through to MCPClient.

        Without args `npx -y <pkg>` starts as a bare `npx` → a valid
        stdio server wrongly shows up as unreachable.
        """
        _patch_servers(monkeypatch, ["stdio:npx -y @modelcontextprotocol/server-filesystem ~/Desktop"])
        from core.tools import mcp_client as mc

        captured: dict = {}
        real_init = mc.MCPClient.__init__

        def spy_init(self, endpoint, transport="http", label="", timeout=30.0, args=None):  # noqa: ANN001
            captured["endpoint"] = endpoint
            captured["transport"] = transport
            captured["args"] = args
            real_init(self, endpoint, transport, label, timeout, args)

        async def fake_initialize(self):  # noqa: ANN001
            return {"jsonrpc": "2.0", "id": 1, "result": {}}

        async def fake_list_tools(self):  # noqa: ANN001
            return [{"name": "read"}]

        monkeypatch.setattr(mc.MCPClient, "__init__", spy_init)
        monkeypatch.setattr(mc.MCPClient, "initialize", fake_initialize)
        monkeypatch.setattr(mc.MCPClient, "list_tools", fake_list_tools)
        with _boot() as client:
            r = client.post("/api/mcp/health")
            assert r.status_code == 200
            assert captured["endpoint"] == "npx"
            assert captured["transport"] == "stdio"
            assert captured["args"] == ["-y", "@modelcontextprotocol/server-filesystem", "~/Desktop"]


class TestCatalogRoute:

    def test_catalog_contract(self, clean_mcp: Path):
        with _boot() as client:
            r = client.get("/api/mcp/catalog")
            assert r.status_code == 200
            entries = r.json()["entries"]
            assert len(entries) >= 4
            for e in entries:
                assert set(("id", "name", "description", "category")) <= set(e)
                if "spec" in e:
                    assert str(e["spec"]).startswith(("http://", "https://", "stdio:"))

    def test_catalog_no_secret_fields(self, clean_mcp: Path):
        with _boot() as client:
            raw = client.get("/api/mcp/catalog").text
            assert SECRET not in raw
            for bad in ("api_key", "apikey", "password", "secret"):
                assert bad not in raw.lower()
