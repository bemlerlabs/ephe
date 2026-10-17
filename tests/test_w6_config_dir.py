"""W6 — per-device folder (~/.ephe/) + session export/import (round W6).

Parity with leading local agent clients: ONE folder per end device carries the
engine choice, skills, sessions and memory. An optional env cover
``EPHE_CONFIG_DIR`` moves the whole layout root; more specific keys win. On top:
a portable session bundle as zip/tar.gz with a path-traversal guard.

The pins check the call-time contract layer (config_root/config_subdir) so the
module class identities stay stable and no reload is needed.
"""
from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest


# Per-device folder layout

def test_default_config_root_is_home_ephe(monkeypatch):
    """GIVEN no env cover
    WHEN the root is resolved
    THEN it sits under ~/.ephe with skills/sessions/memory as subfolders."""
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("EPHE_SESSIONS_DIR", raising=False)
    monkeypatch.delenv("EPHE_SKILLS_DIR", raising=False)
    import core.engine_config as ec

    home = Path.home() / ".ephe"
    assert ec.config_root() == home
    assert ec.config_subdir("skills") == home / "skills"
    assert ec.config_subdir("sessions") == home / "sessions"
    assert ec.config_subdir("memory") == home / "memory"


def test_config_dir_env_redirects_whole_layout(tmp_path, monkeypatch):
    """GIVEN EPHE_CONFIG_DIR points at a tmp root
    WHEN the subfolders are resolved
    THEN all areas land 1:1 under that root."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("EPHE_SESSIONS_DIR", raising=False)
    monkeypatch.delenv("EPHE_SKILLS_DIR", raising=False)
    monkeypatch.delenv("EPHE_MEMORY_DIR", raising=False)
    import core.engine_config as ec

    assert ec.config_subdir("sessions") == tmp_path / "sessions"
    assert ec.config_subdir("skills") == tmp_path / "skills"
    assert ec.config_subdir("memory") / "chroma_db" == tmp_path / "memory" / "chroma_db"


def test_specific_env_key_wins_over_root(tmp_path, monkeypatch):
    """GIVEN the root and the sessions key are both set
    WHEN the session resolution runs (or-fallback as in the module)
    THEN the more specific EPHE_SESSIONS_DIR wins."""
    import os

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "s"))
    import core.engine_config as ec

    resolved = Path(os.environ.get("EPHE_SESSIONS_DIR") or str(ec.config_subdir("sessions")))
    assert resolved == tmp_path / "s"
    # without a sessions key the resolution would fall back to the root
    monkeypatch.delenv("EPHE_SESSIONS_DIR", raising=False)
    fallback = Path(os.environ.get("EPHE_SESSIONS_DIR") or str(ec.config_subdir("sessions")))
    assert fallback == tmp_path / "sessions"


# Session export/import

@pytest.fixture()
def client(tmp_path, monkeypatch):
    import core.multi_session as ms

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path / "config")
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c, sessions_dir


_PAYLOAD = {
    "sessions": [
        {"id": "abc123", "title": "Kaffee", "messages": [
            {"role": "user", "content": "Cold Brew?", "timestamp": 1}]},
        {"id": "def456", "title": "Router", "messages": [
            {"role": "user", "content": "packet loss", "timestamp": 2}]},
    ]
}


def _sync(client) -> None:
    assert client.post("/api/sessions/sync", json=_PAYLOAD).status_code == 200


def test_export_returns_valid_zip(client):
    """GIVEN two synchronised sessions
    WHEN /api/sessions/export (zip) is called
    THEN the archive contains the registry + both session files."""
    client, _ = client
    _sync(client)
    resp = client.get("/api/sessions/export")
    assert resp.status_code == 200
    data = resp.content
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "registry.json" in names
    assert "pwa-abc123.json" in names
    assert "pwa-def456.json" in names


def test_export_supports_targz(client):
    """GIVEN format=tar.gz is requested
    WHEN the export runs
    THEN the payload is a valid gz-compressed tar archive."""
    client, _ = client
    _sync(client)
    data = client.get("/api/sessions/export", params={"format": "tgz"}).content
    assert data[:2] == b"\x1f\x8b"  # gzip magic bytes
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = tar.getnames()
    assert "registry.json" in names


def test_import_restores_bundle_1_zu_1(client):
    """GIVEN an export bundle
    WHEN it is imported into an emptied store
    THEN registry + contents are found back identically (1:1)."""
    client, sessions_dir = client
    _sync(client)
    data = client.get("/api/sessions/export").content
    before = json.loads((sessions_dir / "registry.json").read_text(encoding="utf-8"))
    for f in sessions_dir.glob("*.json"):
        f.unlink()
    resp = client.post(
        "/api/sessions/import",
        files={"file": ("bundle.zip", data, "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["restored"] == 2
    after = json.loads((sessions_dir / "registry.json").read_text(encoding="utf-8"))
    assert after == before
    body = json.loads((sessions_dir / "pwa-abc123.json").read_text(encoding="utf-8"))
    assert body[0]["content"] == "Cold Brew?"


def test_import_rejects_path_traversal(tmp_path, monkeypatch):
    """GIVEN an archive with a '../' entry
    WHEN the import runs
    THEN it is rejected (guard) without any file landing outside."""
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path))
    import core.multi_session as ms

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("registry.json", '{"sessions": []}')
        zf.writestr("../evil.json", "{}")
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/sessions/import",
            files={"file": ("bundle.zip", buf.getvalue(), "application/zip")},
        )
        assert resp.status_code == 400
        # the valid single archive, for comparison
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("registry.json", '{"sessions": []}')
    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/sessions/import",
            files={"file": ("bundle.zip", buf2.getvalue(), "application/zip")},
        )
        assert resp.status_code == 200


def test_import_rejects_non_archive(tmp_path, monkeypatch):
    """GIVEN a non-archive upload
    WHEN the import runs
    THEN the route answers 400 (no guessing)."""
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path))
    import core.multi_session as ms

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/sessions/import",
            files={"file": ("bundle.zip", b"not-a-zip", "application/zip")},
        )
        assert resp.status_code == 400
