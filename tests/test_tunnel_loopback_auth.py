"""Root-cause guard: an outgoing tunnel delivers public requests as
client.host=127.0.0.1. Loopback trust must not kick in there — otherwise the
QR/tunnel access stands unprotected. The call is made on the Host header."""
from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from server import middleware
from server.middleware import (
    AuthMiddleware,
    _host_without_port,
    host_allowed,
    init_auth,
)


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


def test_a_dns_name_starting_with_127_is_not_loopback():
    assert host_allowed("127.0.0.1.attacker.test") is False
    assert host_allowed("127.0.0.2") is True
    assert host_allowed("::1") is True


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


def test_the_request_guard_does_not_take_the_token_path_away():
    """A tunnel request is a loopback peer with a public Host. The token stays
    its credential: the new Host/Origin guard must not reject it before the
    AuthMiddleware can accept it."""
    from server.main import create_app

    app = create_app(lan_mode=True)
    token = middleware.LAN_AUTH_TOKEN
    assert token
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54321))

    async def run(headers: dict[str, str]) -> int:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://tunnel.invalid"
        ) as client:
            response = await client.get("/api/plugins", headers=headers)
            return response.status_code

    try:
        headers = {
            "Host": "e1f625f2614298.lhr.life",
            "Origin": "http://e1f625f2614298.lhr.life",
        }
        assert asyncio.run(run(headers)) == 401
        assert asyncio.run(run({**headers, "X-Auth-Token": token})) == 200
    finally:
        init_auth(lan_mode=False)


# #60: the token comparison must be total over what a client can send.


def _file_app() -> FastAPI:
    """An app with the route whose query-string token fallback the media elements use.

    `AuthMiddleware` only reads `?token=` on `/api/file*` and `/charts` (an `<img>` cannot
    send a header), and that is the parameter a phone fills in from the QR link. The defect
    lived exactly there, so the guard has to be tested through it.
    """
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/file/read")
    async def read():
        return {"ok": True}

    return app


async def _call(app: FastAPI, client_host: str, host_header: str, token: str | None) -> int:
    transport = httpx.ASGITransport(app=app, client=(client_host, 54321))
    params = {} if token is None else {"token": token}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/api/file/read", params=params, headers={"Host": host_header})
        return response.status_code


def test_a_non_ascii_token_is_refused_and_never_raises():
    """A percent-encoded byte the gate cannot compare is still a wrong token.

    Measured before the fix: `hmac.compare_digest` raises
    `TypeError: comparing strings with non-ASCII characters is not supported`, and the
    exception inside the middleware is answered as a 500. A client should not be able to
    turn an authentication check into a server error by what it puts in a query string.
    """
    token = init_auth(lan_mode=True)
    try:
        app = _file_app()
        # The right token still gets through, so the cases below are proven to have
        # reached the comparison rather than an earlier rejection.
        assert asyncio.run(_call(app, "203.0.113.7", "e1f625f2614298.lhr.life", token)) == 200
        for offered in ("äöü", "\U0001f600", "\ufffd", "½", "tok\u200ben"):
            status = asyncio.run(_call(app, "203.0.113.7", "e1f625f2614298.lhr.life", offered))
            assert status == 401, (offered, status)
    finally:
        init_auth(lan_mode=False)


def test_tokens_match_is_total_on_every_string_shape():
    """The helper on its own, including the shapes a decoder can hand back."""
    from server.middleware import tokens_match

    assert tokens_match("abc123", "abc123") is True
    assert tokens_match("abc124", "abc123") is False
    assert tokens_match("", "abc123") is False
    # A lone surrogate is what a strict decode of a hostile byte sequence can produce.
    for hostile in ("ä", "\ud800", "\udfff", "\x00", "a" * 4096):
        assert tokens_match(hostile, "abc123") is False, repr(hostile)


def test_the_websocket_handshake_refuses_a_non_ascii_token_without_raising():
    """The same comparison sits on the WS gate, which BaseHTTPMiddleware never covers.

    A raise here does not answer 500 — it fails the handshake as an unhandled exception,
    which is the worse shape to leave a client in.
    """
    from server.middleware import ws_client_authorized

    init_auth(lan_mode=True)
    try:
        class _Client:
            host = "203.0.113.7"

        class _Ws:
            client = _Client()
            headers = {"host": "e1f625f2614298.lhr.life", "origin": "https://e1f625f2614298.lhr.life"}
            query_params = {"token": "ä"}

        assert ws_client_authorized(_Ws()) is False

        class _WsGood(_Ws):
            query_params = {"token": middleware.LAN_AUTH_TOKEN or ""}

        assert ws_client_authorized(_WsGood()) is True
    finally:
        init_auth(lan_mode=False)
