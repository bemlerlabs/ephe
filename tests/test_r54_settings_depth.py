"""
◑ Ephe – wave 5: settings depth (generation block in GET/POST /api/settings).
tests/test_r54_settings_depth.py

RULE: tests written BEFORE the implementation.

Pins:
1. GET /api/settings contains the `generation` block with the six keys
   (temperature, top_p, max_tokens, tool_budget, context_window,
   memory_max_entries) — defaults: 0.0 / None / None / 10 / None / 1000.
2. POST /api/settings with a generation payload persists to engine.json
   (EPHE_CONFIG_DIR isolation) and GET returns the new values.
3. Validation: tool_budget > HARD_CAP (40) → 422; temperature outside
   [0,2] → 422.
4. Env precedence: EPHE_TEMPERATURE/EPHE_TOOL_BUDGET override the
   persisted values on the read path, without changing the file.
5. clamp function: None → default, 0 → 1, 999 → 40.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch: pytest.MonkeyPatch):
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec
    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    # POST /api/settings writes the generation block into engine.json, and an
    # EngineChoice takes no empty tag since 2026-10-11: the test starts from a
    # machine that already chose an engine.
    ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="mine:work"),
        isolated / "engine.json",
    )
    for k in ("EPHE_TEMPERATURE", "EPHE_TOOL_BUDGET", "EPHE_TOP_P",
              "EPHE_MAX_TOKENS", "EPHE_CONTEXT_WINDOW",
              "EPHE_MEMORY_MAX_ENTRIES"):
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture()
def client() -> TestClient:
    from server.routes import settings
    app = FastAPI()
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


GEN_KEYS = {"temperature", "top_p", "max_tokens", "tool_budget",
            "context_window", "memory_max_entries"}


def test_get_settings_has_generation_block(client: TestClient):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "generation" in body
    assert set(body["generation"].keys()) >= GEN_KEYS


def test_generation_defaults(client: TestClient):
    g = client.get("/api/settings").json()["generation"]
    assert g["temperature"] == 0.0
    assert g["tool_budget"] == 10
    assert g["top_p"] is None
    assert g["max_tokens"] is None
    assert g["context_window"] is None
    assert g["memory_max_entries"] == 1000


def test_post_generation_persists_and_roundtrips(client: TestClient):
    payload = {"generation": {"temperature": 0.7, "top_p": 0.9,
                              "max_tokens": 2048, "tool_budget": 25,
                              "context_window": 32768,
                              "memory_max_entries": 250}}
    r = client.post("/api/settings", json=payload)
    assert r.status_code == 200
    g = r.json()["generation"]
    assert g["temperature"] == 0.7
    assert g["tool_budget"] == 25
    assert g["max_tokens"] == 2048
    # Persisted in engine.json (one source — the CLI sees the same values)
    from core.engine_config import load_engine_config
    cfg = load_engine_config()
    assert cfg is not None and cfg.generation is not None
    assert cfg.generation["temperature"] == 0.7
    # GET returns the same values back
    assert client.get("/api/settings").json()["generation"]["tool_budget"] == 25


def test_tool_budget_over_cap_rejected(client: TestClient):
    r = client.post("/api/settings", json={"generation": {"tool_budget": 999}})
    assert r.status_code == 422


def test_temperature_out_of_range_rejected(client: TestClient):
    r = client.post("/api/settings", json={"generation": {"temperature": 7.5}})
    assert r.status_code == 422


def test_env_precedence_over_persisted(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    client.post("/api/settings", json={"generation": {"temperature": 0.3,
                                                       "tool_budget": 12}})
    monkeypatch.setenv("EPHE_TEMPERATURE", "1.0")
    monkeypatch.setenv("EPHE_TOOL_BUDGET", "30")
    g = client.get("/api/settings").json()["generation"]
    assert g["temperature"] == 1.0
    assert g["tool_budget"] == 30
    # The file stayed untouched (env is only read precedence)
    from core.engine_config import load_engine_config
    assert load_engine_config().generation["temperature"] == 0.3


def test_clamp_generation_values_pure():
    from core.engine_config import clamp_generation_value
    assert clamp_generation_value("tool_budget", None) == 10
    assert clamp_generation_value("tool_budget", 0) == 1
    assert clamp_generation_value("tool_budget", 999) == 40
    assert clamp_generation_value("temperature", 9.0) == 2.0
    assert clamp_generation_value("temperature", -1.0) == 0.0
