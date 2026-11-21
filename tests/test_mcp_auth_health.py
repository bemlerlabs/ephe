"""GAP-06 / MCP-02 — auth binding, redirect refusal and health on HTTP.

The request goes to the checked address, the Authorization header stays with the
intended host, a redirect is refused rather than followed, and the server's
failure state is visible without exposing the credential.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools.mcp_transport import MCPClient


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.is_redirect = 300 <= status_code < 400

    def json(self) -> dict:
        return self._payload


@pytest.fixture()
def public_name(monkeypatch):
    import core.network_guard as guard
    import socket

    monkeypatch.setattr(
        guard.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )


@pytest.mark.asyncio
async def test_a_redirect_is_refused_and_the_auth_header_stays_on_the_first_host(
    monkeypatch, public_name
) -> None:
    import core.tools.mcp_transport as transport

    seen: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None, extensions=None):
            seen["url"] = url
            seen["headers"] = dict(headers or {})
            seen["extensions"] = extensions
            return _FakeResponse(302, {"jsonrpc": "2.0", "id": 1, "result": {}})

    monkeypatch.setattr(transport.httpx, "AsyncClient", FakeClient)
    client = MCPClient("https://mcp.example.com/mcp", auth_token="secret-token")
    result = await client._post(
        client.endpoint, client._headers(), {"jsonrpc": "2.0", "id": 1}
    )

    assert result["error"]["code"] == -32011
    assert seen["url"] == "https://93.184.216.34/mcp"
    assert seen["headers"]["Host"] == "mcp.example.com"
    assert seen["headers"]["Authorization"] == "Bearer secret-token"
    assert seen["extensions"] == {"sni_hostname": "mcp.example.com"}
    assert seen["client"]["follow_redirects"] is False
    assert seen["client"]["trust_env"] is False
    assert "secret-token" not in str(result)


@pytest.mark.asyncio
async def test_a_private_target_never_reaches_the_http_client(monkeypatch) -> None:
    import core.tools.mcp_transport as transport

    called = {"count": 0}

    class FakeClient:
        def __init__(self, **kwargs):
            called["count"] += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            raise AssertionError("must not be called")

    monkeypatch.setattr(transport.httpx, "AsyncClient", FakeClient)
    client = MCPClient("https://127.0.0.1:8844/mcp")
    result = await client._post(client.endpoint, client._headers(), {})
    assert result["error"]["code"] == -32010
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_a_jsonrpc_failure_is_visible_as_health_state(monkeypatch) -> None:
    client = MCPClient("https://mcp.example.com/mcp")

    async def fake_post(endpoint, headers, body):
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32601, "message": "nope"},
        }

    client._post = fake_post
    tools = await client.list_tools()
    assert tools == [{"error": "mcp error -32601: nope"}]
    assert "nope" in client.last_error


@pytest.mark.asyncio
async def test_stdio_backoff_is_visible_after_a_failure() -> None:
    from core.tools.mcp_process import StdioLink

    link = StdioLink("true")
    link.note_failure()
    assert link.backoff_seconds() > 0
    assert link.last_error == ""
    link.note_success()
    assert link.backoff_seconds() == 0
