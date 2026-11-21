"""The two write sites that must reach the keychain, not only the process env.

`core/engine_config.store_engine_api_key` is the one store (keychain first, 0600
file as fallback). Both places where a user hands the engine its token used to set
`EPHE_OPENAI_COMPAT_API_KEY` and stop there: the variable answers the running
process and dies with it, so an icon-launched app started without it, and the
keychain read that `engine_api_key_for` consults stayed empty.

GIVEN a settings POST or an interactive onboarding that carries an API key
WHEN  the key is submitted
THEN  store_engine_api_key receives it, and no path is written for an absent key.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import engine_config as ec  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Keep engine.json inside the test space; the real ~/.ephe stays untouched."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    yield
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)


@pytest.fixture()
def client() -> TestClient:
    from server.routes import settings

    app = FastAPI()
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


def _record_keyring(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A keychain double that records writes and always accepts them."""
    seen: list[str] = []

    def store(token: str) -> bool:
        seen.append(token)
        return True

    monkeypatch.setattr(ec, "_store_engine_keyring", store)
    return seen


def test_settings_post_writes_the_key_into_the_keychain(client, monkeypatch):
    seen = _record_keyring(monkeypatch)
    resp = client.post("/api/settings", json={
        "provider": {"type": "openai_compatible", "model": "qwen-test",
                     "endpoint": "http://127.0.0.1:8000", "api_key": "sk-placeholder-1"},
    })
    assert resp.status_code == 200, resp.text[:200]
    assert seen == ["sk-placeholder-1"], "the keychain write site never saw the token"


def test_settings_post_without_a_key_touches_no_store(client, monkeypatch):
    """An omitted key is not a revoke: the stored token has to survive such a POST."""
    seen = _record_keyring(monkeypatch)
    resp = client.post("/api/settings", json={
        "provider": {"type": "openai_compatible", "model": "qwen-test",
                     "endpoint": "http://127.0.0.1:8000"},
    })
    assert resp.status_code == 200, resp.text[:200]
    assert seen == []


def test_settings_post_with_a_blank_key_writes_nothing(client, monkeypatch):
    """A whitespace token is no token: it must not overwrite the stored one."""
    seen = _record_keyring(monkeypatch)
    resp = client.post("/api/settings", json={
        "provider": {"type": "openai_compatible", "model": "qwen-test",
                     "endpoint": "http://127.0.0.1:8000", "api_key": "   "},
    })
    assert resp.status_code == 200, resp.text[:200]
    assert seen == []


def test_settings_post_persists_through_the_file_fallback(client, tmp_path, monkeypatch):
    """With no keyring backend the route has to reach the 0600 file the resolver reads."""
    key_file = tmp_path / "engine.key"
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)
    monkeypatch.setattr(ec, "key_file_path", lambda home=None: key_file)
    resp = client.post("/api/settings", json={
        "provider": {"type": "openai_compatible", "model": "qwen-test",
                     "endpoint": "http://127.0.0.1:8000", "api_key": "sk-fallback-1"},
    })
    assert resp.status_code == 200, resp.text[:200]
    assert key_file.read_text(encoding="utf-8") == "sk-fallback-1\n"


def _run_onboarding(answers, tmp_path, monkeypatch) -> "list[str]":
    import ephe_cli
    from core import _cli_onboarding

    monkeypatch.setattr(_cli_onboarding, "_fetch_served_models", lambda api_url: None)
    monkeypatch.setattr(_cli_onboarding, "_local_ollama_detected", lambda: False)
    seen = _record_keyring(monkeypatch)
    ephe_cli._run_engine_onboarding(
        input_fn=lambda _p: next(answers), config_path=tmp_path / "engine.json"
    )
    return seen


def test_onboarding_preset_3_writes_the_key_into_the_keychain(tmp_path, monkeypatch):
    seen = _run_onboarding(iter(["3", "http://127.0.0.1:1/v1", "sk-cli-3", "model-3"]), tmp_path, monkeypatch)
    assert seen == ["sk-cli-3"]


def test_onboarding_preset_4_writes_the_key_into_the_keychain(tmp_path, monkeypatch):
    seen = _run_onboarding(iter(["4", "https://api.example/v1", "sk-cli-4", "model-4"]), tmp_path, monkeypatch)
    assert seen == ["sk-cli-4"]


def test_onboarding_without_a_key_writes_nothing(tmp_path, monkeypatch):
    seen = _run_onboarding(iter(["3", "http://127.0.0.1:1/v1", "", "model-3"]), tmp_path, monkeypatch)
    assert seen == []
