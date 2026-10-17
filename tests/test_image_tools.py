"""
◑ Ephe – TDD: generate_image (user tool, review 2026-09-06).

Given / When / Then – strictly.

Purpose: the tool has to fail honestly without a configured endpoint (no simulated
image), really write b64_json AND url answers to ~/Downloads, sanitise filenames
(path traversal) and derive the /images/generations URL from all common
base_url variants. httpx is faked — no real network calls in tests.
"""
from __future__ import annotations

import base64
import sys
import types
from pathlib import Path

import pytest

from core.tools.image_tools import _generations_url, _safe_filename, generate_image


class _FakeResponse:
    def __init__(self, payload: dict | bytes):
        self._payload = payload
        self.headers: dict = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload  # type: ignore[return-value]

    @property
    def content(self) -> bytes:
        return self._payload  # type: ignore[return-value]


class _FakeAsyncClient:
    """Async context-manager stand-in for httpx.AsyncClient."""

    last_post: dict | None = None
    last_get: str | None = None

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        type(self).last_post = {"url": url, "json": json, "headers": headers}
        return _FakeResponse({"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}]})

    async def get(self, url: str):
        type(self).last_get = url
        return _FakeResponse(b"URLIMAGEBYTES")


@pytest.fixture
def fake_httpx(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.last_post = None
    _FakeAsyncClient.last_get = None
    return _FakeAsyncClient


@pytest.fixture
def tmp_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr("core.tools.image_tools._downloads", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def image_endpoint(monkeypatch):
    """Isolates the endpoint resolution: no fallback to the real engine."""
    monkeypatch.setenv("EPHE_IMAGE_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.delenv("EPHE_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("EPHE_IMAGE_MODEL", raising=False)


class TestGenerateImage:

    @pytest.mark.asyncio
    async def test_given_empty_prompt_then_honest_error(self):
        """G: empty prompt W: generate_image T: honest error message, no file"""
        out = await generate_image("   ")
        assert "image error" in out
        assert "PNG_FILE:" not in out

    @pytest.mark.asyncio
    async def test_given_no_endpoint_then_config_error_without_network(
        self, monkeypatch, tmp_downloads
    ):
        """G: no EPHE_IMAGE_* and no active engine W: call T: config error"""
        monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)

        import core.model_provider as mp

        def _boom():
            raise RuntimeError("keine Engine")

        monkeypatch.setattr(mp, "get_active_provider", _boom)
        out = await generate_image("a cat")
        assert "EPHE_IMAGE_BASE_URL" in out
        assert "PNG_FILE:" not in out

    @pytest.mark.asyncio
    async def test_given_b64_response_then_png_written_and_marker_returned(
        self, fake_httpx, tmp_downloads, image_endpoint
    ):
        """G: endpoint answers with b64_json W: generate_image T: a real PNG file + marker"""
        out = await generate_image("a cat in the woods", filename="cat.png")
        assert out.startswith("PNG_FILE:")
        path = Path(out.split(":", 1)[1])
        assert path.exists()
        assert path.read_bytes() == b"PNGDATA"
        assert fake_httpx.last_post is not None
        assert fake_httpx.last_post["url"].endswith("/v1/images/generations")

    @pytest.mark.asyncio
    async def test_given_url_response_then_bytes_downloaded(
        self, fake_httpx, tmp_downloads, image_endpoint, monkeypatch
    ):
        """G: cloud answer with data[0].url W: generate_image T: bytes loaded + written"""

        async def _post_url(self, url, json=None, headers=None):
            type(self).last_post = {"url": url}
            return _FakeResponse({"data": [{"url": "http://img.example/x.png"}]})

        monkeypatch.setattr(fake_httpx, "post", _post_url)
        out = await generate_image("a dog", filename="dog.png")
        assert out.startswith("PNG_FILE:")
        assert Path(out.split(":", 1)[1]).read_bytes() == b"URLIMAGEBYTES"
        assert fake_httpx.last_get == "http://img.example/x.png"

    @pytest.mark.asyncio
    async def test_given_auth_key_then_bearer_header_sent(
        self, fake_httpx, tmp_downloads, monkeypatch
    ):
        """G: EPHE_IMAGE_API_KEY set W: call T: Authorization header Bearer"""
        monkeypatch.setenv("EPHE_IMAGE_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("EPHE_IMAGE_API_KEY", "secret-key")
        await generate_image("a cat", filename="c.png")
        assert fake_httpx.last_post["headers"]["Authorization"] == "Bearer secret-key"


class TestSafeFilename:

    def test_given_path_traversal_then_stripped_to_name(self):
        """G: '../../etc/passwd.png' W: sanitize T: no traversal possible"""
        assert _safe_filename("../../etc/passwd.png", "x.png", ".png") == "passwd.png"

    def test_given_weird_characters_then_sanitized_and_ext_forced(self):
        """G: special characters + wrong extension W: sanitize T: only [A-Za-z0-9._-], .png forced"""
        out = _safe_filename("Mein: super Bild??", "ephe_image.png", ".png")
        assert out == "Mein_super_Bild.png"

    def test_given_empty_then_default_used(self):
        """G: empty filename W: sanitize T: default with extension"""
        assert _safe_filename("", "ephe_image.png", ".png") == "ephe_image.png"


class TestGenerationsUrl:

    def test_given_plain_base_then_appended(self):
        """G: base without a path W: resolve T: base + /images/generations"""
        assert _generations_url("http://localhost:7860") == "http://localhost:7860/images/generations"

    def test_given_v1_base_then_kept(self):
        """G: base ends on /v1 W: resolve T: /v1/images/generations"""
        assert _generations_url("http://localhost:9999/v1") == "http://localhost:9999/v1/images/generations"

    def test_given_chat_completions_then_stripped(self):
        """G: base is a chat URL W: resolve T: the chat part is removed"""
        assert (
            _generations_url("http://localhost:9999/v1/chat/completions")
            == "http://localhost:9999/v1/images/generations"
        )

    def test_given_full_url_then_unchanged(self):
        """G: base is already the generations endpoint W: resolve T: unchanged"""
        assert (
            _generations_url("http://localhost:9999/images/generations")
            == "http://localhost:9999/images/generations"
        )


class TestRegistryIntegration:

    def test_given_generate_image_when_classified_then_mutating_never_auto(self):
        """G: tool registration W: classify T: mutating + no auto-approve (network + file)"""
        from core.tools.approval import classify_tool
        from core.tools.registry import TOOL_MAP, get_tool_schemas

        assert "generate_image" in TOOL_MAP
        cls = classify_tool("generate_image")
        assert cls.is_mutating is True
        assert cls.auto_approve_by_default is False
        schemas = [s["function"]["name"] for s in get_tool_schemas()]
        assert "generate_image" in schemas
