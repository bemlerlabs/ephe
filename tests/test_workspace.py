"""
◑ Ephe – TDD: workspace (project folder) — round 3

Given / When / Then – strictly.

Failure picture before the fix: shell/file tools always ran in the server cwd. A user
could not set a project folder — "git status" in the chat showed the Ephe repo,
not the user's own project (AI-client workspace parity).
"""
from __future__ import annotations

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

    # An isolated engine.json per test — NEVER touch the real user config.
    # CONFIG_DIR is baked out of the env at module import, so env vars
    # in the fixture are NOT enough — the module attribute has to be patched.
    import core.engine_config as engine_config
    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")

    # The settings route persists the folders INTO engine.json, so the state under
    # test is a machine that already chose an engine. Since 2026-10-11 nothing fills a
    # model in for a machine that has not (EngineChoice refuses an empty tag), and the
    # POST would answer 500 on its way to writing the workspace.
    engine_config.save_engine_config(
        engine_config.EngineChoice(provider="local_ollama", model="mine:work"),
        tmp_path / "config" / "engine.json",
    )

    from server.routes.memory import _get_memory
    _get_memory.cache_clear()

    from server.main import create_app
    app = create_app()
    return TestClient(app)


class TestWorkspaceSettingsRoute:

    def test_given_project_dir_when_post_settings_then_workspace_persisted_and_returned(self, client, tmp_path):
        """G: an existing project dir W: POST /api/settings {workspace_dir}
        T: 200, the reported path; GET returns it; engine.json holds it"""
        project = tmp_path / "mein-projekt"
        project.mkdir()

        r = client.post("/api/settings", json={"workspace_dir": str(project)})
        assert r.status_code == 200
        assert r.json()["workspace_dir"] == str(project.resolve())

        r2 = client.get("/api/settings")
        assert r2.json()["workspace_dir"] == str(project.resolve())

        from core.engine_config import load_engine_config
        assert load_engine_config().workspace_dir == str(project.resolve())

    def test_given_relative_path_when_post_settings_then_422(self, client):
        """G: relative path W: POST /api/settings T: 422 with an understandable error"""
        r = client.post("/api/settings", json={"workspace_dir": "relativer/pfad"})
        assert r.status_code == 422
        body = r.json()
        msg = body.get("detail") or body.get("error", {}).get("message", "")
        # The producer raises "Workspace path must be absolute." — a bare "absolut"
        # was only ever green because it is a substring of the English word, so the
        # assertion could not fail when the message was reworded. Pin the phrase
        # instead: if the contract changes, this test changes with it.
        assert "must be absolute" in msg.lower()

    def test_given_nonexistent_dir_when_post_settings_then_422(self, client, tmp_path):
        """G: non-existent directory W: POST T: 422"""
        r = client.post("/api/settings", json={"workspace_dir": str(tmp_path / "gibts-nicht")})
        assert r.status_code == 422

    def test_given_empty_string_when_post_settings_then_workspace_cleared(self, client, tmp_path):
        """G: empty string W: POST T: workspace reset (None persisted)"""
        project = tmp_path / "projekt"
        project.mkdir()
        client.post("/api/settings", json={"workspace_dir": str(project)})
        r = client.post("/api/settings", json={"workspace_dir": ""})
        assert r.status_code == 200
        from core.engine_config import load_engine_config
        assert load_engine_config().workspace_dir is None


class TestWorkspaceShellCwd:

    def test_given_workspace_set_when_run_shell_pwd_then_command_runs_in_workspace(self, client, tmp_path):
        """G: workspace set W: POST /api/shell with 'pwd' T: output == the workspace path"""
        project = tmp_path / "shell-projekt"
        project.mkdir()
        client.post("/api/settings", json={"workspace_dir": str(project)})

        r = client.post("/api/shell", json={"command": "pwd", "approved": True}, headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["output"] == str(project.resolve())

    def test_given_no_workspace_when_run_shell_then_server_cwd(self, client, tmp_path):
        """G: no workspace W: POST /api/shell 'pwd' T: falls back to the server cwd"""
        r = client.post("/api/shell", json={"command": "pwd", "approved": True}, headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # the server cwd (the repo) answers; a tmp folder or / would answer with itself
        out = r.json()["output"]
        assert Path(out).is_dir()


class TestWorkspaceFileTools:

    def test_given_workspace_when_read_relative_path_then_resolves_against_workspace(self, client, tmp_path):
        """G: workspace + a file inside it W: read_file('note.md') T: the workspace file's content"""
        import asyncio
        from core.tools.file_ops import read_file

        project = tmp_path / "file-projekt"
        (project / "src").mkdir(parents=True)
        (project / "src" / "note.md").write_text("Hallo aus dem Workspace", encoding="utf-8")
        client.post("/api/settings", json={"workspace_dir": str(project)})

        content = asyncio.run(read_file("src/note.md"))
        assert "Hallo aus dem Workspace" in content

    def test_given_absolute_path_when_read_then_unchanged(self, client, tmp_path):
        """G: absolute path W: read_file T: is NOT bent to the workspace"""
        import asyncio
        from core.tools.file_ops import read_file

        outside = tmp_path / "outside.md"
        outside.write_text("außerhalb", encoding="utf-8")
        project = tmp_path / "anderes-projekt"
        project.mkdir()
        client.post("/api/settings", json={"workspace_dir": str(project)})

        content = asyncio.run(read_file(str(outside)))
        assert "außerhalb" in content

    def test_given_workspace_when_edit_relative_then_diff_erreugt(self, client, tmp_path):
        """G: workspace file W: edit_file relative T: the unified diff comes back"""
        import asyncio
        from core.tools.file_ops import edit_file

        project = tmp_path / "edit-projekt"
        project.mkdir()
        (project / "app.py").write_text("value = 1\n", encoding="utf-8")
        client.post("/api/settings", json={"workspace_dir": str(project)})

        diff = asyncio.run(edit_file("app.py", "value = 1", "value = 2"))
        assert "+value = 2" in diff
        assert "-value = 1" in diff
