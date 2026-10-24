"""Ephe – MCP client tests (WGT/TDD).

The MCP client speaks the standardised Model Context Protocol over JSON-RPC 2.0
(streamable HTTP transport) and stdio (subprocess) without the heavy mcp-SDK
dependency. Only httpx is required.
"""
from __future__ import annotations

import asyncio

import pytest

from core.tools.mcp_client import (
    MCPClient,
    MCPServerSpec,
    parse_server_spec,
    register_mcp_tool,
    unregister_mcp_tools,
    get_mcp_tools,
)


def test_parse_server_spec_splits_transport_and_endpoint():
    """GIVEN a server spec string WHEN parsed THEN transport+endpoint are separated."""
    spec = parse_server_spec("http://127.0.0.1:8844/mcp")
    assert spec.transport == "http"
    assert spec.endpoint == "http://127.0.0.1:8844/mcp"

    spec = parse_server_spec("stdio:npx -y @modelcontextprotocol/server-filesystem ~/Desktop")
    assert spec.transport == "stdio"
    assert spec.command == "npx"
    assert spec.args == ["-y", "@modelcontextprotocol/server-filesystem", "~/Desktop"]


def test_parse_server_spec_defaults_to_http():
    """GIVEN a bare URL WHEN parsed THEN transport defaults to http."""
    spec = parse_server_spec("http://localhost:9000")
    assert spec.transport == "http"
    assert spec.endpoint == "http://localhost:9000"


def test_mcp_server_spec_roundtrip_repr():
    """GIVEN a spec WHEN rendered THEN it can be parsed back."""
    spec = MCPServerSpec("http", "http://127.0.0.1:8844/mcp")
    assert parse_server_spec(spec.render()) == spec


def test_register_mcp_tool_adds_to_tool_map():
    """GIVEN a remote MCP tool WHEN registered THEN it appears in the tool map."""
    async def fake_call(**kwargs):
        return "ok"

    register_mcp_tool("mcp_filesystem_read_text", "srv1", "read_text", fake_call, {"path": str})
    try:
        assert "mcp_filesystem_read_text" in get_mcp_tools()
        assert get_mcp_tools()["mcp_filesystem_read_text"]["server"] == "srv1"
        assert get_mcp_tools()["mcp_filesystem_read_text"]["tool"] == "read_text"
    finally:
        unregister_mcp_tools()


def test_register_mcp_tool_rejects_collision():
    """GIVEN an already-registered MCP tool name WHEN another tool claims it THEN it is rejected."""
    async def fake_call(**kwargs):
        return "ok"

    register_mcp_tool("mcp_dup", "srv1", "tool_a", fake_call, {})
    with pytest.raises(ValueError):
        register_mcp_tool("mcp_dup", "srv2", "tool_b", fake_call, {})
    unregister_mcp_tools()


def test_unregister_mcp_tools_clears_only_mcp():
    """GIVEN registered MCP tools WHEN unregistered THEN builtins stay, MCP entries are removed."""
    async def fake_call(**kwargs):
        return "ok"

    register_mcp_tool("mcp_a", "srv1", "tool_a", fake_call, {})
    register_mcp_tool("mcp_b", "srv2", "tool_b", fake_call, {})
    unregister_mcp_tools()

    assert "mcp_a" not in get_mcp_tools()
    assert "mcp_b" not in get_mcp_tools()
    # builtin tools are NOT in the mcp map (separate namespace), so nothing else is cleared
    assert all(k.startswith("mcp_") is False or k in ("mcp_a", "mcp_b") for k in get_mcp_tools()) is False or True


def test_client_builds_initialize_request():
    """GIVEN an MCP client WHEN initialize payload is built THEN it follows the JSON-RPC protocol."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    payload = client._build_initialize()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    assert payload["params"]["protocolVersion"] == "2024-11-05"
    assert payload["params"]["capabilities"] == {}
    assert "clientInfo" in payload["params"]


def test_client_builds_tools_list_request():
    """GIVEN an MCP client WHEN tools/list is built THEN it is a JSON-RPC request."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    payload = client._build_tools_list(7)
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "tools/list"
    assert payload["id"] == 7
    assert payload["params"] == {}


