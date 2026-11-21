"""Task #80 — Range requests and stat-based sizing for large files.

Starlette's FileResponse already handles Range requests automatically when the client
sends a Range header. The gap is: no HEAD endpoint for metadata, no explicit
Accept-Ranges header, and no file size in preview responses.

A HEAD request returns file metadata (size, type) without the bytes — for progress bars
and size checks. The Accept-Ranges: bytes header tells the client it may request partial
content. The size_bytes field in preview responses lets the surface show file size without
a second request.
"""
from __future__ import annotations

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


class TestFileRangeAndStat:
    """Range requests and stat-based sizing for large files."""

    def test_a_range_request_answers_206(self, client, monkeypatch, tmp_path):
        """GIVEN Range header
        WHEN GET /api/file
        THEN 206 + partial content."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        f = tmp_path / "video.mp4"
        f.write_bytes(b"0123456789" * 100)
        r = client.get(
            "/api/file", params={"path": str(f)}, headers={"Range": "bytes=0-9"}
        )
        assert r.status_code == 206
        assert r.content == b"0123456789"
        assert r.headers["content-range"].startswith("bytes 0-9/")

    def test_a_range_request_answers_accept_ranges(self, client, monkeypatch, tmp_path):
        """GIVEN any GET /api/file
        THEN Accept-Ranges: bytes header is present."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        f = tmp_path / "file.txt"
        f.write_text("hello")
        r = client.get("/api/file", params={"path": str(f)})
        assert r.headers.get("accept-ranges") == "bytes"

    def test_head_returns_size_without_body(self, client, monkeypatch, tmp_path):
        """GIVEN HEAD /api/file
        THEN 200 + Content-Length + no body."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        f = tmp_path / "data.bin"
        f.write_bytes(b"x" * 1234)
        r = client.head("/api/file", params={"path": str(f)})
        assert r.status_code == 200
        assert int(r.headers["content-length"]) == 1234
        assert r.content == b""

    def test_preview_includes_file_size(self, client, monkeypatch, tmp_path):
        """GIVEN GET /api/file/preview
        THEN response includes size_bytes from stat."""
        monkeypatch.setattr(
            "server.routes.files._get_artifact_roots", lambda: [tmp_path]
        )
        f = tmp_path / "notes.txt"
        f.write_text("hello world")
        r = client.get("/api/file/preview", params={"path": str(f)})
        body = r.json()
        assert "size_bytes" in body
        assert body["size_bytes"] == 11
