"""Task 2 TDD: the engine probe is provider-aware."""
from __future__ import annotations

import pytest

from core import chat as chat_mod
from core.chat import OllamaModelBusyError
from core.model_provider import ModelProviderConfig


async def test_openai_provider_probes_api_url_not_ollama(monkeypatch):
    """OpenAI provider: the probe hits {base_url}/models, NOT Ollama."""
    import httpx

    captured: dict = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kw):
            captured["timeout"] = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kw):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    cfg = ModelProviderConfig(
        provider="openai_compatible",
        model="qwen3.8-27b",
        base_url="http://gpu-host.example:8000/v1",
        label="Test-DGX",
        offline_capable=False,
        requires_internet=True,
    )
    state = await chat_mod._engine_reachable(cfg)
    assert state == "ok"
    assert captured["url"] == "http://gpu-host.example:8000/v1/models"


async def test_engine_probe_unreachable_returns_false(monkeypatch):
    """Connection error → 'unreachable' (engine down), no raise."""
    import httpx

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            raise httpx.ConnectError("connection refused")

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    cfg = ModelProviderConfig(
        provider="openai_compatible",
        model="qwen3.8-27b",
        base_url="http://gpu-host.example:8000/v1",
        label="Test-DGX",
        offline_capable=False,
        requires_internet=True,
    )
    state = await chat_mod._engine_reachable(cfg)
    assert state == "unreachable"


async def test_engine_probe_timeout_returns_busy(monkeypatch):
    """Probe timeout → 'busy' (engine reachable, model loading), NOT 'unreachable'."""
    import httpx

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kw):
            raise httpx.ReadTimeout("read timed out")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    cfg = ModelProviderConfig(
        provider="openai_compatible",
        model="qwen3.8-27b",
        base_url="http://gpu-host.example:8000/v1",
        label="Test-DGX",
        offline_capable=False,
        requires_internet=True,
    )
    state = await chat_mod._engine_reachable(cfg)
    assert state == "busy"


async def test_ollama_provider_uses_ollama_list(monkeypatch):
    """Ollama provider (the default): the probe still runs through Ollama .list()."""
    from unittest.mock import AsyncMock

    fake_client = AsyncMock()
    fake_client.list = AsyncMock(return_value={"models": []})
    monkeypatch.setattr(
        chat_mod.ollama, "AsyncClient", lambda host=None: fake_client
    )

    cfg = ModelProviderConfig(
        provider="local_ollama",
        model="gemma4:12b",
        base_url="http://localhost:11434",
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    )
    state = await chat_mod._engine_reachable(cfg)
    assert state == "ok"
    fake_client.list.assert_awaited()
