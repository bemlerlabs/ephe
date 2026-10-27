"""R1-5 / R2-0: GET /api/cell — the lifetime line may report only what the registry knows."""
from __future__ import annotations

import pytest

from core.ephemeral_cell import (
    CELL_IDLE_TTL_SECONDS,
    create_cell,
    record_call,
    reset_cells,
)


def _client():
    from fastapi.testclient import TestClient
    from server.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_cells():
    reset_cells()
    yield
    reset_cells()


def test_unbekannte_session_antwortet_leer_statt_null(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    body = _client().get("/api/cell", params={"session": "nie-geboren"}).json()
    assert body["cell"]["alive"] is False
    assert body["cell"]["calls"] == 0
    assert body["cell"]["avg_ms"] is None
    # The line needs the containment fact even before a cell exists (F9).
    assert isinstance(body["cell"]["contained"], bool)


def test_lauf_erscheint_in_der_zeile_mit_seinen_echten_zahlen(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    create_cell("s-1")
    record_call("s-1", 120.0)
    record_call("s-1", 60.0)
    cell = _client().get("/api/cell", params={"session": "s-1"}).json()["cell"]
    assert cell["alive"] is True
    assert cell["calls"] == 2
    assert cell["avg_ms"] == 90.0
    assert cell["ttl_seconds"] == CELL_IDLE_TTL_SECONDS
    assert cell["seconds_left"] <= cell["ttl_seconds"]


def test_lesen_verlaengert_nicht(tmp_path, monkeypatch):
    """The endpoint is a glance, not a use — otherwise the UI could keep a cell from
    starving by the very act of looking at it."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    cell = create_cell("s-2", ttl_seconds=600.0)
    before = cell.last_active_at
    for _ in range(3):
        _client().get("/api/cell", params={"session": "s-2"})
    assert cell.last_active_at == before


def test_leere_session_faellt_auf_default_zurueck(tmp_path, monkeypatch):
    """The chat register names the session with no label, 'default' — the route
    has to use the same word, otherwise the UI never sees a cell."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    create_cell("default")
    record_call("default", 5.0)
    cell = _client().get("/api/cell").json()["cell"]
    assert cell["alive"] is True and cell["calls"] == 1
