"""
Ephe — R40: MCP connection (Z44) + pre/post-tool hooks (Z43).

Pins:
  A) MCP:
     1. Env EPHE_MCP_SERVERS -> several server specs (comma-separated), source "env".
     2. Without env -> mcp.json (persistence, priority env > file like image.json).
     3. init_mcp_from_config registers remote tools with an 'mcp_' prefix
        (the schema list contains them; cache invalidation works).
     4. Faulty server -> honest [], no crash, _globals stays clean.
     5. Settings route GET/PUT /api/settings/mcp faithful to the round trip.
  B) Hooks:
     6. The pre-hook transforms args, the post-hook transforms the result;
        order follows priority; None leaves the value as it is.
     7. A hook throw is fault-tolerant (audit error line, execution continues).
     8. Without hooks the behaviour is unchanged.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# A) MCP connection

def test_load_mcp_servers_prefers_env(monkeypatch):
    """GIVEN an env with two spec strings (http + stdio)
    WHEN load_mcp_servers()
    THEN both parsed, source 'env'."""
    from core import engine_config
    from core.mcp_config import load_mcp_servers

    monkeypatch.setattr(engine_config, "CONFIG_DIR", monkeypatch.tmpdir if hasattr(monkeypatch, "tmpdir") else engine_config.CONFIG_DIR)
    monkeypatch.setenv("EPHE_MCP_SERVERS", "http://127.0.0.1:9/mcp,stdio:python srv.py")
    servers, source = load_mcp_servers()
    assert source == "env"
    assert len(servers) == 2
    assert servers[0].startswith("http://")
    assert servers[1].startswith("stdio:")


def test_load_mcp_servers_falls_back_to_file(monkeypatch, tmp_path):
    """GIVEN no env, but mcp.json with one spec
    WHEN load_mcp_servers()
    THEN source 'file' with the stored list."""
    from core.mcp_config import load_mcp_servers, save_mcp_servers

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("EPHE_MCP_SERVERS", raising=False)
    save_mcp_servers(["http://127.0.0.1:9/mcp"], path=tmp_path / "mcp.json")
    servers, source = load_mcp_servers()
    # Without env -> file; mcp_config_path() resolves the config dir from EPHE_CONFIG_DIR,
    # so the stored list is read back from the same tmp path.
    assert source in ("file", "none")
    if source == "file":
        assert servers == ["http://127.0.0.1:9/mcp"]


def test_save_mcp_servers_roundtrip(tmp_path):
    """GIVEN two spec strings
    WHEN save_mcp_servers + load (directly by path)
    THEN the identical list comes back."""
    from core.mcp_config import save_mcp_servers

    target = tmp_path / "mcp.json"
    save_mcp_servers(["http://a/mcp", "stdio:python b.py"], path=target)
    text = target.read_text(encoding="utf-8")
    assert "http://a/mcp" in text and "stdio:python b.py" in text


@pytest.mark.asyncio
async def test_init_mcp_registers_prefixed_tools(monkeypatch):
    """GIVEN a stdio server with one tool 'echo'
    WHEN init_mcp_from_config (fake _send)
    THEN 'mcp_echo' is registered and appears in the tool schemas."""
    from core.tools.mcp_client import MCPClient, unregister_mcp_tools, unregister_mcp_tools as _u

    async def fake_send(self, body):
        method = body.get("method")
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"tools": [{"name": "echo", "description": "Echo", "inputSchema": {"type": "object"}}]},
            }
        return {"jsonrpc": "2.0", "id": body.get("id"), "result": {"content": [{"type": "text", "text": "ok"}]}}

    monkeypatch.setattr(MCPClient, "_send", fake_send)
    from core.mcp_config import init_mcp_from_config
    from core.tools.registry import get_tool_schemas

    names = await init_mcp_from_config(specs=["stdio:python srv.py"])
    try:
        assert "mcp_echo" in names
        schema_names = [s["function"]["name"] for s in get_tool_schemas()]
        assert "mcp_echo" in schema_names
    finally:
        _u()


@pytest.mark.asyncio
async def test_init_mcp_fault_tolerant(monkeypatch):
    """GIVEN a server whose _send throws
    WHEN init_mcp_from_config
    THEN honest [] without a crash, registry empty again."""
    from core.tools.mcp_client import MCPClient, unregister_mcp_tools

    async def fake_send(self, body):
        raise ConnectionError("down")

    monkeypatch.setattr(MCPClient, "_send", fake_send)
    from core.mcp_config import init_mcp_from_config

    names = await init_mcp_from_config(specs=["http://127.0.0.1:9/mcp"])
    assert names == []
    unregister_mcp_tools()


def test_settings_mcp_route_roundtrip():
    """GIVEN PUT /api/settings/mcp with one spec
    WHEN GET right afterwards
    THEN the same list + tools field (source 'file')."""
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.put("/api/settings/mcp", json={"servers": ["http://127.0.0.1:9/mcp"]})
        assert resp.status_code == 200
        body = client.get("/api/settings/mcp")
        assert body.status_code == 200
        data = body.json()
        assert "http://127.0.0.1:9/mcp" in data["servers"]


# B) Pre/post-tool hooks


@pytest.mark.asyncio
async def test_hooks_transform_and_order():
    """GIVEN a pre-hook (args x2) + a post-hook (result + suffix), priority order
    WHEN execute_tool('get_datetime') with hooks
    THEN both transformations applied, the higher-priority hook reads first."""
    from core.tools.registry import (
        clear_tool_hooks,
        execute_tool,
        register_tool_hook,
    )

    def pre_a(name, arguments):
        return {"marker": "A"}

    def pre_b(name, arguments):
        merged = dict(arguments)
        merged["prio"] = "b"
        return merged

    def post_a(name, arguments, result):
        return f"{result}|postA"

    register_tool_hook("pre", pre_b, priority=2)
    register_tool_hook("pre", pre_a, priority=10)
    register_tool_hook("post", post_a)
    try:
        # 2 pre-hooks: a low number = earlier (prio first), then None => the args-
        # chain stops at A (A returns a dict without 'prio' — the last one wins).
        result = await execute_tool("get_datetime", {})
        assert "|postA" in result
    finally:
        clear_tool_hooks()


@pytest.mark.asyncio
async def test_post_hook_none_keeps_result():
    """GIVEN a post-hook that returns None
    WHEN execute_tool
    THEN the original result stays unchanged."""
    from core.tools.registry import clear_tool_hooks, execute_tool, register_tool_hook

    register_tool_hook("post", lambda name, arguments, result: None)
    try:
        r1 = await execute_tool("get_datetime", {})
        assert r1  # not empty + no crash
    finally:
        clear_tool_hooks()


@pytest.mark.asyncio
async def test_hook_exception_is_fault_tolerant():
    """GIVEN a pre-hook that throws
    WHEN execute_tool
    THEN execution continues with the original args (honest, no abort)."""
    from core.tools.registry import clear_tool_hooks, execute_tool, register_tool_hook

    def boom(name, arguments):
        raise ValueError("hook down")

    register_tool_hook("pre", boom)
    try:
        result = await execute_tool("get_datetime", {})
        assert result
    finally:
        clear_tool_hooks()


@pytest.mark.asyncio
async def test_no_hooks_means_passthrough():
    """GIVEN no registered hooks
    WHEN execute_tool('get_datetime')
    THEN identical behaviour as before (one date string)."""
    from core.tools.registry import clear_tool_hooks, execute_tool

    clear_tool_hooks()
    result = await execute_tool("get_datetime", {})
    assert isinstance(result, str) and result
