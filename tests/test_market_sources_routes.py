"""S2 — the breadth door: user-provisioned marketplace sources.

The shelf reads the bundled index only until the user adds a source; these
routes are the add/remove pair behind the sources row. A source lives in
~/.ephe/marketplaces.json, is validated before it is stored (https-only,
no credentials, no fragment; local sources need an absolute path), and
every refusal carries a stable code with the fixed refusal sentence.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    from server.main import create_app

    return TestClient(create_app())


def test_sources_route_lists_bundled_and_user_sources(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    listed = client.get("/api/market/sources").json()["sources"]
    ids = [s["id"] for s in listed]
    assert "bundled" in ids
    added = client.post(
        "/api/market/sources",
        json={"kind": "https", "title": "My mirror", "url": "https://mirror.example/index.json"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert added.status_code == 200, added.text
    assert added.json()["id"].startswith("src-")
    listed = client.get("/api/market/sources").json()["sources"]
    assert any(s["id"] == added.json()["id"] and s["trust"] == "community" for s in listed)


def test_source_add_is_idempotent_and_refuses_bad_urls(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    body = {"kind": "https", "title": "A", "url": "https://a.example/index.json"}
    xhr = {"X-Requested-With": "XMLHttpRequest"}
    first = client.post("/api/market/sources", json=body, headers=xhr).json()
    second = client.post("/api/market/sources", json=body, headers=xhr).json()
    assert first["id"] == second["id"]
    bad = client.post(
        "/api/market/sources",
        json={"kind": "https", "title": "A", "url": "http://a.example/index.json"},
        headers=xhr,
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["detail"]["code"] == "invalid_url"
    credentialed = client.post(
        "/api/market/sources",
        json={"kind": "https", "title": "A", "url": "https://user:pass@a.example/index.json"},
        headers=xhr,
    )
    assert credentialed.status_code == 400
    assert credentialed.json()["error"]["detail"]["code"] == "invalid_url"


def test_source_remove_and_bundled_guard(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    added = client.post(
        "/api/market/sources",
        json={"kind": "https", "title": "B", "url": "https://b.example/index.json"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ).json()
    removed = client.post("/api/market/sources/remove", json={"id": added["id"]},
                           headers={"X-Requested-With": "XMLHttpRequest"})
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    again = client.post("/api/market/sources/remove", json={"id": added["id"]},
                        headers={"X-Requested-With": "XMLHttpRequest"})
    assert again.status_code == 400
    bundled = client.post("/api/market/sources/remove", json={"id": "bundled"},
                           headers={"X-Requested-With": "XMLHttpRequest"})
    assert bundled.status_code == 400
