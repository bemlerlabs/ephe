"""LAN mode: the media mounts are behind the pairing token.

`/charts` was gated after it served the whole artifact tree. `/audio` and
`/images` kept answering a LAN peer without a token because their prefixes were
not in the middleware's list, so a phone on the same Wi-Fi could fetch desktop
screenshots and voice recordings after guessing or reading a name.

The last test walks the app's mounts instead of naming the three that exist,
so a mount added later cannot reopen the same door.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from server import middleware

#: A peer on the LAN: not loopback, so `AuthMiddleware` is the gate.
REMOTE_PEER = ("192.168.1.50", 50001)
LAN_TOKEN = "lan-token-for-the-static-mounts"

MEDIA_PATHS = (
    "/images/screenshot_1700000000.png",
    "/audio/tts_1700000000_piper.wav",
)


def _get(app, path: str, *, token: str | None = None):
    async def run():
        transport = httpx.ASGITransport(app=app, client=REMOTE_PEER)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://ephe.invalid:8765"
        ) as client:
            params = {"token": token} if token else None
            return await client.get(path, params=params)

    return asyncio.run(run())


@pytest.fixture
def lan_app(tmp_path, monkeypatch):
    from server.main import create_app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("EPHE_AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.delenv("EPHE_SETUP_MODE", raising=False)

    app = create_app(lan_mode=True)
    middleware.LAN_AUTH_TOKEN = LAN_TOKEN
    (tmp_path / "images" / "screenshot_1700000000.png").write_bytes(b"PNGPROOF")
    (tmp_path / "audio" / "tts_1700000000_piper.wav").write_bytes(b"WAVPROOF")
    try:
        yield app
    finally:
        middleware.init_auth(lan_mode=False)


@pytest.mark.parametrize("path", MEDIA_PATHS)
def test_a_lan_peer_without_a_token_gets_401(lan_app, path):
    response = _get(lan_app, path)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("path", MEDIA_PATHS)
def test_the_query_token_admits_a_media_element(lan_app, path):
    """`<img>` and `<audio>` cannot send a header; the QR link carries the token."""
    response = _get(lan_app, path, token=LAN_TOKEN)

    assert response.status_code == 200, response.text
    assert response.content


@pytest.mark.parametrize("path", MEDIA_PATHS)
def test_a_wrong_query_token_gets_401(lan_app, path):
    response = _get(lan_app, path, token="not-the-token")

    assert response.status_code == 401, response.text


def test_health_stays_public(lan_app):
    response = _get(lan_app, "/api/health")

    assert response.status_code == 200, response.text


def test_every_non_frontend_mount_is_behind_the_token(lan_app):
    from starlette.routing import Mount

    # `/` is the frontend catch-all and `''` its normalised form; both are the public app,
    # not a data mount. Every other mount has to sit behind the token.
    mounts = [
        route.path
        for route in lan_app.routes
        if isinstance(route, Mount) and route.path not in {"", "/"}
    ]
    assert {"/audio", "/images", "/charts"} <= set(mounts)

    uncovered = [path for path in mounts if not path.startswith(middleware.AUTH_PREFIXES)]
    assert uncovered == []
