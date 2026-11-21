"""W19 — the setup onboarding can be skipped (no silent engine default).

The user can finish onboarding WITHOUT an engine choice: POST /setup/skip
sets a marker (``~/.ephe/setup.json``), the PWA gate lets them into the
chat — which stays fail-closed (409 setup_required, see test_w19_setup_start).
The marker falls away as soon as an engine is chosen (POST /settings) or the
user resets the setup (POST /setup/reset). NO silent local_ollama
default — the skip is a documented, deliberate decision.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _isolated_config(tmp_path, monkeypatch):
    import core.engine_config as ec

    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)
    return cfg


@pytest.fixture
def client(_isolated_config):
    from server.main import app

    with TestClient(app) as c:
        yield c


def test_setup_status_reports_skip_field(client, _isolated_config):
    status = client.get("/api/setup/status").json()
    assert "skipped" in status
    assert status["skipped"] is False


def test_skip_marks_and_reset_clears(client, _isolated_config):
    r = client.post("/api/setup/skip")
    assert r.status_code == 200
    assert r.json() == {"configured": False, "skipped": True}
    # The marker exists physically (SSOT ~/.ephe/setup.json).
    marker = _isolated_config / "setup.json"
    assert marker.exists() and json.loads(marker.read_text(encoding="utf-8"))["skipped"] is True
    # Status reports the skip — the PWA gate lets the user into the chat.
    status = client.get("/api/setup/status").json()
    assert status["configured"] is False
    assert status["skipped"] is True

    # A reset (or a new engine pick) lifts the skip again.
    r = client.post("/api/setup/reset")
    assert r.json() == {"configured": False, "skipped": False}
    assert not marker.exists()
    assert client.get("/api/setup/status").json()["skipped"] is False


def test_engine_pick_clears_skip_marker(client, _isolated_config):
    client.post("/api/setup/skip")
    r = client.post(
        "/api/settings",
        json={"provider": {"type": "local_ollama", "model": "gemma4:12b"}},
    )
    assert r.status_code == 200
    assert not (_isolated_config / "setup.json").exists()
    status = client.get("/api/setup/status").json()
    assert status["configured"] is True
    assert status["skipped"] is False


def test_an_incomplete_persisted_engine_cannot_be_skipped_into_chat(client, _isolated_config):
    """GIVEN engine.json names openai_compatible without api_url
    WHEN the user asks to skip onboarding
    THEN the gate reports configured=false and skipped=false, so the setup page
    opens instead of a chat that can only say Disconnected."""
    from core.engine_config import EngineChoice, save_engine_config

    save_engine_config(
        EngineChoice("openai_compatible", "m", None),
        _isolated_config / "engine.json",
    )
    client.post("/api/setup/skip")

    status = client.get("/api/setup/status").json()
    assert status["configured"] is False
    assert status["skipped"] is False


def test_corrupt_skip_marker_reads_as_not_skipped(client, _isolated_config):
    """A corrupt marker reads like no marker at all — the gate still decides."""
    _isolated_config.mkdir(parents=True, exist_ok=True)
    (_isolated_config / "setup.json").write_text("{not json", encoding="utf-8")
    assert client.get("/api/setup/status").json()["skipped"] is False
