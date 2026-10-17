"""API: /api/model/providers/probe + /api/setup/status — engine detection.

Root cause: after installation the PWA has to detect the local/external engines
so the user chooses themselves (no Ollama install forcing, no
model pull). /api/model/providers/probe checks an endpoint and lists
its models; /api/setup/status reports whether an engine was chosen.

GIVEN TestClient + isolated engine.json
WHEN  POST /api/model/providers/probe (Ollama URL, OpenAI URL)
THEN  200 + reachable/models/detail (httpx mock, no real network)

WHEN  GET /api/setup/status
THEN  configured=True (engine.json present) or False (empty config)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolated engine.json — tests never write into ~/.ephe."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec
    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    yield
    import core.model_provider as mp
    mp._ACTIVE_OVERRIDE = None


@pytest.fixture()
def client() -> TestClient:
    from server.routes import model_provider, settings
    app = FastAPI()
    app.include_router(model_provider.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


# POST /api/model/providers/probe

def test_probe_ollama_reachable_lists_models(client: TestClient):
    """GIVEN Ollama answers on /api/tags
    WHEN  probe(local_ollama, http://127.0.0.1:11434)
    THEN  reachable + model list + detail."""
    import httpx
    import server.routes.model_provider as mp

    async def fake_get(self, url, *a, **kw):
        return httpx.Response(200, json={"models": [
            {"name": "gemma4:12b"},
            {"name": "nomic-embed-text"},
        ]}, request=httpx.Request("GET", url))

    with patch("httpx.AsyncClient.get", new=fake_get):
        resp = client.post("/api/model/providers/probe", json={
            "provider": "local_ollama",
            "base_url": "http://127.0.0.1:11434",
        })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reachable"] is True
    assert "gemma4:12b" in body["models"]
    assert "11434" in body["detail"]


def test_probe_ollama_unreachable_reports_not_reachable(client: TestClient):
    """GIVEN Ollama does not answer
    WHEN  probe(custom_ollama, http://10.0.0.50:11434)
    THEN  reachable=False + empty models + error detail."""
    import httpx
    import server.routes.model_provider as mp

    async def fake_get(self, url, *a, **kw):
        raise httpx.ConnectError("connection refused")

    with patch("httpx.AsyncClient.get", new=fake_get):
        resp = client.post("/api/model/providers/probe", json={
            "provider": "custom_ollama",
            "base_url": "http://10.0.0.50:11434",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is False
    assert body["models"] == []
    assert "not reachable" in body["detail"]
    assert body["state"] == "unreachable"


def test_probe_openai_compatible_strips_v1_and_lists_models(client: TestClient):
    """GIVEN a vLLM/DGX URL with the /v1 suffix
    WHEN  probe(openai_compatible, http://host:8000/v1)
    THEN  GET http://host:8000/v1/models + reachable + ids."""
    import httpx
    seen_urls: list[str] = []

    async def fake_get(self, url, *a, **kw):
        seen_urls.append(url)
        return httpx.Response(200, json={"data": [
            {"id": "qwen38-27b-unsloth-nvfp4"},
            {"id": "deepseek-v4-flash"},
        ]}, request=httpx.Request("GET", url))

    with patch("httpx.AsyncClient.get", new=fake_get):
        resp = client.post("/api/model/providers/probe", json={
            "provider": "openai_compatible",
            "base_url": "http://10.0.0.5:8000/v1",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert "qwen38-27b-unsloth-nvfp4" in body["models"]
    assert seen_urls == ["http://10.0.0.5:8000/v1/models"]
    # W18/A5: a three-valued state for the UI (ok | busy | unreachable).
    assert body["state"] == "ok"


def test_probe_openai_compatible_sends_no_authorization_without_key(client: TestClient, monkeypatch):
    """W18/A4: without an env/config key NO credential is invented.

    GIVEN openai_compatible without a user key
    WHEN  POST /api/model/providers/probe
    THEN  no Authorization header goes out (no key literal in the code) —
          and with a key, exactly the user's."""
    import httpx

    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    seen_headers: list[dict] = []

    async def fake_get(self, url, *a, **kw):
        seen_headers.append(dict(kw.get("headers") or {}))
        return httpx.Response(200, json={"data": [{"id": "m"}]}, request=httpx.Request("GET", url))

    with patch("httpx.AsyncClient.get", new=fake_get):
        resp = client.post("/api/model/providers/probe", json={
            "provider": "openai_compatible",
            "base_url": "http://10.0.0.5:8000/v1",
        })
    assert resp.status_code == 200
    assert seen_headers == [{}], "ohne Key darf kein Authorization-Header gesendet werden"

    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "user-key")
    with patch("httpx.AsyncClient.get", new=fake_get):
        client.post("/api/model/providers/probe", json={
            "provider": "openai_compatible",
            "base_url": "http://10.0.0.5:8000/v1",
        })
    assert seen_headers[1]["Authorization"] == "Bearer user-key"


def test_probe_unknown_provider_returns_422(client: TestClient):
    """GIVEN an unknown provider type
    WHEN  probe(bogus)
    THEN  422 (validation, not a 500)."""
    resp = client.post("/api/model/providers/probe", json={"provider": "bogus"})
    assert resp.status_code == 422


# GET /api/setup/status

def test_setup_status_unconfigured_when_no_engine_json(client: TestClient):
    """GIVEN no engine.json
    WHEN  GET /api/setup/status
    THEN  configured=False → the PWA shows the engine choice."""
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert set(body) >= {"configured", "provider", "model", "url", "reachable", "available_models"}


def test_setup_status_configured_after_persisting_choice(client: TestClient, tmp_path):
    """GIVEN engine.json with the local Ollama
    WHEN  GET /api/setup/status
    THEN  configured=True + provider/model from the persisted file."""
    from core.engine_config import EngineChoice, save_engine_config, LOCAL_OLLAMA

    save_engine_config(EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b"))
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["provider"] == "local_ollama"
    assert body["model"] == "gemma4:12b"


def test_setup_status_remote_engine_reports_url(client: TestClient):
    """GIVEN engine.json with an OpenAI-compatible DGX engine
    WHEN  GET /api/setup/status
    THEN  configured=True + api_url + provider=openai_compatible."""
    from core.engine_config import EngineChoice, save_engine_config, OPENAI_COMPAT

    save_engine_config(EngineChoice(
        provider=OPENAI_COMPAT,
        model="qwen38-27b-unsloth-nvfp4",
        api_url="http://gpu-host.example:8000/v1",
    ))
    resp = client.get("/api/setup/status")
    body = resp.json()
    assert body["configured"] is True
    assert body["provider"] == "openai_compatible"
    assert body["url"] == "http://gpu-host.example:8000/v1"


# POST /api/setup/reset

def test_setup_reset_clears_engine_json(client: TestClient, tmp_path):
    """GIVEN engine.json exists
    WHEN  POST /api/setup/reset
    THEN  configured=False (file deleted, the user chooses again). The W19 skip
          marker goes with it — afterwards the gate decides again."""
    from core.engine_config import EngineChoice, load_engine_config, save_engine_config, LOCAL_OLLAMA

    save_engine_config(EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b"))
    assert load_engine_config() is not None

    resp = client.post("/api/setup/reset")
    assert resp.status_code == 200
    assert resp.json() == {"configured": False, "skipped": False}
    assert load_engine_config() is None


# Endpoint history (P6: DGX stays in the scan after a provider switch)

def test_endpoint_history_survives_provider_switch(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """GIVEN history with a DGX URL, the active engine.json points at opencode
    WHEN  _setup_candidates()
    THEN  both OpenAI-compatible URLs are candidates (the DGX is not lost)."""
    from core.engine_config import EngineChoice, save_engine_config, OPENAI_COMPAT
    from server.routes import settings as st

    st._remember_endpoint("http://dgx-host.example:8888/v1")
    save_engine_config(EngineChoice(
        provider=OPENAI_COMPAT, model="m", api_url="https://opencode.ai/zen/v1",
    ))
    urls = {c["url"] for c in st._setup_candidates() if c["provider"] == "openai_compatible"}
    assert "http://dgx-host.example:8888/v1" in urls
    assert "https://opencode.ai/zen/v1" in urls


def test_remember_endpoint_dedupes_recent_first(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """GIVEN two remembered URLs
    WHEN  the first URL is remembered again
    THEN  no duplicates, the most recently used URL stands first."""
    from server.routes import settings as st

    st._remember_endpoint("http://a.example:8888/v1")
    st._remember_endpoint("http://b.example:8888/v1")
    st._remember_endpoint("http://a.example:8888/v1")
    hist = st._load_endpoint_history()
    assert hist[0] == "http://a.example:8888/v1"
    assert len(hist) == len(set(hist)) == 2
