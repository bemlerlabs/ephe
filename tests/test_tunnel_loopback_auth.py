"""Root-cause guard: an outgoing tunnel delivers public requests as
client.host=127.0.0.1. Loopback trust must not kick in there — otherwise the
QR/tunnel access stands unprotected. The call is made on the Host header."""
from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from server import middleware
from server.middleware import AuthMiddleware, _host_without_port, init_auth


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/chat")
    async def chat():
        return {"response": "ok"}

    return app


def _get(client_host: str, host_header: str, token: str | None = None) -> int:
    transport = httpx.ASGITransport(app=_app(), client=(client_host, 54321))

    async def run() -> int:
        headers = {"Host": host_header}
        if token:
            headers["X-Auth-Token"] = token
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/chat", headers=headers)
            return r.status_code

    return asyncio.run(run())


def test_host_without_port_ipv4_ipv6_bare():
    assert _host_without_port("localhost:8765") == "localhost"
    assert _host_without_port("[::1]:8765") == "::1"
    assert _host_without_port("127.0.0.1") == "127.0.0.1"
    assert _host_without_port("e1f6.lhr.life") == "e1f6.lhr.life"


def test_tunnel_request_from_loopback_requires_token():
    """GIVEN a tunnel request (client.host=127.0.0.1, Host=*.lhr.life)
    WHEN /api/chat without a token
    THEN 401 — loopback trust does NOT apply for the public host."""
    token = init_auth(lan_mode=True)
    try:
        assert _get("127.0.0.1", "e1f625f2614298.lhr.life") == 401
        # ...but WITH a token (the QR carries it) it comes through:
        assert _get("127.0.0.1", "e1f625f2614298.lhr.life", token=token) == 200
    finally:
        init_auth(lan_mode=False)


def test_genuine_desktop_loopback_stays_trusted():
    """GIVEN a real desktop browser (client.host=127.0.0.1, Host=localhost)
    WHEN /api/chat without a token
    THEN 200 — no token is needed for the local app."""
    init_auth(lan_mode=True)
    try:
        assert _get("127.0.0.1", "localhost:8765") == 200
        assert _get("127.0.0.1", "127.0.0.1:8765") == 200
    finally:
        init_auth(lan_mode=False)
