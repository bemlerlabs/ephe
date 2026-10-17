"""
◑ Ephe – TDD: W3c Git actions (POST /api/git/add + /api/git/commit)

Given / When / Then — strictly.

Purpose: the Git tab buttons — stage (add) + commit in the workspace, following
the read-only pattern from git_info.py (argument list, no shell).
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

    # The route commits through _git_raw (server/routes/git_info.py:34), which inherits
    # os.environ — and a CI runner ships no git identity, while `git add` needs none and
    # `git commit` refuses without one. Every ubuntu leg answered 409; the macOS leg
    # passed because a developer machine has a user configured. Staging in a test also
    # has to say who commits, or the assertion depends on the host.
    for _identity_key, _identity_value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }.items():
        monkeypatch.setenv(_identity_key, _identity_value)

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


class TestGitAdd:

    def test_given_dirty_file_when_add_all_then_staged_counted(self, client, tmp_path):
        """G: repo with an unstaged a.txt W: POST /api/git/add T: ok, staged>=1"""
        ws = _git_repo(tmp_path, "addy")
        (ws / "a.txt").write_text("neu", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/add", json={})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["staged"] >= 1

    def test_given_selected_path_when_add_then_only_that_path_staged(self, client, tmp_path):
        """G: two unstaged files W: add with paths=[a.txt] T: exactly 1 staged"""
        ws = _git_repo(tmp_path, "sel")
        (ws / "a.txt").write_text("neu", encoding="utf-8")
        (ws / "b.txt").write_text("b", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/add", json={"paths": ["a.txt"]})
        assert r.status_code == 200
        assert r.json()["staged"] == 1

    def test_given_traversal_path_when_add_then_400(self, client, tmp_path):
        """G: a path containing '..' or a leading '-' W: POST T: 400"""
        ws = _git_repo(tmp_path, "sec")
        _set_workspace(tmp_path, ws)
        for bad in ["../x", "-A", "/etc/passwds", ""]:
            r = client.post("/api/git/add", json={"paths": [bad]})
            assert r.status_code == 400, bad

    def test_given_non_repo_when_add_then_409(self, client, tmp_path):
        """G: workspace without Git W: POST T: 409"""
        ws = tmp_path / "plain"
        ws.mkdir()
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/add", json={})
        assert r.status_code == 409


class TestGitCommit:

    def test_given_staged_change_when_commit_then_hash_and_clean(self, client, tmp_path):
        """G: staged a.txt W: POST /api/git/commit T: ok, non-empty hash, dirty=0"""
        ws = _git_repo(tmp_path, "commity")
        (ws / "a.txt").write_text("neu", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        added = client.post("/api/git/add", json={})
        assert added.status_code == 200, added.text
        r = client.post("/api/git/commit", json={"message": "W3c test commit"})
        # the route's 409 detail carries git's own stderr, which is the difference
        # between "the product refused" and "the runner had no commit identity"
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert len(body["hash"]) >= 7
        assert body["branch"] == "main"
        assert client.get("/api/git/info").json()["dirty"] == 0

    def test_given_empty_message_when_commit_then_400(self, client, tmp_path):
        """G: empty message W: POST T: 400"""
        ws = _git_repo(tmp_path, "empty")
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/commit", json={"message": "  "})
        assert r.status_code == 400

    def test_given_nothing_staged_when_commit_then_409(self, client, tmp_path):
        """G: clean, nothing staged W: POST T: 409 (no empty commit)"""
        ws = _git_repo(tmp_path, "cleanrepo")
        _set_workspace(tmp_path, ws)
        r = client.post("/api/git/commit", json={"message": "x"})
        assert r.status_code == 409
