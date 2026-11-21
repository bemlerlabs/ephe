"""Wave 2 / B4 — reasoning effort exposed, unset unchanged.

The option already existed in `core/engine_config` (env key, normalizer, wire shapes)
and had no reader in the surface. It now round-trips through the generation block of
`/api/settings`; unset stays the request shape every earlier version sent.
"""
from __future__ import annotations

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
    ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="mine:work"),
        isolated / "engine.json",
    )
    monkeypatch.delenv("EPHE_REASONING_EFFORT", raising=False)
    yield


@pytest.fixture()
def client() -> TestClient:
    from server.routes import settings

    app = FastAPI()
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


class TestRoundTrip:
    def test_a_chosen_value_survives_the_round_trip(self, client: TestClient):
        r = client.post("/api/settings", json={"generation": {"reasoning_effort": "high"}})
        assert r.status_code == 200, r.text
        assert client.get("/api/settings").json()["generation"]["reasoning_effort"] == "high"

    def test_unset_is_the_absence_of_the_field(self, client: TestClient):
        # Every earlier version sent no reasoning_effort at all; that is what unset
        # has to keep sending.
        assert "reasoning_effort" not in client.get("/api/settings").json()["generation"]
        from core.engine_config import read_generation_options

        assert read_generation_options()["reasoning_effort"] is None

    def test_clearing_it_again_removes_the_field(self, client: TestClient):
        client.post("/api/settings", json={"generation": {"reasoning_effort": "low"}})
        assert client.get("/api/settings").json()["generation"]["reasoning_effort"] == "low"
        # The panel sends the block without the key when the first option is chosen.
        client.post("/api/settings", json={"generation": {"temperature": 0.2}})
        assert "reasoning_effort" not in client.get("/api/settings").json()["generation"]

    def test_the_engine_vocabulary_passes_through(self, client: TestClient):
        # The normalizer is a pass-through on purpose: the engine's own set can grow.
        for value in ("none", "medium", "high", "xhigh"):
            client.post("/api/settings", json={"generation": {"reasoning_effort": value}})
            assert (
                client.get("/api/settings").json()["generation"]["reasoning_effort"] == value
            )

    def test_the_request_carries_no_field_until_it_is_set(self, monkeypatch):
        # The wire shape is the promise: `thinking_request_fields` returns only what
        # was configured, so an unset option adds nothing to the request body.
        from core.engine_config import read_generation_options
        from core.model_provider import thinking_request_fields

        options = read_generation_options()
        assert thinking_request_fields(options, "http://127.0.0.1:8000/v1") == {}
