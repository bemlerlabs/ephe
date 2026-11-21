"""
◑ Ephe – TDD: GET /api/fs (file browser, round 4)

Given / When / Then – strict.

Purpose: file explorer in the AgentPanel + workspace folder dialog. Read-only;
allowed are the standard roots (incl. the user-set workspace) plus home at
depth 1 (the starting point of the folder dialog).
"""
from __future__ import annotations

import os
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


def _set_workspace(tmp_path: Path, name: str) -> Path:
    from core.engine_config import save_engine_config, EngineChoice
    ws = tmp_path / name
    (ws / "src").mkdir(parents=True)
    (ws / "README.md").write_text("hallo", encoding="utf-8")
    save_engine_config(EngineChoice(provider="local_ollama", model="m", workspace_dir=str(ws)))
    return ws


class TestFsListing:

    def test_given_default_when_list_then_home_returned_with_root_entries(self, client, tmp_path, monkeypatch):
        """G: no path W: GET /api/fs T: 200, path==home, entries as dirs/files
        Hermetic: Path.home() points at a tmp HOME holding Documents/ — a
        CI runner guarantees no standard user folders."""
        fake_home = tmp_path / "home"
        (fake_home / "Documents").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        r = client.get("/api/fs")
        assert r.status_code == 200
        data = r.json()
        assert data["path"] == str(fake_home)
        assert isinstance(data["entries"], list)
        assert any(e["name"] == "Documents" for e in data["entries"])

    def test_given_a_symlinked_home_when_list_then_home_is_served(self, client, tmp_path, monkeypatch):
        """G: HOME resolves through a symlink (/tmp -> /private/tmp)
        W: GET /api/fs without a path
        T: 200 and the resolved home — the same directory, not a 403."""
        real = tmp_path / "real-home"
        (real / "Documents").mkdir(parents=True)
        link = tmp_path / "home-link"
        link.symlink_to(real)
        monkeypatch.setattr(Path, "home", lambda: link)
        r = client.get("/api/fs")
        assert r.status_code == 200
        assert r.json()["path"] == str(real)

    def test_given_allowed_root_dir_when_list_then_entries_sorted_dirs_first(self, client, tmp_path):
        """G: directory inside an allowed root W: listing T: dirs first, files with size"""
        root = tmp_path / "roots" / "Documents"
        (root / "zFolder").mkdir(parents=True)
        (root / "a.txt").write_text("x", encoding="utf-8")
        # tmp_path sits under /tmp → allowed root
        r = client.get("/api/fs", params={"path": str(root)})
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert [e["name"] for e in entries] == ["zFolder", "a.txt"]
        assert entries[0]["type"] == "dir"
        assert entries[1]["type"] == "file" and entries[1]["size"] == 1

    def test_given_hidden_entries_when_list_then_skipped(self, client, tmp_path):
        """G: dotfiles in the folder W: listing T: hidden entries are missing"""
        root = tmp_path / "hidden-test"
        root.mkdir()
        (root / ".secret").write_text("x", encoding="utf-8")
        (root / "sichtbar.md").write_text("y", encoding="utf-8")
        r = client.get("/api/fs", params={"path": str(root)})
        names = [e["name"] for e in r.json()["entries"]]
        assert names == ["sichtbar.md"]

    def test_given_workspace_dir_when_list_then_allowed_even_outside_standard_roots(self, client, tmp_path):
        """G: workspace outside the standard roots W: GET /api/fs T: 200 (the workspace root counts)"""
        # /tmp is itself a root; to test 'outside' the workspace is placed
        # directly under home (home subfolders are NOT automatically roots).
        home = Path.home()
        ws = home / f".ephe-fs-test-{os.getpid()}"
        (ws / "src").mkdir(parents=True)
        try:
            from core.engine_config import save_engine_config, EngineChoice
            save_engine_config(EngineChoice(provider="local_ollama", model="m", workspace_dir=str(ws)))
            r = client.get("/api/fs", params={"path": str(ws)})
            assert r.status_code == 200
            assert any(e["name"] == "src" for e in r.json()["entries"])
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)

    def test_given_path_outside_roots_when_list_then_403(self, client):
        """G: path outside every root (e.g. /etc) W: GET T: 403"""
        r = client.get("/api/fs", params={"path": "/etc"})
        assert r.status_code == 403

    def test_given_a_protected_root_when_list_then_403(self, client, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "id_rsa").write_text("fixture", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(Path, "home", lambda: home)
        r = client.get("/api/fs", params={"path": str(home / ".ssh")})
        assert r.status_code == 403

    def test_given_missing_dir_when_list_then_404(self, client, tmp_path):
        """G: nonexistent directory inside a root W: GET T: 404"""
        r = client.get("/api/fs", params={"path": str(tmp_path / "roots" / "gibts-nicht")})
        assert r.status_code == 404

    def test_given_relative_path_when_list_then_400(self, client):
        """G: relative path W: GET T: 400"""
        r = client.get("/api/fs", params={"path": "relative/dir"})
        assert r.status_code == 400
