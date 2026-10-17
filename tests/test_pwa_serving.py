"""
◑ Ephe – PWA static serving (root-cause regression, 2026-08-21)
tests/test_pwa_serving.py

Root cause (5 whys):
  Symptom:  ephe start opens http://127.0.0.1:8765 → "Not Found" (404)
  Why-1:    server/main.py was configured with a static mount on "/"
  Why-2:    the mount directory points at app/src (the Vite SOURCE) — since the
            React-Vite migration no index.html exists there anymore
  Why-3:    the built frontend lives in app/dist (git-ignored)
  Why-4:    the one-command installer (install.sh/install.ps1) and the Dockerfile
            never build the frontend → fresh clone = no PWA
  Fix:      the server mounts app/dist; if the build is missing the root serves a
            repair-hint page (instead of a silent 404); the installer and
            doctor --fix build the frontend.

Rules (100% real, no mocks for the server behaviour):
  - TestClient against the real create_app()
  - the frontend directory is isolated via the EPHE_FRONTEND_DIR env
    (product code may honour that env → testability WITHOUT a mock)
  - the repo's own dist smoke test against the real build (skip if missing)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app

ROOT = Path(__file__).resolve().parents[1]
REAL_DIST = ROOT / "app" / "dist"


def _make_dist(tmp_path: Path, with_assets: bool = True) -> Path:
    """A minimal but real dist tree (index.html + asset)."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!DOCTYPE html>\n<html lang=\"de\">\n"
        "<head><title>Ephe — Test Build</title>"
        '<link href="/assets/app.js" rel="module"></head>\n'
        "<body>Ephe Test PWA</body>\n</html>\n",
        encoding="utf-8",
    )
    if with_assets:
        (dist / "assets" / "app.js").write_text(
            "console.log('test-pwa');\n", encoding="utf-8"
        )
    return dist


# 1) dist present → the PWA is served under /

def test_given_dist_build_present_when_root_requested_then_serves_index_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    GIVEN the PWA build (app/dist) exists
    WHEN the new user loads http://127.0.0.1:8765/
    THEN the server serves the PWA (HTTP 200 + index.html + assets)
    """
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("EPHE_FRONTEND_DIR", str(dist))
    with TestClient(create_app()) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "Ephe — Test Build" in root.text

        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "test-pwa" in asset.text


# 2) dist missing → a repair-hint page instead of a silent 404

def test_given_dist_missing_when_root_requested_then_serves_repair_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    GIVEN the PWA build is missing (fresh git clone, dist is git-ignored)
    WHEN the new user loads http://127.0.0.1:8765/
    THEN they get no dead 404 but a hint page that says exactly how to build
       the PWA
    """
    empty = tmp_path / "kein-build"
    empty.mkdir()
    monkeypatch.setenv("EPHE_FRONTEND_DIR", str(empty))
    with TestClient(create_app()) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "Ephe" in root.text
        assert "npm run build" in root.text
        assert "npm install" in root.text


# 3) without a frontend the API stays fully functional

def test_given_dist_missing_when_api_called_then_api_unaffected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    GIVEN the PWA build is missing
    WHEN the API endpoints are requested
    THEN the API keeps working (a frontend fault does not block the backend)
    """
    empty = tmp_path / "kein-build"
    empty.mkdir()
    monkeypatch.setenv("EPHE_FRONTEND_DIR", str(empty))
    with TestClient(create_app()) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = json.loads(health.text)
        assert "status" in body or "ok" in body


# 4) smoke test against the repo's own dist (new-user regression)

@pytest.mark.skipif(
    not (REAL_DIST / "index.html").is_file(),
    reason="app/dist fehlt (lokal bauen: cd app && npm install && npm run build)",
)
def test_given_repo_dist_present_when_root_requested_then_serves_real_pwa():
    """
    GIVEN the repo's own app/dist build exists (no env override)
    WHEN the root is loaded
    THEN the real PWA build is served (not the Vite source)
    """
    with TestClient(create_app()) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "Ephe" in root.text
        # Vite build artefact, not the app/src source
        assert "/assets/" in root.text
