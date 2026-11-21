"""tests/test_image_config.py — R16 image-endpoint configuration

Endpoint precedence for generate_image:
  1. EPHE_IMAGE_* env vars (override everything — the deployment override)
  2. ~/.ephe/image.json (Settings UI / R16)
  3. the active chat engine (fallback, the older contract)

The Settings UI configures the image path without env vars; image.json holds an
API key, which is why it is written atomically with mode 0600.
"""
from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    from core import engine_config

    cfg_dir = tmp_path / "ephe-config"
    cfg_dir.mkdir()
    monkeypatch.setattr(engine_config, "CONFIG_DIR", cfg_dir)
    return cfg_dir


class TestImageConfigStore:
    def test_given_no_config_when_loaded_then_empty_defaults(self, config_dir):
        from core.image_config import load_image_config

        cfg = load_image_config()
        assert cfg.base_url == "" and cfg.api_key == "" and cfg.model == ""

    def test_given_saved_config_when_loaded_then_roundtrip(self, config_dir):
        from core.image_config import load_image_config, save_image_config

        save_image_config(base_url="http://127.0.0.1:8080/v1", model="sd-1.5", api_key="secret-key-123")
        cfg = load_image_config()
        assert cfg.base_url == "http://127.0.0.1:8080/v1"
        assert cfg.model == "sd-1.5"
        assert cfg.api_key == "secret-key-123"

    def test_given_saved_config_when_inspected_then_file_is_owner_only(self, config_dir):
        from core.image_config import image_config_path, save_image_config

        save_image_config(base_url="http://127.0.0.1:8080/v1")
        mode = stat.S_IMODE(image_config_path().stat().st_mode)
        assert mode == 0o600, "THEN: image.json enthält ggf. API-Keys → nur Owner"

    def test_given_non_http_base_url_when_saved_then_rejected(self, config_dir):
        from core.image_config import save_image_config

        with pytest.raises(ValueError):
            save_image_config(base_url="ftp://example.com/v1")

    def test_given_path_traversal_config_dir_when_resolved_then_within_config(self, config_dir):
        from core.image_config import image_config_path

        assert image_config_path().parent == config_dir


class TestImageEndpointPriority:
    def test_given_env_when_resolving_then_env_wins_over_config(self, config_dir, monkeypatch):
        from core.image_config import save_image_config
        from core.tools.image_tools import _image_endpoint

        save_image_config(base_url="http://127.0.0.1:8080/v1")
        monkeypatch.setenv("EPHE_IMAGE_BASE_URL", "http://env-host:9000/v1")
        base, _, _ = _image_endpoint()
        assert base == "http://env-host:9000/v1"

    def test_given_config_without_env_when_resolving_then_config_wins_over_provider(self, config_dir, monkeypatch):
        from core.image_config import save_image_config
        from core.tools.image_tools import _image_endpoint

        monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
        save_image_config(base_url="http://127.0.0.1:8080/v1", model="sd-1.5", api_key="k-123")
        base, key, model = _image_endpoint()
        assert base == "http://127.0.0.1:8080/v1"
        assert key == "k-123" and model == "sd-1.5"

    def test_given_nothing_configured_when_resolving_then_provider_fallback(self, config_dir, monkeypatch):
        from core.tools.image_tools import _image_endpoint

        monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
        base, _, _ = _image_endpoint()
        assert base, "THEN: aktive Chat-Engine bleibt der Fallback (alter Vertrag)"