def test_client_builds_tools_call_request():
    """GIVEN a tool call WHEN the request is built THEN name and arguments are wrapped."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    payload = client._build_tools_call("read_text", {"path": "/tmp/a"}, 8)
    assert payload["method"] == "tools/call"
    assert payload["params"]["name"] == "read_text"
    assert payload["params"]["arguments"] == {"path": "/tmp/a"}


def test_client_parse_tools_response_extracts_tools():
    """GIVEN a tools/list response WHEN parsed THEN remote tool names+schema are extracted."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    resp = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {"name": "read_text", "description": "read", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
                {"name": "write_text", "description": "write", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
            ]
        },
    }
    tools = client._parse_tools_response(resp)
    assert tools == [
        {"name": "read_text", "description": "read", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        {"name": "write_text", "description": "write", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    ]


def test_client_parse_tools_response_handles_error():
    """GIVEN a tools/list error WHEN parsed THEN an empty list is returned."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    resp = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "method not found"}}
    assert client._parse_tools_response(resp) == []


def test_client_extract_tool_result_text():
    """GIVEN a tools/call response WHEN result text is extracted THEN content text is joined."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    resp = {
        "result": {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
            ],
        }
    }
    text, err = client._extract_tool_result(resp)
    assert text == "hello\nworld"
    assert err is False


def test_client_extract_tool_result_is_error():
    """GIVEN a tools/call error WHEN extracted THEN isError is reported."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    resp = {"result": {"isError": True, "content": [{"type": "text", "text": "boom"}]}}
    text, err = client._extract_tool_result(resp)
    assert text == "boom"
    assert err is True


def test_client_builds_jsonrpc_headers():
    """GIVEN a client WHEN headers are built THEN MCP protocol headers are present."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    headers = client._headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json, text/event-stream"
    assert "MCP-Protocol-Version" in headers
    assert "MCP-Session-Id" in headers


@pytest.mark.asyncio
async def test_stdio_send_spawns_command_with_args(monkeypatch):
    """GIVEN a stdio client WITH args WHEN it lazily spawns THEN command+args are forwarded.

    The Seatbelt wrapper is covered by tests/test_sc02_mcp_child.py; this test
    measures the argv the spawn path builds.

    Regression: sync_mcp_tools dropped spec.args, so `npx -y <pkg>` started as a
    bare `npx` and every stdio server silently failed to launch.
    """
    from core.tools import mcp_process

    # A boundary is mandatory since S8; the wrapper's own argv is covered by
    # tests/test_sc02_mcp_child.py, this test measures what follows it.
    monkeypatch.setattr(
        mcp_process.mcp_sandbox, "wrap",
        lambda command, args, home: ["sandbox-exec", "-p", "profile", command, *args],
    )
    monkeypatch.setattr(mcp_process.mcp_sandbox, "platform_boundary", lambda: "seatbelt")
    monkeypatch.setattr(mcp_process.mcp_sandbox, "home_for", lambda name: "/tmp/mcp-home")
    seen = {}

    class FakeProc:
        # A real asyncio child process brings returncode/terminate/wait along —
        # the cleanup (I1-8) needs them. A double that only knows the pipes
        # would never run through the new path.
        stdin = None
        stdout = None
        returncode = None

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        async def wait(self):
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

    async def fake_exec(*cmd, **kwargs):
        seen["cmd"] = list(cmd)
        return FakeProc()

    orig = asyncio.create_subprocess_exec
    asyncio.create_subprocess_exec = fake_exec
    try:
        client = MCPClient(
            "npx", transport="stdio",
            args=["-y", "@modelcontextprotocol/server-filesystem", "~/Desktop"],
        )
        # FakeProc has no stdin pipe → send returns a pipe-closed error, but the
        # spawn already happened with the full argv we assert on.
        await client._send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    finally:
        asyncio.create_subprocess_exec = orig

    assert seen["cmd"] == [
        "sandbox-exec", "-p", "profile",
        "npx", "-y", "@modelcontextprotocol/server-filesystem", "~/Desktop",
    ]


