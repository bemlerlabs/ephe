"""Task #80 — every refusal from /api/file carries a reason_code the surface can translate.

The file route used to answer with bare `HTTPException(detail="...")`, which is a dead end
for the surface: no code to look up, no sentence in the reader's own language, no next
step. Every other route in this server uses the coded `Refused` envelope; the file route
now does too.

One guard (`_guarded_file`) decides whether a path may be read. The four refusal codes
map to the four ways that guard can say no:

* `file_path_not_allowed` — outside the artifact scope: the workspace and its output
  folder (the narrow whitelist #120 put in place of the kernel's HOME + subfolders + tmp)
* `file_path_protected` — credential-shaped name or system file
* `file_not_found` — no such file, or a relative name that resolved nowhere
* `file_too_large` — above the preview byte ceiling

The preview door uses the same guard, so it answers with the same codes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    yield config


@pytest.fixture()
def client(device):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client


class TestFileRouteCodedRefusals:
    """Every refusal from /api/file carries a reason_code the surface can translate."""

    def test_path_outside_whitelist_answers_403_with_code(self, client, monkeypatch, tmp_path):
        """GIVEN /etc/passwd
        WHEN GET /api/file
        THEN 403 + reason_code='file_path_not_allowed'."""
        r = client.get("/api/file", params={"path": "/etc/passwd"})
        assert r.status_code == 403
        body = r.json()
        assert body["error"]["reason_code"] == "file_path_not_allowed"

    def test_credential_shaped_file_answers_403_with_code(
        self, client, monkeypatch, tmp_path
    ):
        """GIVEN .env in allowed root
        WHEN GET /api/file
        THEN 403 + reason_code='file_path_protected'."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".env").write_text("API_KEY=x")
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [home]
        )
        r = client.get("/api/file", params={"path": str(home / ".env")})
        assert r.status_code == 403
        assert r.json()["error"]["reason_code"] == "file_path_protected"

    def test_missing_file_answers_404_with_code(self, client, monkeypatch, tmp_path):
        """GIVEN nonexistent path
        WHEN GET /api/file
        THEN 404 + reason_code='file_not_found'."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        r = client.get("/api/file", params={"path": str(tmp_path / "ghost.txt")})
        assert r.status_code == 404
        assert r.json()["error"]["reason_code"] == "file_not_found"

    def test_relative_path_not_resolved_answers_404_with_code(
        self, client, monkeypatch, tmp_path
    ):
        """GIVEN relative path with no hit
        WHEN GET /api/file
        THEN 404 + reason_code."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        monkeypatch.setattr("server.routes.files._relative_bases", lambda: [tmp_path])
        r = client.get("/api/file", params={"path": "ghost.md"})
        assert r.status_code == 404
        assert r.json()["error"]["reason_code"] == "file_not_found"

    def test_too_large_answers_413_with_code(self, client, monkeypatch, tmp_path):
        """GIVEN file > MAX_FILE_BYTES
        WHEN GET /api/file
        THEN 413 + reason_code='file_too_large'."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        monkeypatch.setattr("server.routes.files.MAX_FILE_BYTES", 10)
        (tmp_path / "big.bin").write_bytes(b"x" * 11)
        r = client.get("/api/file", params={"path": str(tmp_path / "big.bin")})
        assert r.status_code == 413
        assert r.json()["error"]["reason_code"] == "file_too_large"

    def test_preview_door_refuses_with_same_codes(self, client, monkeypatch, tmp_path):
        """The preview route uses the same guard, so it answers with the same codes."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".env").write_text("API_KEY=x")
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [home]
        )
        for route in ("/api/file", "/api/file/preview"):
            r = client.get(route, params={"path": str(home / ".env")})
            assert r.json()["error"]["reason_code"] == "file_path_protected"
