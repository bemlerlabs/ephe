"""◑ Ephe · TDD — a plugin MCP tool rides its own confined server over stdio.

Slice 2 of #50: the walking skeleton proves one tool call over the MCP rail.
The plugin declares `components.mcp.entry`, the host starts the server as a
confined subprocess, discovers tools via `tools/list`, and routes `tools/call`
through the live connection. Ruling A1 holds: the host never imports the
plugin's server module.

The test creates a minimal MCP server script, a manifest declaring it, and
proves the call reaches the subprocess and returns its answer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.tools.dynamic_registry import (
    TRANSPORT_MCP,
    ToolDescriptor,
    default_registry,
    fingerprint_for,
)


SERVER_SCRIPT = '''\
import json
import sys

def _result(request_id, payload):
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}

def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

def _tool_reply(text, *, is_error=False):
    return {
        "content": [{"type": "text", "text": text}],
        **({"isError": True} if is_error else {}),
    }

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "Parse error")) + "\\n")
            sys.stdout.flush()
            continue
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            sys.stdout.write(json.dumps(_result(request_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-countdown", "version": "1.0.0"},
            })) + "\\n")
        elif method == "tools/list":
            sys.stdout.write(json.dumps(_result(request_id, {"tools": [
                {
                    "name": "mcp_countdown_set",
                    "description": "Start a countdown timer.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"seconds": {"type": "integer"}},
                        "required": ["seconds"],
                    },
                }
            ]})))
        elif method == "tools/call":
            params = request.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name == "mcp_countdown_set":
                seconds = arguments.get("seconds", 0)
                sys.stdout.write(json.dumps(_result(request_id, _tool_reply(
                    f"Countdown started: {seconds} seconds"
                ))) + "\\n")
            else:
                sys.stdout.write(json.dumps(_result(request_id, _tool_reply(
                    f"Unknown tool: {name}", is_error=True
                ))) + "\\n")
        else:
            sys.stdout.write(json.dumps(_error(request_id, -32601, f"Method not found: {method}")) + "\\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
'''


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    """A minimal plugin bundle with an MCP server script."""
    bundle = tmp_path / "plugins" / "countdown"
    bundle.mkdir(parents=True)
    server_script = bundle / "server.py"
    server_script.write_text(SERVER_SCRIPT, encoding="utf-8")
    manifest = {
        "manifest_version": 2,
        "name": "countdown",
        "version": "1.0.0",
        "description": "A timer the agent can set and read back.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "origin": "first-party",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "tools": [
                {
                    "name": "mcp_countdown_set",
                    "transport": "mcp",
                    "family": "read",
                    "description": "Start a countdown timer.",
                    "parameters": {
                        "type": "object",
                        "properties": {"seconds": {"type": "integer"}},
                        "required": ["seconds"],
                    },
                }
            ],
            "mcp": {"entry": "server.py:main"},
        },
    }
    (bundle / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


@pytest.fixture(autouse=True)
def clean_registry():
    """Unregister the test plugin after each test."""
    yield
    default_registry().unregister_plugin("countdown")


class TestPluginMCPRail:
    """The MCP rail: a plugin tool call reaches its confined server."""

    @pytest.mark.asyncio
    async def test_a_plugin_mcp_tool_call_reaches_the_confined_server(self, plugin_dir: Path, monkeypatch):
        """GIVEN a plugin with an MCP server and one tool declared on the MCP rail
        WHEN the tool is called via dispatch_dynamic_call
        THEN the call reaches the confined server and returns its answer."""
        from core.plugin_mcp_server import PluginMCPServerManager
        from core.tools.dynamic_wiring import dispatch_dynamic_call

        manager = PluginMCPServerManager()
        monkeypatch.setattr(
            "core.plugin_mcp_server.plugin_mcp_manager", lambda: manager
        )

        # Start the server and register the tool
        client = await manager.start_server("countdown", plugin_dir, "server.py:main")
        assert client is not None

        schema = {
            "type": "function",
            "function": {
                "name": "mcp_countdown_set",
                "description": "Start a countdown timer.",
                "parameters": {
                    "type": "object",
                    "properties": {"seconds": {"type": "integer"}},
                    "required": ["seconds"],
                },
            },
        }
        descriptor = ToolDescriptor(
            name="mcp_countdown_set",
            plugin_id="countdown",
            schema=schema,
            transport=TRANSPORT_MCP,
            entry=None,
            tool_family="read",
            fingerprint=fingerprint_for(schema),
            families=frozenset({"read"}),
        )
        assert default_registry().register(descriptor).ok

        # Call the tool
        result = await dispatch_dynamic_call("mcp_countdown_set", {"seconds": 42})

        assert result is not None
        assert "Countdown started: 42 seconds" in result
        assert "is not available" not in result

        # Clean up
        await manager.stop_server("countdown")

    @pytest.mark.asyncio
    async def test_a_plugin_mcp_tool_call_without_a_started_server_refuses(
        self, plugin_dir: Path, monkeypatch
    ):
        """GIVEN a registered MCP descriptor whose server was never started
        WHEN the tool is called
        THEN the call is refused with the existing 'not available' line."""
        from core.plugin_mcp_server import PluginMCPServerManager
        from core.tools.dynamic_wiring import dispatch_dynamic_call

        manager = PluginMCPServerManager()
        monkeypatch.setattr(
            "core.plugin_mcp_server.plugin_mcp_manager", lambda: manager
        )

        schema = {
            "type": "function",
            "function": {
                "name": "mcp_countdown_set",
                "description": "Start a countdown timer.",
                "parameters": {
                    "type": "object",
                    "properties": {"seconds": {"type": "integer"}},
                    "required": ["seconds"],
                },
            },
        }
        descriptor = ToolDescriptor(
            name="mcp_countdown_set",
            plugin_id="countdown",
            schema=schema,
            transport=TRANSPORT_MCP,
            entry=None,
            tool_family="read",
            fingerprint=fingerprint_for(schema),
            families=frozenset({"read"}),
        )
        assert default_registry().register(descriptor).ok

        # Call without starting the server
        result = await dispatch_dynamic_call("mcp_countdown_set", {"seconds": 10})

        assert result is not None
        assert "is not available" in result

    @pytest.mark.asyncio
    async def test_stopping_a_plugin_server_reaps_the_subprocess(
        self, plugin_dir: Path, monkeypatch
    ):
        """GIVEN a started plugin MCP server
        WHEN the server is stopped
        THEN the subprocess is reaped and no longer alive."""
        from core.plugin_mcp_server import PluginMCPServerManager

        manager = PluginMCPServerManager()
        client = await manager.start_server("countdown", plugin_dir, "server.py:main")
        assert client is not None
        assert manager.is_running("countdown")

        await manager.stop_server("countdown")

        assert not manager.is_running("countdown")
