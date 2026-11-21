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

    Every route in the authority list answers 403, and the pairing flag, the
    update cache, the tour file and the artifact tree stay put.
    """
    from server.middleware import AUTHORITY_GET_PREFIXES

    stamp = _stamp()
    targets = (
        "/api/artifacts/proxy?url=https://example.test/a.png",
        "/api/mobile/qr",
        "/api/update/check",
        "/api/proxy/5173",
        "/api/browser/watch/aaaaaaaa11111111",
        "/api/setup/detect",
        "/api/reader?url=https://example.test/page",
        "/api/git/info",
        "/api/model/providers",
        "/api/context/budget",
        "/api/market/index",
        "/api/market/updates",
        "/api/discover/bootstrap",
        "/api/setup/status",
    )
    assert len(targets) == len(AUTHORITY_GET_PREFIXES)
    for path in targets:
        refused = desktop.get(path, headers={"Origin": "null"})
        assert refused.status_code == 403, (path, refused.text)
        assert refused.json()["error"]["detail"]["code"] == "untrusted_origin"
        _unchanged(stamp)


def test_the_apps_own_fetch_still_runs_the_two_dials(desktop, monkeypatch):
    """The caller the app really is still gets through the widened list.

    The settings page's scan button and the reader panel are the only callers of
    the two routes that joined the authority list. A guard that locked them out
    would leave a green build and two dead buttons, so the case asks as the
    webview asks: this server's own host, `Sec-Fetch-Site: same-origin`, and no
    `PYTEST_CURRENT_TEST` — the synthetic host is a seam, not an allowance.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    headers = {"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"}

    scan = desktop.get("/api/setup/detect", headers=headers)
    assert scan.status_code == 200, scan.text
    assert "candidates" in scan.json(), scan.text

    read = desktop.get("/api/reader", params={"url": "https://example.test/page"}, headers=headers)
    assert read.status_code == 200, read.text
    assert "reason_code" in read.json(), read.text


def test_the_apps_own_fetch_reaches_every_route_that_joined_later(desktop, monkeypatch):
    """Each of the seven routes is called by the PWA and by nothing else on this machine.

    A guard that locked them out would leave a green suite — the synthetic host is a seam,
    not an allowance — and dead pages: the source-control panel, the context meter, the model
    setup, the market tab. So each is asked the way the webview asks, and none may answer
    with the authority refusal.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    headers = {"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"}
    for path in (
        "/api/git/status",
        "/api/model/providers",
        "/api/context/budget",
        "/api/market/index",
        "/api/market/updates",
        "/api/discover/bootstrap",
        "/api/setup/status",
    ):
        answer = desktop.get(path, headers=headers)
        detail = {}
        if (answer.headers.get("content-type") or "").startswith("application/json"):
            detail = ((answer.json() or {}).get("error") or {}).get("detail") or {}
        assert detail.get("code") != "untrusted_origin", (path, answer.status_code, answer.text)
def test_a_get_under_a_root_path_still_spends_local_authority(desktop):
    """A mount at a subpath used to switch the whole list off, quietly.

    `uvicorn --root-path /console` is how this dashboard gets served behind a proxy at a
    subpath. Starlette gives the router the path without that prefix and leaves the prefix in
    `request.url.path`, so `get_spends_local_authority` saw `/console/api/reader`, matched no
    entry, and the GET answered — with a list on screen that still read exactly as before. The
    guard is asked directly here, with the scope a mount produces, because the synthetic
    TestClient host is a seam and cannot carry a `root_path`.
    """
    import asyncio

    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from server.middleware import LocalRequestGuardMiddleware

    async def _noop_asgi(scope, receive, send):   # the app behind the guard
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def _ask(path: str, root_path: str):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": root_path,
            "query_string": b"",
            "headers": [(b"host", b"127.0.0.1:8765"), (b"origin", b"null")],
            "client": ("127.0.0.1", 55555),
            "server": ("127.0.0.1", 8765),
        }
        guard = LocalRequestGuardMiddleware(app=_noop_asgi)

        async def call_next(_request):
            return JSONResponse({"answered": True})

        return await guard.dispatch(Request(scope), call_next)

    for path, root in (("/api/reader", ""), ("/console/api/reader", "/console")):
        refused = asyncio.run(_ask(path, root))
        assert refused.status_code == 403, (path, root, refused.body)
        assert json.loads(refused.body)["error"]["detail"]["code"] == "untrusted_origin", (path, root)

    read_only = asyncio.run(_ask("/console/api/settings", "/console"))
    assert read_only.status_code == 200, read_only.body


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


WATCH_SESSION = "aaaaaaaa11111111"
WATCH_PATH = f"/api/browser/watch/{WATCH_SESSION}"


class _CastingManager:
    """The manager surface the watch route touches, with the cast ask recorded.

    `start_watch` is the mutation: it tells a live browser to begin screencasting. Both cases feed
    back the engine's refusal, because a stream that did open would never finish under
    `TestClient`, and a red suite has to be red rather than stuck.
    """

    def __init__(self, refusal: str = "cast refused: no engine") -> None:
        self.refusal = refusal
        self.started: list[str] = []

    def has_session(self, session: str) -> bool:
        return True

    async def start_watch(self, session: str) -> str:
        self.started.append(session)
        return self.refusal

    async def stop_watch(self, session: str) -> None:
        return None


def _watch_headers(**extra: str) -> dict[str, str]:
    """The pane's own request: an event-stream fetch, plus whatever proof the case names."""
    return {"Accept": "text/event-stream", **extra}


def test_the_watch_channel_needs_an_origin_this_server_serves(desktop, monkeypatch):
    """A watch is not a read: it turns casting on in the browser the agent is driving.

    Frames are that browser's screen, so an attacker's page that names a live session both starts
    the cast and receives it. The guard runs before the handler, which is why a refused call
    leaves the manager untouched.
    """
    manager = _CastingManager()
    monkeypatch.setattr("core.browser.browser_manager", manager)
    refused = desktop.get(WATCH_PATH, headers=_watch_headers(Origin="null"))
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["detail"]["code"] == "untrusted_origin"
    assert manager.started == []


def test_the_watch_still_opens_for_the_page_this_server_serves(desktop, monkeypatch):
    """The pane fetches its own stream, so the same-origin proof has to reach the handler.

    The engine answers this cast with a refusal; what matters is whose answer came back.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    manager = _CastingManager()
    monkeypatch.setattr("core.browser.browser_manager", manager)
    opened = desktop.get(
        WATCH_PATH,
        headers=_watch_headers(Host="127.0.0.1:8765", **{"Sec-Fetch-Site": "same-origin"}),
    )
    assert opened.status_code != 403, opened.text
    assert opened.json()["error"]["reason_code"] == "browser_watch_unavailable", opened.text
    assert manager.started == [WATCH_SESSION]
