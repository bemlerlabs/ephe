"""Loopback callers that spend authority.

A read-only GET with no Origin stays token-free: that is the app's own fetch
and the local health check. A mutation, and a GET that writes state or opens
another service, require an Origin this server serves or the LAN token.
With LAN mode off there is no token. The suite's synthetic host stands in
for the app, and only when the request brought no Origin of its own.
"""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    """LAN auth off, config under the test tmp dir, the desktop trust path."""
    from core import update_check
    from server.main import create_app
    from server.middleware import init_auth
    from server.routes import mobile

    config = tmp_path / "ephe-home"
    config.mkdir(exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    saved_cache = dict(update_check._cache)
    saved_flag = mobile._device_connected
    init_auth(lan_mode=False)
    app = create_app(lan_mode=False)
    try:
        with TestClient(app) as suite:
            yield suite
    finally:
        update_check._cache.clear()
        update_check._cache.update(saved_cache)
        mobile._device_connected = saved_flag
        init_auth(lan_mode=False)


def _loopback(app, method: str, path: str, headers: dict | None = None, body: dict | None = None):
    """One request whose TCP peer and Host are loopback, the shape curl has."""
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))

    async def run():
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8765"
        ) as client:
            return await client.request(method, path, headers=headers, json=body)

    return asyncio.run(run())


def _code(response) -> str:
    return response.json()["error"]["detail"]["code"]


def test_a_local_process_without_an_origin_cannot_mutate(desktop, monkeypatch):
    """curl on 127.0.0.1 sends no Origin. A settings write is refused."""
    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    refused = _loopback(desktop.app, "POST", "/api/settings", body={"language": "en"})
    assert refused.status_code == 403, refused.text
    assert _code(refused) == "untrusted_origin"
    assert os.environ["EPHE_LANGUAGE"] == "de"


def test_a_blank_origin_is_the_same_missing_header(desktop, monkeypatch):
    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    refused = _loopback(
        desktop.app,
        "POST",
        "/api/settings",
        headers={"Origin": "   "},
        body={"language": "en"},
    )
    assert refused.status_code == 403, refused.text
    assert _code(refused) == "untrusted_origin"
    assert os.environ["EPHE_LANGUAGE"] == "de"


def test_a_null_origin_mutation_stays_refused_on_the_loopback_peer(desktop, monkeypatch):
    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    refused = _loopback(
        desktop.app,
        "POST",
        "/api/settings",
        headers={"Origin": "null"},
        body={"language": "en"},
    )
    assert refused.status_code == 403, refused.text
    assert _code(refused) == "untrusted_origin"
    assert os.environ["EPHE_LANGUAGE"] == "de"


def test_a_local_process_without_an_origin_cannot_spend_a_get(desktop):
    """The four authority GETs stay refused when the caller sends no Origin."""
    from core import update_check
    from server.middleware import AUTHORITY_GET_PREFIXES
    from server.routes import mobile

    mobile._device_connected = True
    update_check._cache["value"] = {"marker": "stay"}
    targets = (
        "/api/artifacts/proxy?url=https://example.test/a.png",
        "/api/mobile/qr",
        "/api/update/check",
        "/api/proxy/5173",
    )
    assert len(targets) == len(AUTHORITY_GET_PREFIXES)
    for path in targets:
        refused = _loopback(desktop.app, "GET", path)
        assert refused.status_code == 403, (path, refused.text)
        assert _code(refused) == "untrusted_origin"
    assert mobile._device_connected is True
    assert update_check._cache["value"]["marker"] == "stay"


def test_a_read_only_get_without_an_origin_still_answers(desktop):
    """`/api/settings` with no Origin is the desktop fetch and the health check's sibling."""
    for path in ("/api/settings", "/api/mobile/status"):
        read = _loopback(desktop.app, "GET", path)
        assert read.status_code == 200, (path, read.text)


