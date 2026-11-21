"""R26: Shell API — system metrics + workspace project listing.

Data sources for the TopBar (CPU/Mem/Disk/Uptime) and the sidebar
PROJEKTE tree / welcome cards:

- GET /api/system/metrics: psutil preferred (main dependency), graceful
  degradation without it (disk via shutil, cpu/mem honestly reported as
  unavailable — never fabricated).
- GET /api/projects: project discovery rooted at the active workspace
  (preferred) plus default roots.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    # Isolated engine.json per test — NEVER touch the real user config.
    # CONFIG_DIR is baked from the env at module import time, so patching the
    # env var here would be too late; the module attribute must be patched.
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")
    # A chosen engine, because POST /api/settings writes the workspace into
    # engine.json and EngineChoice takes no empty tag since 2026-10-11.
    engine_config.save_engine_config(
        engine_config.EngineChoice(provider="local_ollama", model="mine:work"),
        tmp_path / "config" / "engine.json",
    )
    from server.main import create_app

    return TestClient(create_app())


def _seed_workspace(tmp_path: Path) -> Path:
    """Create a workspace containing two discoverable projects."""
    ws = tmp_path / "workroot"
    for name in ("proj-alpha", "proj-beta"):
        proj = ws / name
        proj.mkdir(parents=True)
        (proj / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (proj / ".git").mkdir()
        (proj / "README.md").write_text("demo", encoding="utf-8")
    # Noise: plain directory without markers must not be detected
    (ws / "not-a-project").mkdir()
    return ws


class TestSystemMetrics:
    def test_metrics_shape_with_psutil(self, client):
        pytest.importorskip("psutil", reason="psutil is a main dependency; only degradation path is testable without it")
        resp = client.get("/api/system/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert 0 <= body["cpu_percent"] <= 100
        assert body["mem_used_mb"] >= 0
        assert 0 <= body["mem_percent"] <= 100
        assert body["disk_free_bytes"] >= 0
        assert 0 <= body["disk_percent"] <= 100
        assert body["uptime_s"] >= 0

    def test_metrics_degrades_without_psutil(self, client, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil" or name.startswith("psutil."):
                raise ImportError("psutil disabled for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        resp = client.get("/api/system/metrics")
        assert resp.status_code == 200
        body = resp.json()
        # Disk is always available (shutil); cpu/mem honestly unavailable
        assert body["available"] is False
        assert body["cpu_percent"] is None
        assert body["mem_used_mb"] is None
        assert body["disk_free_bytes"] >= 0


class TestProjectsRoute:
    def test_lists_projects_under_workspace(self, client, tmp_path, monkeypatch):
        ws = _seed_workspace(tmp_path)
        import core.engine_config as ec

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: str(ws))

        resp = client.get("/api/projects")
        assert resp.status_code == 200
        body = resp.json()
        names = [p["name"] for p in body["projects"]]
        assert "proj-alpha" in names
        assert "proj-beta" in names
        assert "not-a-project" not in names
        rec = next(p for p in body["projects"] if p["name"] == "proj-alpha")
        assert rec["path"]
        assert rec["workspace"] == str(ws)

    def test_duplicate_project_names_collapse_to_best_score(self, client, tmp_path, monkeypatch):
        """Same project name in two roots (Desktop copy vs. repo clone) must
        appear once in the sidebar, keeping the higher-scoring record."""
        ws = _seed_workspace(tmp_path)
        clone = tmp_path / "elsewhere" / "proj-alpha"
        clone.mkdir(parents=True)
        (clone / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (clone / ".git").mkdir()
        (clone / "README.md").write_text("demo", encoding="utf-8")
        (clone / "package.json").write_text('{"name": "x"}', encoding="utf-8")

        import core.engine_config as ec

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: str(ws))
        import core.project_discovery as pd

        monkeypatch.setattr(pd, "default_project_roots", lambda: [tmp_path / "elsewhere"])

        resp = client.get("/api/projects")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()["projects"]]
        assert names.count("proj-alpha") == 1

    def test_route_never_crashes_on_missing_workspace(self, client, monkeypatch):
        import core.engine_config as ec

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: str(Path("Z:/no/such/dir")))
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json()["projects"], list)


class TestWorkspaceSwitch:
    def test_workspace_dir_roundtrip_via_settings(self, client, tmp_path):
        ws = tmp_path / "switched-ws"
        ws.mkdir()
        (ws / ".gitkeep").write_text("", encoding="utf-8")
        resp = client.post("/api/settings", json={"workspace_dir": str(ws)})
        assert resp.status_code == 200
        body = resp.json()
        assert str(ws) in str(body.get("workspace_dir", ""))
        # fs route reports the new workspace
        fs = client.get("/api/fs").json()
        assert fs["workspace"] == str(ws)
