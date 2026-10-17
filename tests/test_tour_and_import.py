from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from server.routes import importer, tour

    app = FastAPI()
    app.include_router(tour.router, prefix="/api")
    app.include_router(importer.router, prefix="/api")
    return TestClient(app)


def test_tour_defaults_without_a_marker(client: TestClient) -> None:
    body = client.get("/api/tour").json()
    assert body["exists"] is False
    assert body["step"] == 0
    assert body["walked"] is False


def test_tour_round_trip_on_the_device(client: TestClient, tmp_path: Path) -> None:
    marker = {
        "step": 3,
        "walked": False,
        "skipped": False,
        "answers": {"usage": "code"},
    }
    saved = client.post("/api/tour", json=marker)
    assert saved.status_code == 200
    assert saved.json()["exists"] is True
    on_disk = json.loads((tmp_path / "tour.json").read_text(encoding="utf-8"))
    assert on_disk["step"] == 3
    read = client.get("/api/tour").json()
    assert read["exists"] is True
    assert read["answers"] == {"usage": "code"}


def test_a_corrupt_marker_is_no_marker(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "tour.json").write_text("{ not json", encoding="utf-8")
    body = client.get("/api/tour").json()
    assert body["exists"] is False
    assert body["step"] == 0


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "old-setup"
    (source / "skills" / "demo").mkdir(parents=True)
    (source / "SOUL.md").write_text("# Persona\n", encoding="utf-8")
    (source / "skills" / "demo" / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    (source / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"demo": {"url": "http://127.0.0.1:9"}}}),
        encoding="utf-8",
    )
    (source / "config.json").write_text(json.dumps({"temperature": 0.2}), encoding="utf-8")
    return source


def _select(tmp_path: Path, source: Path, token: str = "picked-1", created_at: int | None = None) -> str:
    """What the desktop shell writes after the native picker returned a folder."""
    body = {
        "path": str(source),
        "token": token,
        "created_at": int(time.time() * 1000) if created_at is None else created_at,
    }
    (tmp_path / "import-source.json").write_text(json.dumps(body), encoding="utf-8")
    return token


def test_import_plan_never_writes(client: TestClient, tmp_path: Path) -> None:
    token = _select(tmp_path, _source(tmp_path))
    response = client.post("/api/import", json={"token": token, "apply": False})
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is None
    assert body["plan"]["persona"]["found"] is True
    assert [skill["name"] for skill in body["plan"]["skills"]] == ["demo"]
    assert body["plan"]["mcp"]["found"] is True
    assert not (tmp_path / "persona.md").exists()


def test_import_apply_is_additive_and_skills_land_disabled(
    client: TestClient, tmp_path: Path
) -> None:
    token = _select(tmp_path, _source(tmp_path))
    response = client.post("/api/import", json={"token": token, "apply": True})
    assert response.status_code == 200
    applied = response.json()["applied"]
    assert applied["persona"] is True
    assert applied["skills"] == ["demo"]
    assert (tmp_path / "persona.md").read_text(encoding="utf-8") == "# Persona\n"
    state = json.loads((tmp_path / "skills_state.json").read_text(encoding="utf-8"))
    assert state["disabled"]["demo"] is True
    assert (tmp_path / "mcp.json").exists()
    assert not (tmp_path / "import-source.json").exists()


def test_import_refuses_a_missing_folder(client: TestClient, tmp_path: Path) -> None:
    token = _select(tmp_path, tmp_path / "nope")
    response = client.post("/api/import", json={"token": token, "apply": False})
    assert response.status_code == 422


def test_import_without_a_selection_is_refused(client: TestClient) -> None:
    response = client.post("/api/import", json={"token": "picked-1", "apply": False})
    assert response.status_code == 409


def test_import_wrong_token_is_refused(client: TestClient, tmp_path: Path) -> None:
    _select(tmp_path, _source(tmp_path))
    response = client.post("/api/import", json={"token": "other", "apply": False})
    assert response.status_code == 403


def test_import_expired_selection_is_refused(client: TestClient, tmp_path: Path) -> None:
    token = _select(tmp_path, _source(tmp_path), created_at=int(time.time() * 1000) - 11 * 60 * 1000)
    response = client.post("/api/import", json={"token": token, "apply": False})
    assert response.status_code == 410


def test_import_token_is_one_shot(client: TestClient, tmp_path: Path) -> None:
    token = _select(tmp_path, _source(tmp_path))
    assert client.post("/api/import", json={"token": token, "apply": True}).status_code == 200
    again = client.post("/api/import", json={"token": token, "apply": False})
    assert again.status_code == 409