def test_the_app_origin_may_mutate(desktop, monkeypatch):
    """The PWA and the shell send an Origin this server serves."""
    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    allowed = _loopback(
        desktop.app,
        "POST",
        "/api/settings",
        headers={"Origin": "http://127.0.0.1:8765"},
        body={"language": "en"},
    )
    assert allowed.status_code == 200, allowed.text
    assert os.environ["EPHE_LANGUAGE"] == "en"


def test_a_typed_app_origin_is_accepted_on_loopback(desktop, monkeypatch):
    """A program on this machine can type the app Origin. The header is a label.

    `docs/SECURITY_AND_PRIVACY.md` names that limit. The plugin worker cannot
    open the socket, and a browser page cannot type a foreign page's Origin.
    """
    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    typed = _loopback(
        desktop.app,
        "POST",
        "/api/settings",
        headers={"Origin": "tauri://localhost"},
        body={"language": "en"},
    )
    assert typed.status_code == 200, typed.text
    assert os.environ["EPHE_LANGUAGE"] == "en"


def test_the_lan_token_stands_in_for_a_missing_origin(desktop, monkeypatch):
    """With LAN mode on, the token is the credential a script on the machine carries."""
    from server import middleware

    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    middleware.LAN_AUTH_TOKEN = "loopback-caller-token"
    try:
        refused = _loopback(
            desktop.app, "POST", "/api/settings", body={"language": "en"}
        )
        assert refused.status_code == 403, refused.text
        assert _code(refused) == "untrusted_origin"
        assert os.environ["EPHE_LANGUAGE"] == "de"
        allowed = _loopback(
            desktop.app,
            "POST",
            "/api/settings",
            headers={"X-Auth-Token": "loopback-caller-token"},
            body={"language": "en"},
        )
        assert allowed.status_code == 200, allowed.text
        assert os.environ["EPHE_LANGUAGE"] == "en"
        wrong = _loopback(
            desktop.app,
            "POST",
            "/api/settings",
            headers={"X-Auth-Token": "nope"},
            body={"language": "de"},
        )
        assert wrong.status_code == 403, wrong.text
        assert _code(wrong) == "untrusted_origin"
        assert os.environ["EPHE_LANGUAGE"] == "en"
    finally:
        middleware.LAN_AUTH_TOKEN = None


def test_the_suite_host_keeps_an_absent_origin(desktop, monkeypatch):
    """TestClient speaks as `testserver`. Production has no such host."""
    monkeypatch.setenv("EPHE_LANGUAGE", "de")
    allowed = desktop.post("/api/settings", json={"language": "en"})
    assert allowed.status_code == 200, allowed.text
    assert os.environ["EPHE_LANGUAGE"] == "en"


def test_a_websocket_without_an_origin_needs_the_app_or_the_token():
    """The handshake follows the same split as a mutation."""
    from server.middleware import init_auth, ws_client_authorized

    init_auth(lan_mode=False)

    class _Sock:
        def __init__(self, host: str, origin: str | None = None, token: str = ""):
            self.client = type("Peer", (), {"host": "127.0.0.1"})()
            self.headers = {"host": host}
            if origin is not None:
                self.headers["origin"] = origin
            self.query_params = {"token": token} if token else {}

    assert ws_client_authorized(_Sock("127.0.0.1:8765")) is False
    assert ws_client_authorized(
        _Sock("127.0.0.1:8765", origin="http://127.0.0.1:8765")
    ) is True
    assert ws_client_authorized(
        _Sock("127.0.0.1:8765", origin="https://evil.example")
    ) is False
    assert ws_client_authorized(_Sock("testserver")) is True

    token = init_auth(lan_mode=True)
    try:
        assert ws_client_authorized(_Sock("127.0.0.1:8765")) is False
        assert ws_client_authorized(_Sock("127.0.0.1:8765", token=token or "")) is True
        assert ws_client_authorized(
            _Sock("127.0.0.1:8765", origin="https://evil.example", token=token or "")
        ) is True
    finally:
        init_auth(lan_mode=False)
