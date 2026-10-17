"""
tests/test_file_route.py — P2-1 artifact delivery (GET /api/file)

Security: only files from the allowed roots (the core.tools.base whitelist),
no path escape, 404 for missing ones. Relative paths resolve against the
workspace/output folder (found 2026-10-01: black preview panel).
"""
from __future__ import annotations

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
    from server.routes.memory import _get_memory
    _get_memory.cache_clear()
    from server.main import create_app
    return TestClient(create_app())


class TestFileRoute:

    def test_allowed_root_file_served(self, client, monkeypatch, tmp_path):
        """GIVEN file in an allowed root WHEN GET /api/file THEN 200 + content."""
        # Widen the whitelist to tmp_path (the test stand-in for ~/tmp)
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        f = tmp_path / "chart.svg"
        f.write_text("<svg/>", encoding="utf-8")
        r = client.get("/api/file", params={"path": str(f)})
        assert r.status_code == 200
        assert "svg" in r.headers["content-type"]
        assert r.text == "<svg/>"

    def test_served_inline_not_attachment(self, client, monkeypatch, tmp_path):
        """GIVEN artifact in an allowed root WHEN GET /api/file
        THEN Content-Disposition inline — attachment made the
        AgentPanel iframe start a download (white preview)."""
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        f = tmp_path / "qr.png"
        f.write_bytes(b"\x89PNG fake")
        r = client.get("/api/file", params={"path": str(f)})
        assert r.status_code == 200
        disposition = r.headers["content-disposition"]
        assert disposition.startswith("inline")
        assert "qr.png" in disposition

    def test_path_outside_whitelist_rejected(self, client):
        """GIVEN /etc/passwd WHEN GET /api/file THEN 403."""
        r = client.get("/api/file", params={"path": "/etc/passwd"})
        assert r.status_code == 403

    def test_relative_path_resolves_against_workspace(self, client, monkeypatch, tmp_path):
        """GIVEN a deliverable with a relative name WHEN GET /api/file THEN 200.
        Found 2026-10-01: the artifact detector reports "document.md" relative
        to the workspace — the preview iframe otherwise got 400 + a black panel."""
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        monkeypatch.setattr(
            "server.routes.files._relative_bases", lambda: [tmp_path]
        )
        f = tmp_path / "document.md"
        f.write_text("# Einkaufsliste", encoding="utf-8")
        r = client.get("/api/file", params={"path": "document.md"})
        assert r.status_code == 200
        assert "# Einkaufsliste" in r.text

    def test_relative_path_resolves_against_output_dir(self, client, monkeypatch, tmp_path):
        """GIVEN a relative artifact file in the output dir WHEN GET /api/file THEN 200."""
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        out = tmp_path / "output"
        out.mkdir()
        monkeypatch.setattr(
            "server.routes.files._relative_bases", lambda: [tmp_path / "nope", out]
        )
        f = out / "chart.svg"
        f.write_text("<svg/>", encoding="utf-8")
        r = client.get("/api/file", params={"path": "chart.svg"})
        assert r.status_code == 200

    def test_relative_path_without_hit_404(self, client, monkeypatch, tmp_path):
        """GIVEN a relative path, the file exists in no base WHEN GET THEN 404
        (instead of 400 — the user then at least sees a clear not-found message)."""
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        monkeypatch.setattr(
            "server.routes.files._relative_bases", lambda: [tmp_path]
        )
        r = client.get("/api/file", params={"path": "ghost.md"})
        assert r.status_code == 404

    def test_missing_file_404(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        r = client.get("/api/file", params={"path": str(tmp_path / "nope.txt")})
        assert r.status_code == 404

    def test_too_large_413(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "server.routes.files._get_allowed_roots", lambda: [tmp_path]
        )
        monkeypatch.setattr("server.routes.files.MAX_FILE_BYTES", 10)
        f = tmp_path / "big.bin"
        f.write_bytes(b"x" * 11)
        r = client.get("/api/file", params={"path": str(f)})
        assert r.status_code == 413
