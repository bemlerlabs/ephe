"""An unknown non-API path is the app, not a JSON 404.

The frontend routes with ``HashRouter`` (``app/src/App.tsx:1``), so a refresh, a
bookmark or a pasted link to a client-side route reaches the server as a bare
path with no file behind it — ``/workspaces``, ``/memory``, ``/artifacts``. The
server mounted ``StaticFiles(..., html=True)`` at ``/``, which answers every one
of them with the API's 404 envelope: the app existed only at ``/``.

Four behaviours are pinned together, because the failure mode of this fix is
fixing one by breaking another:

- a non-API path with no file at its end serves the app shell (``index.html``);
- an unknown ``/api/`` path keeps the JSON 404 envelope — an API route that
  answers HTML breaks every client, which is worse than the bug being fixed;
- an unknown ``/v1/`` path keeps its JSON hint;
- a path that names a *file* keeps its 404 — answering a missing
  ``/assets/app.js`` with ``index.html`` hides a broken build and hands a module
  request ``text/html``.

Rules (no mocks for the server behaviour): ``TestClient`` against the real
``create_app()``, the frontend directory isolated through ``EPHE_FRONTEND_DIR``
— the same seam ``tests/test_pwa_serving.py`` uses.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app

SHELL_MARKER = "Ephe — Test Build"
DEEP_LINKS = ["/workspaces", "/memory", "/artifacts", "/workspaces/ws-0001"]


def _make_dist(tmp_path: Path) -> Path:
    """A minimal but real dist tree (index.html + one asset)."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!DOCTYPE html>\n<html lang=\"en\">\n"
        f"<head><title>{SHELL_MARKER}</title></head>\n"
        "<body>Ephe Test PWA</body>\n</html>\n",
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('test-pwa');\n", encoding="utf-8")
    return dist


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPHE_FRONTEND_DIR", str(_make_dist(tmp_path)))
    with TestClient(create_app()) as c:
        yield c


# 1) the deep link answers the app shell

@pytest.mark.parametrize("path", DEEP_LINKS)
def test_given_client_side_route_when_requested_then_serves_the_app_shell(
    client: TestClient, path: str
) -> None:
    """
    GIVEN a phone (or a browser) asks for a route the frontend owns
    WHEN the path carries no file at its end
    THEN the app shell is served, so the installed PWA survives a reload
    """
    res = client.get(path)
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert SHELL_MARKER in res.text


def test_given_unknown_api_route_when_requested_then_stays_a_json_404(client: TestClient) -> None:
    """
    GIVEN a client calls an API route this server does not mount
    WHEN the SPA fallback is in place
    THEN the answer is still the JSON 404 envelope — never the app shell
    """
    res = client.get("/api/not-a-route")
    assert res.status_code == 404
    assert "application/json" in res.headers["content-type"]
    body = json.loads(res.text)
    assert body["error"]["code"] == "not_found"
    assert SHELL_MARKER not in res.text


def test_given_unknown_v1_route_when_requested_then_stays_a_json_404(client: TestClient) -> None:
    """
    GIVEN an OpenAI-compatible client calls /v1/... on the PWA server
    WHEN the SPA fallback is in place
    THEN the honest JSON hint is still the answer
    """
    res = client.get("/v1/models")
    assert res.status_code == 404
    assert "application/json" in res.headers["content-type"]
    assert "not mounted" in res.text
    assert SHELL_MARKER not in res.text


def test_given_missing_asset_when_requested_then_stays_a_404(client: TestClient) -> None:
    """
    GIVEN the build is missing an asset a page asks for
    WHEN the request names a file
    THEN it is a 404 — not the shell wearing a text/html label
    """
    res = client.get("/assets/gone-1234.js")
    assert res.status_code == 404
    assert SHELL_MARKER not in res.text


# 2) the surfaces that already worked keep working

def test_given_root_and_real_asset_when_requested_then_the_build_is_served(client: TestClient) -> None:
    """GIVEN the build exists WHEN / and a real asset are asked for THEN they are served."""
    root = client.get("/")
    assert root.status_code == 200
    assert SHELL_MARKER in root.text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "test-pwa" in asset.text