@pytest.fixture
def client(config_dir, monkeypatch):
    monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
    monkeypatch.delenv("EPHE_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("EPHE_IMAGE_MODEL", raising=False)
    from server.main import create_app

    return TestClient(create_app())


class TestImageSettingsRoutes:
    def test_given_nothing_when_get_then_masked_empty(self, client):
        body = client.get("/api/settings/image").json()
        assert body["base_url"] == ""
        assert body["has_api_key"] is False
        assert "api_key" not in body, "THEN: Key wird nie im Klartext zurückgegeben"

    def test_given_put_when_get_then_saved_and_masked(self, client, config_dir):
        r = client.put(
            "/api/settings/image",
            json={"base_url": "http://127.0.0.1:8080/v1", "model": "sd-1.5", "api_key": "sk-secret-9"},
        )
        assert r.status_code == 200
        body = client.get("/api/settings/image").json()
        assert body["base_url"] == "http://127.0.0.1:8080/v1"
        assert body["has_api_key"] is True
        assert body["api_key_hint"].endswith("9") and "sk-secret" not in body["api_key_hint"]

    def test_given_put_without_api_key_when_existing_key_then_key_kept(self, client):
        client.put("/api/settings/image", json={"base_url": "http://a:1/v1", "api_key": "keep-me-1"})
        client.put("/api/settings/image", json={"base_url": "http://b:2/v1"})
        body = client.get("/api/settings/image").json()
        assert body["base_url"] == "http://b:2/v1"
        assert body["has_api_key"] is True, "THEN: an omitted key is not deleted"

    def test_given_put_empty_api_key_when_existing_key_then_key_cleared(self, client):
        client.put("/api/settings/image", json={"base_url": "http://a:1/v1", "api_key": "kill-me-1"})
        client.put("/api/settings/image", json={"base_url": "http://a:1/v1", "api_key": ""})
        assert client.get("/api/settings/image").json()["has_api_key"] is False

    def test_given_invalid_url_when_put_then_422(self, client):
        r = client.put("/api/settings/image", json={"base_url": "not-a-url"})
        assert r.status_code == 422


class TestImageEndpointProbe:
    def test_given_reachable_endpoint_when_tested_then_models_listed(self, client, monkeypatch):
        from core.image_config import save_image_config

        save_image_config(base_url="http://127.0.0.1:8080/v1")

        class _FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"id": "sd-1.5"}, {"id": "flux-schnell"}]}

        async def _fake_get(self, url, **kwargs):
            assert url.endswith("/models")
            return _FakeResponse()

        monkeypatch.setattr("httpx.AsyncClient.get", _fake_get)
        r = client.post("/api/settings/image/test")
        assert r.status_code == 200
        body = r.json()
        assert body["reachable"] is True
        assert "sd-1.5" in body["models"]

    def test_given_dead_endpoint_when_tested_then_honest_unreachable(self, client, monkeypatch):
        import httpx
        from core.image_config import save_image_config

        save_image_config(base_url="http://127.0.0.1:1/v1")

        async def _fake_get(self, url, **kwargs):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr("httpx.AsyncClient.get", _fake_get)
        r = client.post("/api/settings/image/test")
        assert r.status_code == 200
        body = r.json()
        assert body["reachable"] is False
        assert body["models"] == []


class TestDoctorImageCheck:
    """`ephe doctor` reads the image endpoint and only suggests LocalAI (opt-in)."""

    def _check(self, monkeypatch, config_dir):
        import ephe_cli

        return ephe_cli._doctor_image_endpoint()

    def test_given_reachable_explicit_endpoint_when_checked_then_ok(self, config_dir, monkeypatch):
        from core.image_config import save_image_config

        save_image_config(base_url="http://127.0.0.1:9999/v1")

        class _Resp:
            status_code = 200

        monkeypatch.setattr(
            "httpx.get", lambda url, **kw: _Resp()
        )
        ok, detail = self._check(monkeypatch, config_dir)
        assert ok is True and "explicitly configured" in detail

    def test_given_localai_on_default_port_when_checked_then_suggested_not_activated(self, config_dir, monkeypatch):
        monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
        # the chat-engine fallback does NOT answer; LocalAI on :8080 does.
        calls = []

        def _fake_get(url, **kw):
            calls.append(url)
            class _Resp:
                status_code = 200
            if "127.0.0.1:8080" in url:
                return _Resp()
            raise ConnectionError("down")

        monkeypatch.setattr("httpx.get", _fake_get)
        ok, detail = self._check(monkeypatch, config_dir)
        assert ok is False, "THEN: Vorschlag ist opt-in — kein stiller Config-Write"
        assert "detected" in detail and "8080" in detail
        from core.image_config import load_image_config
        assert load_image_config().base_url == "", "THEN: doctor schreibt nie Config"

    def test_given_nothing_reachable_when_checked_then_honest_fail(self, config_dir, monkeypatch):
        monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
        monkeypatch.setattr("httpx.get", lambda url, **kw: (_ for _ in ()).throw(ConnectionError("down")))
        ok, detail = self._check(monkeypatch, config_dir)
        assert ok is False and "not reachable" in detail
