"""
◑ Ephe – TDD: GET /api/git/info (header chips, round 10)

Given / When / Then – strictly.

Purpose: AI-client parity in the top bar — workspace name, active git branch
and dirty count. Purely read-only, fixed git arguments, cwd = workspace_dir.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os
    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")

    import core.engine_config as ec
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(ec, "CONFIG_DIR", config_dir)

    from server.routes.memory import _get_memory
    _get_memory.cache_clear()

    from server.main import create_app
    app = create_app()
    return TestClient(app)


def _git_repo(tmp_path: Path, name: str) -> Path:
    ws = tmp_path / name
    ws.mkdir(parents=True)
    env_merge = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=ws, check=True,
                       capture_output=True, env={**subprocess.os.environ, **env_merge})
    git("init", "-b", "main")
    (ws / "a.txt").write_text("hallo", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-m", "init")
    return ws


def _set_workspace(tmp_path: Path, ws: Path) -> None:
    from core.engine_config import save_engine_config, EngineChoice
    save_engine_config(EngineChoice(provider="local_ollama", model="m", workspace_dir=str(ws)))


class TestGitInfo:

    def test_given_git_workspace_when_info_then_branch_and_clean_count(self, client, tmp_path):
        """G: the workspace is a git repo (clean) W: GET /api/git/info T: git=true, branch, dirty=0"""
        ws = _git_repo(tmp_path, "projekt")
        _set_workspace(tmp_path, ws)
        r = client.get("/api/git/info")
        assert r.status_code == 200
        data = r.json()
        assert data["git"] is True
        assert data["branch"] == "main"
        assert data["dirty"] == 0
        assert data["workspace"] == "projekt"

    def test_given_uncommitted_changes_when_info_then_dirty_counted(self, client, tmp_path):
        """G: an uncommitted change W: GET T: dirty == 1"""
        ws = _git_repo(tmp_path, "dirty-proj")
        (ws / "a.txt").write_text("geaendert", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/info").json()
        assert data["dirty"] == 1

    def test_given_plain_folder_when_info_then_git_false_but_workspace_named(self, client, tmp_path):
        """G: workspace without git W: GET T: git=false, empty branch, workspace name still present"""
        ws = tmp_path / "plain"
        ws.mkdir()
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/info").json()
        assert data["git"] is False
        assert data["branch"] == ""
        assert data["workspace"] == "plain"

    def test_given_missing_workspace_dir_when_info_then_no_500(self, client, tmp_path):
        """G: workspace_dir points at a missing directory W: GET T: 200, no crash.
        (save_engine_config validates and falls back to cwd — the request
        must answer stably in every case.)"""
        from core.engine_config import save_engine_config, EngineChoice
        save_engine_config(EngineChoice(
            provider="local_ollama", model="m",
            workspace_dir=str(tmp_path / "existiert-nicht")))
        r = client.get("/api/git/info")
        assert r.status_code == 200
        assert set(r.json().keys()) == {"workspace", "git", "branch", "dirty"}

class TestGitBranches:

    def test_given_two_branches_when_list_then_current_and_all_returned(self, client, tmp_path):
        """G: repo with main + feature W: GET /api/git/branches T: both, current=main"""
        ws = _git_repo(tmp_path, "branchy")
        subprocess.run(["git", "branch", "feature/x"], cwd=ws, check=True, capture_output=True)
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/branches").json()
        assert data["git"] is True
        assert data["current"] == "main"
        assert sorted(data["branches"]) == ["feature/x", "main"]

    def test_given_valid_branch_when_checkout_then_switched(self, client, tmp_path):
        """G: branch feature exists W: POST /api/git/checkout T: ok, current switches"""
        ws = _git_repo(tmp_path, "switchy")
        subprocess.run(["git", "branch", "feature"], cwd=ws, check=True, capture_output=True)
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/checkout", json={"branch": "feature"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert client.get("/api/git/branches").json()["current"] == "feature"

    def test_given_invalid_branch_name_when_checkout_then_400(self, client, tmp_path):
        """G: branch name with shell metacharacters W: POST T: 400 (validation)"""
        ws = _git_repo(tmp_path, "sec")
        _set_workspace(tmp_path, ws)
        for bad in ["-rf", "a;rm", "a b", "main extra"]:
            r = client.post("/api/git/checkout", json={"branch": bad})
            assert r.status_code == 400, bad

    def test_given_unknown_branch_when_checkout_then_409(self, client, tmp_path):
        """G: the branch does not exist W: POST T: 409, no create"""
        ws = _git_repo(tmp_path, "nope")
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/checkout", json={"branch": "gibts-nicht"})
        assert r.status_code == 409
        assert "gibts-nicht" not in client.get("/api/git/branches").json()["branches"]
