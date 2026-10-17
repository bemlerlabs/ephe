"""
◑ Ephe – TDD: GET /api/ephemeris (S4 workbench parity)

Given / When / Then – strictly.

Purpose: make the ephemerides visible — the sky as read-only JSON
(d/h/k/n, privacy through physics). Fail-soft: a disturbance answers
with an empty sky, never with a 500.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")

    import core.engine_config as ec

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(ec, "CONFIG_DIR", config_dir)

    from server.main import create_app

    app = create_app()
    return TestClient(app)


def _write_store(tmp_path, events: list[dict]):
    """Write the ephemeris store to a known location (default_store redirected)."""
    store = tmp_path / "ephemeris.jsonl"
    with open(store, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return store


class TestEphemerisSky:
    def test_leerer_himmel_available_und_empty(self, client, tmp_path, monkeypatch):
        """Given no store / When GET /api/ephemeris / Then 200, available, empty."""
        monkeypatch.setattr(
            "core.ephemeris.default_store", lambda: tmp_path / "nicht_da.jsonl"
        )
        r = client.get("/api/ephemeris")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is True
        assert body["empty"] is True
        assert body["total"] == 0
        assert len(body["rows"]) == 7

    def test_bahnen_erscheinen_mit_spitzstunde_und_arten(self, client, tmp_path, monkeypatch):
        """Given orbits today / Then the row for today with total, peak_hour, kinds sums."""
        now = datetime.now()
        store = _write_store(
            tmp_path,
            [
                {"d": now.date().isoformat(), "h": 9, "k": "session", "n": 2},
                {"d": now.date().isoformat(), "h": 14, "k": "tool", "n": 5},
                {"d": now.date().isoformat(), "h": 14, "k": "artifact", "n": 1},
            ],
        )
        monkeypatch.setattr("core.ephemeris.default_store", lambda: store)
        r = client.get("/api/ephemeris")
        body = r.json()
        assert r.status_code == 200
        assert body["empty"] is False
        assert body["total"] == 8
        today_row = next(row for row in body["rows"] if row["d"] == now.date().isoformat())
        assert today_row["total"] == 8
        assert today_row["peak_hour"] == 14
        assert today_row["hours"] == {"9": 2, "14": 6}
        assert body["kinds"] == {"session": 2, "tool": 5, "artifact": 1}

    def test_alte_bahnen_verblasst_nur_innerhalb_der_sichtweite(self, client, tmp_path, monkeypatch):
        """Given orbits outside the line of sight / Then total counts only the horizon, faded the rest."""
        today = date.today()
        old = (today - timedelta(days=30)).isoformat()
        store = _write_store(
            tmp_path,
            [
                {"d": today.isoformat(), "h": 8, "k": "session", "n": 3},
                {"d": old, "h": 8, "k": "session", "n": 4},
                {"d": "gestern", "h": 8, "k": "session", "n": 9},  # broken line
            ],
        )
        monkeypatch.setattr("core.ephemeris.default_store", lambda: store)
        body = client.get("/api/ephemeris?days=7").json()
        assert body["total"] == 3
        # A schema-valid row with a nonsense date ("gestern") survives load()
        # and counts here as faded: 4 (outside the horizon) + 9 (no calendar date).
        assert body["faded"] == 13
        assert body["empty"] is False

    def test_days_parameter_geklemmt_und_gefiltert(self, client, tmp_path, monkeypatch):
        """Given days=1 / Then exactly one row; FastAPI refuses days>31."""
        today = date.today()
        store = _write_store(
            tmp_path,
            [
                {"d": today.isoformat(), "h": 8, "k": "session", "n": 1},
                {"d": (today - timedelta(days=3)).isoformat(), "h": 8, "k": "tool", "n": 1},
            ],
        )
        monkeypatch.setattr("core.ephemeris.default_store", lambda: store)
        body = client.get("/api/ephemeris?days=1").json()
        assert len(body["rows"]) == 1
        assert body["total"] == 1
        assert client.get("/api/ephemeris?days=99").status_code == 422

    def test_fail_soft_bei_store_stoerung(self, client, tmp_path, monkeypatch):
        """Given load() raises / Then 200 with available=False instead of 500."""
        def boom(store=None):
            raise OSError("Himmel unlesbar")

        monkeypatch.setattr("core.ephemeris.default_store", lambda: tmp_path / "x.jsonl")
        monkeypatch.setattr("core.ephemeris.load", boom)
        r = client.get("/api/ephemeris")
        assert r.status_code == 200
        body = r.json()
        assert body["available"] is False
        assert body["empty"] is True
        assert body["rows"] == []
