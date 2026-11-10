"""Null-origin GETs on the desktop trust path.

A sandboxed document sends Origin: null. Loopback used to answer every GET.
A GET that writes state or opens another service is refused. A GET that only
reads stays available, and calling it leaves stored state where it was.
The app's own fetch sends no Origin and stays token-free.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    """LAN auth off, config under the test tmp dir, the desktop trust path."""
    from core import update_check
    from server.main import create_app
    from server.middleware import init_auth
    from server.routes import mobile

    config = tmp_path / "ephe-home"
    config.mkdir(exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    saved_cache = dict(update_check._cache)
    saved_flag = mobile._device_connected
    init_auth(lan_mode=False)
    app = create_app(lan_mode=False)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        update_check._cache.clear()
        update_check._cache.update(saved_cache)
        mobile._device_connected = saved_flag
        init_auth(lan_mode=False)


def _stamp() -> dict:
    """Pairing flag, update cache, tour file, and the artifact tree, as they stand."""
    from core import path_guard, update_check
    from server.routes import mobile

    mobile._device_connected = True
    update_check._cache["at"] = 10.0
    update_check._cache["value"] = {"enabled": True, "available": False, "marker": "stay"}
    tour = Path(os.environ["EPHE_CONFIG_DIR"]) / "tour.json"
    tour.write_text(
        json.dumps({"version": 1, "step": 1, "walked": False, "skipped": False, "answers": {}}),
        encoding="utf-8",
    )
    root = path_guard.artifact_root()
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) if root.exists() else []
    return {"tour": tour.read_bytes(), "tour_path": tour, "files": files, "root": root}


def _unchanged(stamp: dict) -> None:
    from core import update_check
    from server.routes import mobile

    assert mobile._device_connected is True
    assert update_check._cache["value"]["marker"] == "stay"
    assert stamp["tour_path"].read_bytes() == stamp["tour"]
    root = stamp["root"]
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) if root.exists() else []
    assert files == stamp["files"]


def test_a_null_origin_get_of_a_state_changing_route_is_refused(desktop):
    """Origin null on loopback cannot run a GET that writes or opens a service.

    The four routes in the authority list each answer 403, and the pairing
    flag, the update cache, the tour file and the artifact tree stay put.
    """
    from server.middleware import AUTHORITY_GET_PREFIXES

    stamp = _stamp()
    targets = (
        "/api/artifacts/proxy?url=https://example.test/a.png",
        "/api/mobile/qr",
        "/api/update/check",
        "/api/proxy/5173",
    )
    assert len(targets) == len(AUTHORITY_GET_PREFIXES)
    for path in targets:
        refused = desktop.get(path, headers={"Origin": "null"})
        assert refused.status_code == 403, (path, refused.text)
        assert refused.json()["error"]["detail"]["code"] == "untrusted_origin"
        _unchanged(stamp)


def test_a_read_only_get_cannot_flip_stored_state(desktop):
    """A GET that only reads still answers, and the stored bytes stay where they were.

    `/api/settings` with no Origin header is the desktop app's own fetch: loopback,
    token-free. A mutation from Origin null stays on the method guard.
    """
    stamp = _stamp()
    for path in ("/api/tour", "/api/settings", "/api/plugins", "/api/mobile/status"):
        read = desktop.get(path, headers={"Origin": "null"})
        assert read.status_code == 200, (path, read.text)
        _unchanged(stamp)
    own = desktop.get("/api/settings")
    assert own.status_code == 200, own.text
    _unchanged(stamp)
    mutation = desktop.post(
        "/api/settings",
        json={"language": "en"},
        headers={"Origin": "null"},
    )
    assert mutation.status_code == 403, mutation.text
    assert mutation.json()["error"]["detail"]["code"] == "untrusted_origin"
    _unchanged(stamp)


def test_the_apps_own_same_origin_fetch_reaches_an_authority_get(desktop, monkeypatch):
    """A page this server serves fetches its own update check without an Origin header.

    The browser omits `Origin` on a same-origin GET, so the origin rule answered 403 and the
    Settings' update check never ran in the PWA or in the desktop webview. In the suite the
    synthetic host stood in for the app, which is why this only ever failed against a real
    browser. `Sec-Fetch-Site: same-origin` is set by the browser and cannot be forged by another
    site, so it names the same caller the Origin header names.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    same = desktop.get(
        "/api/update/check",
        headers={"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"},
    )
    assert same.status_code == 200, same.text


def test_a_cross_site_fetch_stays_refused_even_without_an_origin(desktop, monkeypatch):
    """A page from another site reaches an authority GET with `Sec-Fetch-Site: cross-site`."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    cross = desktop.get(
        "/api/update/check",
        headers={"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "cross-site"},
    )
    assert cross.status_code == 403, cross.text
    assert cross.json()["error"]["detail"]["code"] == "untrusted_origin"


def test_a_referer_from_a_served_origin_also_names_the_app(desktop, monkeypatch):
    """Older and non-browser callers send `Referer` rather than the fetch metadata."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    ok = desktop.get(
        "/api/update/check",
        headers={"Host": "127.0.0.1:8765", "Referer": "http://127.0.0.1:8765/settings"},
    )
    assert ok.status_code == 200, ok.text
    foreign = desktop.get(
        "/api/update/check",
        headers={"Host": "127.0.0.1:8765", "Referer": "https://evil.example/settings"},
    )
    assert foreign.status_code == 403, foreign.text
