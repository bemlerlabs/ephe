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


def test_unknown_session_answers_empty_not_null(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    body = _client().get("/api/cell", params={"session": "nie-geboren"}).json()
    assert body["cell"]["alive"] is False
    assert body["cell"]["calls"] == 0
    assert body["cell"]["avg_ms"] is None
    # The line needs the containment fact even before a cell exists (F9).
    assert isinstance(body["cell"]["contained"], bool)


def test_recorded_run_shows_real_numbers_in_the_line(tmp_path, monkeypatch):
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


def test_getting_the_cell_does_not_extend_its_life(tmp_path, monkeypatch):
    """The endpoint is a glance, not a use — otherwise the UI could keep a cell from
    starving by the very act of looking at it."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    cell = create_cell("s-2", ttl_seconds=600.0)
    before = cell.last_active_at
    for _ in range(3):
        _client().get("/api/cell", params={"session": "s-2"})
    assert cell.last_active_at == before


def test_blank_session_falls_back_to_default(tmp_path, monkeypatch):
    """The chat register names the session with no label, 'default' — the route
    has to use the same word, otherwise the UI never sees a cell."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    create_cell("default")
    record_call("default", 5.0)
    cell = _client().get("/api/cell").json()["cell"]
    assert cell["alive"] is True and cell["calls"] == 1
