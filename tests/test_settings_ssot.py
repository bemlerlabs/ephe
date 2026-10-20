"""API: /api/settings is the single source of truth for the PWA.

Root-cause fix: the frontend (ChatInput, SettingsPanel) calls getSettings()
→ GET /api/settings. This route did NOT exist before → 404 →
catch(() => {}) → the hardcoded gemma4:e4b stayed in place although the
engine uses Qwen/DGX.

GIVEN a server with a Qwen engine (env: openai_compatible)
WHEN  GET /api/settings
THEN  200 + provider.model = qwen (not 404, not gemma4:e4b)

WHEN  POST /api/settings (local_ollama + model)
THEN  the active provider switches + engine.json persists
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.model_provider import set_active_provider


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolated engine.json — the test must NOT write to the REAL config
    (~/.ephe) (deployment readiness: tests have no side effects on the
    user state). EPHE_CONFIG_DIR is the genuine, product-side
    isolation mechanism (also used in the E2E test)."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    # CONFIG_DIR is bound at import time — patch the module attribute directly
    # so save_engine_config()/default_config_path() use the isolation.
    import core.engine_config as ec
    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    # Starting state: local Ollama (the offline-first standard).
    set_active_provider(provider="local_ollama")
    yield
    set_active_provider(provider="local_ollama")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Rule out DGX/network calls inside the test.
    monkeypatch.delenv("EPHE_HEALTH_DEEP", raising=False)
    from server.routes import settings
    app = FastAPI()
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


def test_get_settings_returns_active_engine_not_404(client: TestClient):
    """GIVEN a Qwen engine (env: openai_compatible)
    WHEN GET /api/settings
    THEN 200 + provider.model = qwen (it would have been 404 before)."""
    set_active_provider(
        provider="openai_compatible",
        model="qwen38-27b-unsloth-nvfp4",
        base_url="http://127.0.0.1:8000",
    )
    resp = client.get("/api/settings")
    assert resp.status_code == 200, f"erwartet 200 (SSOT), got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["provider"]["model"] == "qwen38-27b-unsloth-nvfp4"
    assert body["provider"]["type"] == "openai_compatible"


def test_get_settings_default_is_local_ollama(client: TestClient):
    """GIVEN no engine selection
    WHEN GET /api/settings
    THEN 200 + the local Ollama default (offline-first)."""
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["provider"]["type"] == "local_ollama"


def test_post_settings_switches_provider(client: TestClient):
    """GIVEN local Ollama
    WHEN POST /api/settings (openai_compatible + qwen)
    THEN the active provider switches + gets persisted (engine.json)."""
    set_active_provider(provider="local_ollama")
    resp = client.post("/api/settings", json={
        "provider": {"type": "openai_compatible", "model": "qwen38-27b-unsloth-nvfp4",
                     "endpoint": "http://127.0.0.1:8000"},
    })
    assert resp.status_code == 200, resp.text[:200]
    assert resp.json()["provider"]["model"] == "qwen38-27b-unsloth-nvfp4"
    # persisted: the ISOLATED engine.json now shows Qwen (CLI + PWA share
    # the source). default_config_path() reads the patched CONFIG_DIR
    # (isolation) — proving that the persistence went into the test space and the
    # REAL ~/.ephe/engine.json stayed untouched (no test side effects).
    from core.engine_config import default_config_path, load_engine_config
    cfg = load_engine_config()
    assert cfg is not None and cfg.provider == "openai_compatible"
    assert default_config_path().parent.name == "config"  # isolation, not ~/.ephe


def test_run_server_bootstrap_loads_engine_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """GIVEN engine.json with Qwen + a direct server start (no env beforehand)
    WHEN run_server._bootstrap_engine_choice()
    THEN EPHE_MODEL_PROVIDER gets set (the PWA uses Qwen, not Ollama)."""
    from core.engine_config import EngineChoice, save_engine_config
    # engine.json set to Qwen (as in the E2E setup)
    save_engine_config(
        EngineChoice(
            provider="openai_compatible",
            model="qwen38-27b-unsloth-nvfp4",
            api_url="http://127.0.0.1:8000",
        ),
        path=tmp_path / "engine.json",
    )
    # load_engine_config has to read the tmp file → default patch
    import core.engine_config as ec
    monkeypatch.setattr(ec, "default_config_path", lambda: tmp_path / "engine.json")

    # Do NOT set the explicit env (direct start)
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_BASE_URL", raising=False)
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL", raising=False)

    import run_server
    run_server._bootstrap_engine_choice()

    assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"
    assert os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] == "http://127.0.0.1:8000"
    assert os.environ["EPHE_OPENAI_COMPAT_MODEL"] == "qwen38-27b-unsloth-nvfp4"
    # The provider resolver now reports Qwen (not Ollama)
    from core.model_provider import set_active_provider as _reset
    set_active_provider(provider="openai_compatible", model="qwen38-27b-unsloth-nvfp4",
                        base_url="http://127.0.0.1:8000")  # session override for the next test
    from core.model_provider import _provider_from_env
    assert _provider_from_env().provider == "openai_compatible"
    assert _provider_from_env().model == "qwen38-27b-unsloth-nvfp4"


def test_bootstrap_respects_explicit_env(monkeypatch: pytest.MonkeyPatch):
    """GIVEN EPHE_MODEL_PROVIDER is already set (explicit start)
    WHEN _bootstrap_engine_choice()
    THEN the env stays unchanged (the explicit choice wins)."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    monkeypatch.setenv("EPHE_MODEL", "gemma4:12b")
    import run_server
    run_server._bootstrap_engine_choice()
    # engine.json (Qwen) is NOT pushed over it
    assert os.environ["EPHE_MODEL_PROVIDER"] == "local_ollama"
    assert os.environ["EPHE_MODEL"] == os.environ["EPHE_MODEL"] == "gemma4:12b"


def test_settings_carries_no_theme_field(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """GIVEN the product ships one ground
    WHEN GET /api/settings, then POST it a `theme`
    THEN the answer has no `theme` key and the request changes nothing.

    The theme used to round-trip through this route into `os.environ["EPHE_THEME"]`, which
    nothing read: a field the surface wrote and no consumer answered is the shape a theme
    switch returns through, so both halves are refused here.
    """
    monkeypatch.setenv("EPHE_THEME", "paper-from-a-previous-run")
    body = client.get("/api/settings").json()
    assert "theme" not in body, f"the settings answer advertises a theme: {sorted(body)}"

    posted = client.post("/api/settings", json={"theme": "light"})
    assert posted.status_code == 200, posted.text[:200]
    assert "theme" not in posted.json()
    assert os.environ["EPHE_THEME"] == "paper-from-a-previous-run", (
        "a POST wrote EPHE_THEME — the write branch came back")
