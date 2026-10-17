"""
◑ Ephe – TDD: GET /api/git/status + /api/git/diff (the round-G review tab)

Given / When / Then – strictly.

Purpose: the review tab in the side pane shows the workspace's working-tree changes
(file + N/M stats, expandable patch) like the reference product.
Read-only git calls with an argument list (no shell), a path guard against
traversal/absolute paths, a size cap for patches.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
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


_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}


def _git_repo(tmp_path: Path, name: str) -> Path:
    ws = tmp_path / name
    ws.mkdir(parents=True)
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=ws, check=True,
                       capture_output=True, env={**os.environ, **_ENV})
    git("init", "-b", "main")
    (ws / "a.txt").write_text("zeile1\nzeile2\n", encoding="utf-8")
    (ws / "b.md").write_text("# titel\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "init")
    return ws


def _set_workspace(tmp_path: Path, ws: Path) -> None:
    from core.engine_config import save_engine_config, EngineChoice
    save_engine_config(EngineChoice(provider="local_ollama", model="m", workspace_dir=str(ws)))


class TestGitStatusRoute:

    def test_given_modified_file_when_status_then_lists_with_numstat(self, client, tmp_path):
        """G: one tracked file changed W: GET /api/git/status T: status M with +N/-M"""
        ws = _git_repo(tmp_path, "rev")
        (ws / "a.txt").write_text("zeile1\nZEILE2 NEU\nzeile3\n", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/status", params={"staged": "false"}).json()
        assert data["git"] is True
        by_path = {c["path"]: c for c in data["changes"]}
        assert "a.txt" in by_path
        entry = by_path["a.txt"]
        assert entry["status"] == "M"
        assert entry["additions"] >= 1 and entry["deletions"] >= 1

    def test_given_untracked_file_when_status_then_counted_as_additions(self, client, tmp_path):
        """G: new untracked file (3 lines) W: GET T: status ?, additions=3"""
        ws = _git_repo(tmp_path, "untracked")
        (ws / "neu.py").write_text("a\nb\nc\n", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/status").json()
        by_path = {c["path"]: c for c in data["changes"]}
        assert "neu.py" in by_path
        assert by_path["neu.py"]["status"] == "?"
        assert by_path["neu.py"]["additions"] == 3
        assert by_path["neu.py"]["deletions"] == 0

    def test_given_deleted_file_when_status_then_marks_d(self, client, tmp_path):
        """G: tracked file deleted W: GET T: status D with deletions>0"""
        ws = _git_repo(tmp_path, "del")
        (ws / "b.md").unlink()
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/status").json()
        by_path = {c["path"]: c for c in data["changes"]}
        assert by_path["b.md"]["status"] == "D"
        assert by_path["b.md"]["deletions"] >= 1

    def test_given_staged_change_when_status_staged_then_from_index(self, client, tmp_path):
        """G: change only in the index (git add) W: GET staged=true T: listed; the unstaged view is empty"""
        ws = _git_repo(tmp_path, "staged")
        (ws / "a.txt").write_text("zeile1\nindex-anders\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=ws, check=True, capture_output=True)
        _set_workspace(tmp_path, ws)
        staged = client.get("/api/git/status", params={"staged": "true"}).json()
        assert {c["path"] for c in staged["changes"]} == {"a.txt"}
        unstaged = client.get("/api/git/status", params={"staged": "false"}).json()
        assert {c["path"] for c in unstaged["changes"]} == set()

    def test_given_plain_folder_when_status_then_git_false_empty(self, client, tmp_path):
        """G: workspace without git W: GET T: 200, git=false, changes=[]"""
        ws = tmp_path / "plain"
        ws.mkdir()
        _set_workspace(tmp_path, ws)
        data = client.get("/api/git/status").json()
        assert data["git"] is False
        assert data["changes"] == []


class TestGitDiffRoute:

    def test_given_modified_file_when_diff_then_patch_text(self, client, tmp_path):
        """G: changed file W: GET /api/git/diff?path=a.txt T: patch with @@ and a +line"""
        ws = _git_repo(tmp_path, "patch")
        (ws / "a.txt").write_text("zeile1\nzeile2\nNEUE ZEILE\n", encoding="utf-8")
        _set_workspace(tmp_path, ws)
        r = client.get("/api/git/diff", params={"path": "a.txt"})
        assert r.status_code == 200
        body = r.json()
        assert body["path"] == "a.txt"
        assert body["binary"] is False
        assert "@@" in body["diff"]
        assert "+NEUE ZEILE" in body["diff"]

    def test_given_traversal_path_when_diff_then_400(self, client, tmp_path):
        """G: traversal path W: GET T: 400, no git access"""
        ws = _git_repo(tmp_path, "trav")
        _set_workspace(tmp_path, ws)
        for bad in ["../secret", "/etc/passwd", "a/../../b"]:
            assert client.get("/api/git/diff", params={"path": bad}).status_code == 400, bad

    def test_given_dash_flag_injection_when_diff_then_400(self, client, tmp_path):
        """G: path starts with '-' (option injection) W: GET T: 400"""
        ws = _git_repo(tmp_path, "inj")
        _set_workspace(tmp_path, ws)
        assert client.get("/api/git/diff", params={"path": "--output=/tmp/x"}).status_code == 400

    def test_given_unknown_path_when_diff_then_404(self, client, tmp_path):
        """G: path without a change W: GET T: 404"""
        ws = _git_repo(tmp_path, "none")
        _set_workspace(tmp_path, ws)
        assert client.get("/api/git/diff", params={"path": "gibts-nicht.txt"}).status_code == 404

    def test_given_binary_file_when_diff_then_binary_flag_no_panic(self, client, tmp_path):
        """G: tracked binary file changed W: GET T: 200, binary=true, empty diff"""
        ws = _git_repo(tmp_path, "bin")
        (ws / "logo.png").write_bytes(bytes([0x89, 0x50, 0x4E, 0x47, 0x00, 0x01, 0x02]))
        subprocess.run(["git", "add", "logo.png"], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "bin"], cwd=ws, check=True,
                       capture_output=True, env={**os.environ, **_ENV})
        (ws / "logo.png").write_bytes(bytes([0x89, 0x50, 0x4E, 0x47, 0x00, 0x09, 0x08]))
        _set_workspace(tmp_path, ws)
        r = client.get("/api/git/diff", params={"path": "logo.png"})
        assert r.status_code == 200
        body = r.json()
        assert body["binary"] is True
        assert body["diff"] == ""
