from __future__ import annotations

import json
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


def test_import_plan_never_writes(client: TestClient, tmp_path: Path) -> None:
    source = _source(tmp_path)
    response = client.post("/api/import", json={"source": str(source), "apply": False})
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
    source = _source(tmp_path)
    response = client.post("/api/import", json={"source": str(source), "apply": True})
    assert response.status_code == 200
    applied = response.json()["applied"]
    assert applied["persona"] is True
    assert applied["skills"] == ["demo"]
    assert (tmp_path / "persona.md").read_text(encoding="utf-8") == "# Persona\n"
    state = json.loads((tmp_path / "skills_state.json").read_text(encoding="utf-8"))
    assert state["disabled"]["demo"] is True
    assert (tmp_path / "mcp.json").exists()


def test_import_refuses_a_missing_folder(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/import", json={"source": str(tmp_path / "nope"), "apply": False}
    )
    assert response.status_code == 422
