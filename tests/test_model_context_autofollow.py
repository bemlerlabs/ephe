"""
tests/test_model_context_autofollow.py — the switch asks the engine for its window.

Dynamic default (owner decision 2026-11-12): selecting a model takes that model's
maximum supported window as the context window automatically. The switch routes
(POST /api/settings and PUT /api/model/provider) probe /v1/models for the engine they
just made active and answer with its number — every later meter, compaction check and
chat turn reads that number from the probe cache. A probe failure never fails the
switch, and the fallback order (env > cache > tier > legacy) stays intact.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

    _CONTEXT_WINDOW_CACHE.clear()
    yield
    _CONTEXT_WINDOW_CACHE.clear()


def _client():
    from server.main import create_app

    return TestClient(create_app())


def test_put_provider_answers_with_the_engine_reported_window(monkeypatch):
    """GIVEN the user switches to an OpenAI-compatible engine whose /v1/models
    reports max_model_len=229376
    WHEN the switch is applied
    THEN the response carries that window and the probe cache holds it — so the
    next context/budget answers with the new engine's maximum, not the old one's."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    client = _client()

    async def fake_probe(active):
        from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

        _CONTEXT_WINDOW_CACHE[(active.base_url, active.model)] = 229376
        return 229376

    with patch("server.routes.model_provider._active_context_window", new=fake_probe):
        response = client.put(
            "/api/model/provider",
            json={
                "provider": "openai_compatible",
                "model": "probe-me",
                "base_url": "http://engine.test:9999/v1",
                "confirm_online": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["context_window"] == 229376

    from server.routes.context import _resolve_window

    window, source = _resolve_window()
    assert (window, source) == (229376, "engine")


def test_put_provider_switch_survives_a_failing_probe(monkeypatch):
    """GIVEN the engine cannot be reached for its window
    WHEN the switch is applied
    THEN the switch still succeeds with context_window null — the window question
    is the meter's, never a reason the engine choice cannot happen."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    client = _client()

    async def failing_probe(active):
        raise RuntimeError("engine unreachable")

    with patch("server.routes.model_provider._active_context_window", new=failing_probe):
        response = client.put(
            "/api/model/provider",
            json={
                "provider": "openai_compatible",
                "model": "unreachable-me",
                "base_url": "http://engine.test:9998/v1",
                "confirm_online": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["context_window"] is None


def test_settings_post_answers_with_the_probed_window(monkeypatch):
    """GIVEN the composer's model chip switches the engine through the settings
    route (the POST /api/settings path the PWA model tab uses)
    WHEN the provider block is applied
    THEN the response carries the window the probe produced for the new engine."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    client = _client()

    async def fake_probe(active):
        return 1048576

    with patch("server.routes.model_provider._active_context_window", new=fake_probe):
        response = client.post(
            "/api/settings",
            json={
                "provider": {
                    "type": "openai_compatible",
                    "model": "settings-me",
                    "endpoint": "http://engine.test:9997/v1",
                }
            },
        )

    assert response.status_code == 200
    assert response.json()["context_window"] == 1048576