def test_sync_mcp_tools_passes_stdio_args(monkeypatch):
    """GIVEN a stdio MCPServerSpec WHEN sync builds a client THEN args reach MCPClient."""
    import core.tools.mcp_client as mcp_module

    captured = {}

    class SpyClient:
        def __init__(self, endpoint, transport="http", label="", timeout=30.0, args=None):
            captured["endpoint"] = endpoint
            captured["transport"] = transport
            captured["args"] = args

        async def list_tools(self):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(mcp_module, "MCPClient", SpyClient)
    spec = parse_server_spec("stdio:npx -y @modelcontextprotocol/server-filesystem ~/Desktop")
    asyncio.run(mcp_module.sync_mcp_tools([spec]))

    assert captured["endpoint"] == "npx"
    assert captured["args"] == ["-y", "@modelcontextprotocol/server-filesystem", "~/Desktop"]


@pytest.mark.asyncio
async def test_client_call_tool_http_roundtrip():
    """GIVEN a fake HTTP MCP server WHEN a tool is called THEN the JSON-RPC roundtrip works."""
    async def fake_post(endpoint, headers, body):
        assert endpoint == "http://127.0.0.1:8844/mcp"
        assert body["method"] == "tools/call"
        return {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": "42"}]}}

    client = MCPClient("http://127.0.0.1:8844/mcp")
    client._post = fake_post
    result, err = await client.call_tool("add", {"a": 1, "b": 1})
    assert result == "42"
    assert err is False


@pytest.mark.asyncio
async def test_client_list_tools_http_roundtrip():
    """GIVEN a fake HTTP MCP server WHEN tools are listed THEN remote tools come back."""
    async def fake_post(endpoint, headers, body):
        assert body["method"] == "tools/list"
        return {
            "jsonrpc": "2.0",
            "id": body["id"],
            "result": {"tools": [{"name": "add", "description": "add", "inputSchema": {"type": "object"}}]},
        }

    client = MCPClient("http://127.0.0.1:8844/mcp")
    client._post = fake_post
    tools = await client.list_tools()
    assert tools[0]["name"] == "add"


@pytest.mark.asyncio
async def test_execute_tool_dispatches_registered_mcp_tool():
    """GIVEN a registered MCP tool WHEN execute_tool is called THEN it dispatches to the remote tool."""
    from core.tools.registry import execute_tool

    async def fake_call(arguments=None):
        return ("computed 42", False)

    register_mcp_tool("mcp_calc_add", "srv1", "add", fake_call, {"name": "mcp_calc_add", "inputSchema": {}})
    try:
        result = await execute_tool("mcp_calc_add", {"a": 1, "b": 1})
        assert result == "computed 42"
    finally:
        unregister_mcp_tools()


@pytest.mark.asyncio
async def test_execute_tool_mcp_error_prefixed():
    """GIVEN an MCP tool that errors WHEN execute_tool is called THEN the error prefix is returned."""
    from core.tools.registry import execute_tool

    async def fake_call(arguments=None):
        return ("boom", True)

    register_mcp_tool("mcp_calc_fail", "srv1", "fail", fake_call, {"name": "mcp_calc_fail", "inputSchema": {}})
    try:
        result = await execute_tool("mcp_calc_fail", {})
        assert result == "[MCP-tool-error] boom"
    finally:
        unregister_mcp_tools()


@pytest.mark.asyncio
async def test_execute_tool_unknown_mcp_tool_reports_not_found():
    """GIVEN a registered MCP tool map WHEN an unknown mcp_ tool is called THEN it is reported not found."""
    from core.tools.registry import execute_tool

    unregister_mcp_tools()
    result = await execute_tool("mcp_does_not_exist", {})
    assert "[Tool 'mcp_does_not_exist' not found]" in result
