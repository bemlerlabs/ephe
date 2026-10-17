"""tests/test_engine_persist_ssot.py — R20: ONE source for engine persistence.

POST /api/settings and PUT /api/model/provider persisted the same engine.json block
verbatim, twice. Now both go through the core helper persist_engine_choice(); this
test holds the contract (api_url only for remote providers, an identical shape out of
both routes).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    from core import engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
    from server.main import create_app

    return TestClient(create_app())


def _engine_json():
    from core import engine_config

    path = engine_config.CONFIG_DIR / "engine.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class TestEnginePersistSSOT:
    def test_given_model_provider_route_when_switched_then_engine_json_persisted(self, client):
        r = client.put(
            "/api/model/provider",
            json={"provider": "custom_ollama", "model": "llama3.1:8b", "base_url": "http://192.168.1.20:11434"},
        )
        assert r.status_code == 200
        cfg = _engine_json()
        assert cfg is not None, "THEN: PUT /model/provider persistiert engine.json (F3-Vertrag)"
        assert cfg["provider"] == "custom_ollama"
        assert cfg["api_url"] == "http://192.168.1.20:11434"

    def test_given_settings_route_when_local_provider_then_no_api_url(self, client):
        r = client.post("/api/settings", json={"provider": {"type": "local_ollama", "model": "gemma4:12b"}})
        assert r.status_code == 200
        cfg = _engine_json()
        assert cfg is not None
        assert cfg["provider"] == "local_ollama"
        assert cfg.get("api_url") is None, "THEN: lokaler Ollama hat keine api_url"

    def test_given_both_routes_then_same_helper_writes_same_shape(self, client):
        """Both routes run through persist_engine_choice — the same shape."""
        client.put(
            "/api/model/provider",
            json={"provider": "custom_ollama", "model": "mistral:7b", "base_url": "http://10.0.0.5:11434"},
        )
        first = _engine_json()
        client.post(
            "/api/settings",
            json={"provider": {"type": "custom_ollama", "model": "mistral:7b", "endpoint": "http://10.0.0.5:11434"}},
        )
        second = _engine_json()
        assert first == second, "THEN: eine Quelle, identisches Ergebnis"
