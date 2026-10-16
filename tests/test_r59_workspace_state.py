"""R59 — Chat workspace three-state machine (deep-settings wave, Task 4).

Header/chip state machine:
1. workspace_dir set (engine.json, the SSOT) => workspace_set=true, the chip
   shows the project name.
2. No workspace_dir => workspace_set=false, neutral "Workspace" label; the
   browsing root stays the documented CWD fallback (R26 parity with
   /api/projects — no hardcoded path).
3. "Work outside a project" (pick('')) resets the choice; browsing outside
   the allowed roots is rejected (403 — kept from the existing fs guard;
   documented deviation from the plan's 400 so the pinned security tests
   stay valid).

Deviations from the source plan, documented: persistence stays in
engine.json (a settings.json workspace_dir would create a second source of
truth), and out-of-roots stays 403.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")

    import core.engine_config as ec

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(ec, "CONFIG_DIR", config_dir)

    from server.routes.memory import _get_memory

    _get_memory.cache_clear()

    from server.main import create_app

    return TestClient(create_app())


def _set_workspace(tmp_path: Path, name: str) -> Path:
    from core.engine_config import save_engine_config, EngineChoice

    ws = tmp_path / name
    (ws / "src").mkdir(parents=True)
    (ws / "README.md").write_text("hello", encoding="utf-8")
    save_engine_config(EngineChoice(provider="local_ollama", model="m", workspace_dir=str(ws)))
    return ws


class TestWorkspaceThreeState:

    def test_state_1_workspace_set_reports_project(self, client, tmp_path):
        """G: workspace_dir saved W: GET /api/fs T: workspace_set=true + path."""
        ws = _set_workspace(tmp_path, "proj")
        r = client.get("/api/fs")
        assert r.status_code == 200
        body = r.json()
        assert body["workspace_set"] is True
        assert body["workspace"] == str(ws)

    def test_state_2_no_workspace_reports_neutral(self, client):
        """G: no workspace_dir W: GET /api/fs T: workspace_set=false, CWD mirror."""
        r = client.get("/api/fs")
        assert r.status_code == 200
        body = r.json()
        assert body["workspace_set"] is False
        # R26 parity: the reported root mirrors the process CWD fallback.
        assert Path(body["workspace"]).resolve() == Path.cwd().resolve()

    def test_state_3_out_of_roots_rejected(self, client):
        """G: absolute path outside allowed roots W: GET /api/fs T: 403."""
        r = client.get("/api/fs", params={"path": "/usr"})
        assert r.status_code == 403

    def test_work_outside_resets_to_neutral(self, client, tmp_path):
        """G: project set W: PUT settings workspace_dir='' T: neutral state."""
        _set_workspace(tmp_path, "proj")
        r = client.post("/api/settings", json={"workspace_dir": ""})
        assert r.status_code == 200
        body = client.get("/api/fs").json()
        assert body["workspace_set"] is False
