"""
◑ Ephe – TDD: F-02 engine probe in GET /api/health

RULE: tests BEFORE implementation. RED first, then GREEN.
Given / When / Then, strictly.

Failure picture before the fix: with provider=openai_compatible, /api/health did not
probe AT ALL — dgx_online was always False, active_tier always "offline", even though
the engine (for instance DGX Spark/vLLM) was running. The settings health check still
showed "Backend reachable".
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    import os
    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")

    from server.routes.memory import _get_memory
    _get_memory.cache_clear()

    from server.main import create_app
    app = create_app()
    return TestClient(app)


def _openai_provider():
    from core.model_provider import ModelProviderConfig
    return ModelProviderConfig(
        provider="openai_compatible",
        model="qwen3.8-flash-next",
        base_url="http://spark-test.invalid:8888/v1",
        label="DGX Spark (vLLM)",
        offline_capable=False,
        requires_internet=True,
    )


def _refusing_response():
    """What a keyed endpoint answers an anonymous probe: 401 with a JSON error body."""
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = 401
    resp.json.return_value = {"error": {"message": "missing bearer token"}}
    return resp


class TestEngineProbeInHealth:

    def test_given_openai_engine_online_when_health_then_engine_online_true(self, client):
        """G: openai_compatible + reachable engine W: GET /api/health
        T: engine_online/dgx_online True, engine_state 'ok', active_tier 'power',
        models listed"""
        with patch("server.routes.health.get_active_provider", return_value=_openai_provider()), \
             patch("server.routes.health._quick_engine_status", new=AsyncMock(
                 return_value=(True, "engine reachable", ["qwen3.8-flash-next"], "ok", False))):
            response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["engine_online"] is True
        assert data["engine_state"] == "ok"
        assert data["dgx_online"] is True
        assert data["active_tier"] == "power"
        assert data["model_installed"] is True
        assert data["models"] == ["qwen3.8-flash-next"]

    def test_given_openai_engine_down_when_health_then_engine_online_false(self, client):
        """G: openai_compatible + dead engine W: GET /api/health
        T: engine_online False, engine_state 'unreachable', active_tier 'offline',
        the detail names the cause"""
        with patch("server.routes.health.get_active_provider", return_value=_openai_provider()), \
             patch("server.routes.health._quick_engine_status", new=AsyncMock(
                 return_value=(False, "engine unreachable: connection refused", [], "unreachable", False))):
            response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["engine_online"] is False
        assert data["engine_state"] == "unreachable"
        assert data["dgx_online"] is False
        assert data["active_tier"] == "offline"
        assert "engine unreachable" in data["detail"]

    def test_given_local_ollama_when_health_then_engine_online_mirrors_ollama(self, client):
        """G: local_ollama W: GET /api/health T: engine_online mirrors connected"""
        with patch("server.routes.health.check_ollama_connection", new=AsyncMock(
            return_value=(True, "connected", ["gemma4:12b"]))):
            response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["engine_online"] is True
        assert data["engine_state"] == "ok"


    def test_given_keyed_endpoint_when_probe_then_the_challenge_is_named(self, client):
        """G: /models answers 401 to the probe W: GET /api/health
        T: engine_online False, engine_key_challenge True and the detail naming both
        places a token can sit. Measured 2026-10-10: the 401 body is valid JSON with
        no `data`, so this probe used to report "engine reachable, model not
        listed" for an endpoint that had refused every request."""
        with patch("server.routes.health.get_active_provider", return_value=_openai_provider()), \
             patch("server.routes.health.httpx.get", return_value=_refusing_response()), \
             patch("server.routes.health._ENGINE_CACHE", {}):
            data = client.get("/api/health").json()

        assert data["engine_online"] is False
        assert data["engine_key_challenge"] is True
        assert data["engine_key_configured"] is False
        assert "~/.ephe/engine.key" in data["detail"]
        assert "EPHE_OPENAI_COMPAT_API_KEY" in data["detail"]


    def test_given_two_refused_runs_when_probe_then_missing_and_rejected_separate(self, client):
        """G: one run holds no key, the other holds a key the engine rejects
        W: GET /api/health on each
        T: `engine_key_challenge` is true for both and `engine_key_configured`
        separates them — the surface puts an action sentence on the key field, and
        "you have no key" is the wrong action text for a run that has one."""
        from dataclasses import replace

        held = replace(_openai_provider(), api_key_configured=True)
        for provider, configured in ((_openai_provider(), False), (held, True)):
            with patch("server.routes.health.get_active_provider", return_value=provider), \
                 patch("server.routes.health.httpx.get", return_value=_refusing_response()), \
                 patch("server.routes.health._ENGINE_CACHE", {}):
                data = client.get("/api/health").json()

            assert data["engine_key_challenge"] is True
            assert data["engine_key_configured"] is configured


class TestEngineProbeCache:

    def test_given_repeated_polls_when_health_then_engine_probed_once_within_ttl(self, client):
        """G: 10s health polling W: two /api/health calls within the TTL
        T: engine/models endpoint contacted ONCE only (the cache protects the engine)"""
        import json as _json
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.json.return_value = {"data": [{"id": "qwen3.8-flash-next"}]}
        _json.dumps  # (readability: the payload above is a dict, not bytes)

        with patch("server.routes.health.get_active_provider", return_value=_openai_provider()), \
             patch("server.routes.health._ENGINE_CACHE", {}), \
             patch("server.routes.health.httpx.get", return_value=resp) as http_get:
            client.get("/api/health")
            client.get("/api/health")

        assert http_get.call_count == 1

class TestQuickEngineStatus:

    def test_given_reachable_models_endpoint_when_probe_then_models_parsed(self):
        """G: the engine serves /models W: _quick_engine_status
        T: (True, detail, model_list, state='ok') — the W18/A5 three-valued result"""
        import asyncio
        from unittest.mock import MagicMock

        from server.routes.health import _quick_engine_status

        resp = MagicMock()
        resp.json.return_value = {"data": [{"id": "qwen3.8-flash-next"}, {"id": "other"}]}

        with patch("server.routes.health.httpx.get", return_value=resp), \
             patch("server.routes.health._ENGINE_CACHE", {}):
            online, detail, models, state, challenged = asyncio.run(
                _quick_engine_status("http://engine-host.example:8888/v1", "qwen3.8-flash-next")
            )

        assert online is True
        assert state == "ok"
        assert "qwen3.8-flash-next" in models
        assert "other" in models

    def test_given_waf_like_endpoint_when_probe_then_browser_user_agent_sent(self):
        """G: endpoint behind a WAF/Cloudflare (it blocks python UAs with 403)
        W: _quick_engine_status T: the request carries a browser-typical User-Agent
        (regression for the finding: opencode.ai/zen answered the urllib probe with 403,
        while the httpx chat stream reaches that same endpoint)"""
        import asyncio
        from unittest.mock import MagicMock

        from server.routes.health import _quick_engine_status

        resp = MagicMock()
        resp.json.return_value = {"data": [{"id": "m"}]}

        with patch("server.routes.health.httpx.get", return_value=resp) as http_get, \
             patch("server.routes.health._ENGINE_CACHE", {}):
            asyncio.run(_quick_engine_status("http://engine-host.example:8888/v1", "m"))

        sent_headers = http_get.call_args.kwargs["headers"]
        assert sent_headers["User-Agent"].startswith("Mozilla/5.0")
