"""Task #81/#120 — `GET /api/file` reads the scope the surface shows.

The kernel tool path (`core.tools.base._get_allowed_roots`) allows HOME, its subfolders and
tmp, because a tool that reads a user file needs that reach. The artifact route carries the
same sentence as the tool (`_guarded_file`), and the surface it feeds says "workspace". The
two answers to "may this path be read" are two scopes, and a client hitting
`/api/file?path=/Users/<name>/private.txt` got the wide one.

Task #120 ports main's narrowing into this tree: the route answers from the workspace plus
the configured output folder (a plugin call adds that bundle's resolved data roots, the same
list `core.tools.base` hands the confined worker). The kernel path stays wide. The four
refusal sites, the de/en bundles and `server/refusals.REASONS` name those two folders, so
the sentence the reader gets is the scope the guard applied.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    from server.main import create_app

    return TestClient(create_app())


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """A home with a project folder inside it, and the two files the two scopes differ on."""
    home = tmp_path / "home"
    workspace = home / "projects" / "ephe"
    workspace.mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EPHE_OUTPUT_DIR", str(out))
    return home, workspace, out


class TestArtifactRouteScope:
    def test_a_home_file_outside_the_workspace_is_refused(self, client, scope):
        """GIVEN ~/private_notes.txt, workspace = ~/projects/ephe
        WHEN GET /api/file
        THEN 403 + reason_code=file_path_not_allowed."""
        home, _workspace, _out = scope
        diary = home / "private_notes.txt"
        diary.write_text("diary entry", encoding="utf-8")

        answer = client.get("/api/file", params={"path": str(diary)})

        assert answer.status_code == 403
        assert answer.json()["error"]["reason_code"] == "file_path_not_allowed"

    def test_a_tmp_file_outside_the_workspace_is_refused(self, client, scope, tmp_path):
        """GIVEN a file in the kernel's tmp root, workspace elsewhere
        WHEN GET /api/file
        THEN 403 — the tmp root belongs to the tool path."""
        scratch = tmp_path / "temp_data.txt"
        scratch.write_text("temporary", encoding="utf-8")

        answer = client.get("/api/file", params={"path": str(scratch)})

        assert answer.status_code == 403
        assert answer.json()["error"]["reason_code"] == "file_path_not_allowed"

    def test_a_workspace_artifact_is_served(self, client, scope):
        """GIVEN chart.svg inside the workspace
        WHEN GET /api/file
        THEN 200 + the bytes."""
        _home, workspace, _out = scope
        chart = workspace / "chart.svg"
        chart.write_text("<svg/>", encoding="utf-8")

        answer = client.get("/api/file", params={"path": str(chart)})

        assert answer.status_code == 200
        assert answer.text == "<svg/>"

    def test_an_output_folder_artifact_is_served(self, client, scope):
        """GIVEN document.md in the output folder, which sits outside the workspace
        WHEN GET /api/file
        THEN 200 — the folder is the second half of the declared scope."""
        _home, _workspace, out = scope
        doc = out / "document.md"
        doc.write_text("# Goals", encoding="utf-8")

        answer = client.get("/api/file", params={"path": str(doc)})

        assert answer.status_code == 200

    def test_the_preview_door_refuses_what_the_streaming_door_refuses(self, client, scope):
        """One guard, two doors: a path the bytes door will not read, the renderer will not open."""
        home, _workspace, _out = scope
        diary = home / "private_notes.txt"
        diary.write_text("diary entry", encoding="utf-8")

        answer = client.get("/api/file/preview", params={"path": str(diary)})

        assert answer.status_code == 403
        assert answer.json()["error"]["reason_code"] == "file_path_not_allowed"


class TestRefusalCopyNamesTheScope:
    """#120's second half: the sentence matches the guard that produced it."""

    def test_the_english_template_names_the_two_folders_it_reads(self):
        from server.refusals import REASONS

        text = REASONS["file_path_not_allowed"][1]
        assert "workspace" in text and "output" in text
        for wide in ("HOME", "Desktop", "Documents", "Downloads", "tmp"):
            assert wide not in text, f"the copy still offers {wide}"

    @pytest.mark.parametrize(
        "bundle,scope_words",
        [("en", ("workspace", "output")), ("de", ("Arbeitsbereich", "Ausgabe"))],
    )
    def test_both_reader_bundles_name_the_scope_they_enforce(self, bundle, scope_words):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        text = json.loads(
            (root / "app" / "src" / "locales" / f"{bundle}.json").read_text(encoding="utf-8")
        )["serverError"]["file_path_not_allowed"]
        for folder in scope_words:
            assert folder in text, f"{bundle}.json lost {folder}"
        wide = ("HOME", "Desktop", "Downloads", "tmp")
        extra = ("Documents",) if bundle == "en" else ("Dokumente",)
        for word in (*wide, *extra):
            assert word not in text, f"{bundle}.json still offers {word}"
