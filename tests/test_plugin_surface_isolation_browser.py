"""The surface document's sandbox, measured in real browser engines.

Fix-round-1 ruling: the isolation mechanism behind a plugin surface is the
*opaque origin* a `sandbox` directive without `allow-same-origin` produces —
chosen over a cookie (a credential the Origin/Host guards were never designed to
see) and over a per-plugin custom scheme (Tauri 2 cannot allow-list a custom
scheme per webview today, so that confinement would be an unenforced claim). A
CSP claim nobody observed is the defect class this repo has been fixing all week,
so this file does not assert the header alone. It starts the real server on a
loopback port (the desktop trust path: no token is asked for there, and the sandbox
in this route's header is the confinement a mount's reads get), loads the real mount
URL in a real `<iframe>`, and reads back what the sandboxed document actually did,
through `frame.evaluate` because a sandboxed frame's `console` messages do not reach
the page listener on every engine (measured here: WebKit drops them).

What this suite measures is the *read*: the engine hands a null-origin document no
body, so `settings:BLOCKED`, `plugins:BLOCKED` and `file:BLOCKED` say the mount
cannot spend the user's authority, while the unsandboxed parent reads the same two
endpoints back as bytes.

What the server confines besides that read. A mutation: the Origin guard refuses a
method outside GET/HEAD/OPTIONS under a disallowed origin, and off loopback the
missing LAN token answers 401. A GET that writes state or opens another local
service: the same `untrusted_origin`, including a literal Origin of `null` on
loopback. The surface family: a path without a live nonce is refused on loopback
too. The app's own fetches of other `/api` routes stay token-free on loopback.

What stays unconfined, so an opaque origin is not a claim that the request cannot
reach the API. A null-origin GET of a read-only route still leaves the frame, still
reaches this server, and on loopback the server still answers it. The bytes are
withheld on the way back. A local process that sends no Origin header may still
read. A mutation from that process is refused, and so is a GET that spends
authority. WebKit in the shipped shell stays unmeasured (task #43).

Per engine, three measured questions:

  1. did the engine make the origin opaque (`window.origin === "null"`),
  2. did a same-origin fetch the mount fires (`/api/settings`, `/api/plugins`)
     come back BLOCKED, while the unsandboxed parent reads the same bytes back —
     the endpoints are live and hold the user's own data,
  3. does the document still load its own relative script through the nonce
     segment (the directory-shaped mount handing its path prefix to `app.js`).

An engine that cannot boot is skipped with its name in the skip reason; a shipped
claim about it would otherwise be a lie the report has to say out loud.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MARKER = "SURFACE-AUTHORITY-MARKER-6541"
PLUGIN_ID = "acme-isolation"

#: The document the sandbox is judged on: two scripts, the probe and the asset the
#: probe's own `<script src="app.js">` reference resolves to through the nonce.
SURFACE_ENTRY = """<!doctype html><title>Isolation Surface</title>
<script src="probe.js"></script>
<script src="app.js"></script>
"""

#: The probe writes its results into `window.__RESULTS__` — read back through
#: `frame.evaluate`, the one channel that works across every sandboxed engine.
PROBE_SCRIPT = """
window.__RESULTS__ = [];
window.__RESULTS__.push("origin:" + String(window.origin));
function probe(name, url) {
  fetch(url, {cache: "no-store"})
    .then(function (r) { return r.text().then(function (t) { window.__RESULTS__.push(name + ":LEAK " + t.length); }); })
    .catch(function (e) { window.__RESULTS__.push(name + ":BLOCKED"); });
}
probe("settings", "/api/settings");
probe("plugins", "/api/plugins");
probe("file", "/api/file?path=" + encodeURIComponent("__MARK__"));
setTimeout(function () { window.__RESULTS__.push("watchdog"); }, 6000);
"""

#: `app.js` is a relative reference from the document URL — its arrival proves the
#: browser inherited the nonce path segment onto a sub-resource the page derived.
SURFACE_ASSET = 'window.__RESULTS__ = window.__RESULTS__ || []; window.__RESULTS__.push("asset:loaded");'

PARENT_PAGE = """<!doctype html><title>Parent</title>
<iframe id="f" src="__SURFACE_URL__"></iframe>
<script>
window.__PARENT__ = [];
function readBack(name, url) {
  fetch(url, {cache: "no-store"})
    .then(function (r) { return r.text().then(function (t) { window.__PARENT__.push(name + ":READ " + t.length); }); })
    .catch(function (e) { window.__PARENT__.push(name + ":FAIL"); });
}
readBack("settings", "/api/settings");
readBack("plugins", "/api/plugins");
</script>
"""


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """The real app on a real loopback port, LAN auth off: the desktop trust path."""
    from core import plugin_runtime
    from core.engine_config import artifact_output_dir
    from server import plugin_surface_nonce
    from server.main import create_app
    from server.middleware import init_auth
    import uvicorn

    config = tmp_path_factory.mktemp("isolation-home")
    previous = os.environ.get("EPHE_CONFIG_DIR")
    os.environ["EPHE_CONFIG_DIR"] = str(config)
    os.environ["EPHE_OFFLINE"] = "1"
    plugin = config / "plugins" / PLUGIN_ID
    (plugin / "ui").mkdir(parents=True)
    secret = artifact_output_dir() / "surface-secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text(MARKER, encoding="utf-8")
    (plugin / "ui" / "index.html").write_text(SURFACE_ENTRY, encoding="utf-8")
    (plugin / "ui" / "probe.js").write_text(
        PROBE_SCRIPT.replace("__MARK__", str(secret)), encoding="utf-8"
    )
    (plugin / "ui" / "app.js").write_text(SURFACE_ASSET, encoding="utf-8")
    manifest = {
        "manifest_version": 1, "name": PLUGIN_ID, "version": "1.0.0",
        "description": "Measures what the sandbox actually takes away",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": [], "ui": {
            "type": "floating-window", "entry": "ui/index.html", "title": "Isolation",
            "capabilities": ["notifications", "dock-badge"],
        }},
    }
    (plugin / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (config / "plugin-state.json").write_text(
        json.dumps({"schema": 1, "pause_all": False, "plugins": {}}), encoding="utf-8"
    )
    plugin_runtime.invalidate_ownership_cache()
    init_auth(lan_mode=False)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20.0
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the isolation server never started"
    nonce = plugin_surface_nonce.mint_surface_nonce(PLUGIN_ID).nonce
    parent = PARENT_PAGE.replace("__SURFACE_URL__", f"/api/plugins/ui/{PLUGIN_ID}/{nonce}/")
    (secret.parent / "surface-parent.html").write_text(parent, encoding="utf-8")
    yield {
        "base": f"http://127.0.0.1:{port}",
        "surface": f"/api/plugins/ui/{PLUGIN_ID}/{nonce}/",
        "parent": f"/charts/{(secret.parent / 'surface-parent.html').name}",
        "secret": str(secret),
        "home": str(config),
    }
    server.should_exit = True
    thread.join(timeout=15.0)
    assert not thread.is_alive(), "the isolation server thread outlived the test"
    gone = False
    for _ in range(20):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        except (ConnectionRefusedError, OSError):
            gone = True
            break
        time.sleep(0.1)
    assert gone, "the isolation server still answers on its port after teardown"
    if previous is None:
        os.environ.pop("EPHE_CONFIG_DIR", None)
    else:
        os.environ["EPHE_CONFIG_DIR"] = previous


@pytest.fixture(autouse=True)
def _keep_the_isolation_home(live, monkeypatch):
    """The session's autouse home-isolation fixture redirects `EPHE_CONFIG_DIR` per
    test after this module's fixture set it; every test re-points the live server's
    process at the isolation home again — the last `setenv` before the request wins."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", live["home"])
    monkeypatch.setenv("EPHE_OFFLINE", "1")


def _launch(engine_name: str, playwright):
    factory = getattr(playwright, engine_name)
    try:
        return factory.launch()
    except Exception as refused:  # an engine that cannot boot is named, per the brief
        pytest.skip(f"{engine_name} is not drivable in this lane: {refused}")


def _collect_frame(frame, wanted: int, timeout: float = 15.0) -> list[str]:
    deadline = time.monotonic() + timeout
    results: list[str] = []
    while time.monotonic() < deadline:
        try:
            results = frame.evaluate("window.__RESULTS__ || []")
        except Exception:
            results = []
        if len(results) >= wanted:
            break
        time.sleep(0.1)
    return results


@pytest.mark.parametrize("engine_name", ["chromium", "webkit"])
def test_the_sandboxed_surface_holds_no_user_authority(live, engine_name):
    """The Critical's measurement, per real engine: the document runs and loads its
    own relative asset through the nonce segment, but every read of the user's
    authority comes back BLOCKED — while the unsandboxed parent reads the same two
    endpoints back as bytes. Boot or skip by name."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _launch(engine_name, playwright)
        try:
            page = browser.new_page()
            page.goto(live["base"] + live["parent"], wait_until="load")
            frame = next((f for f in page.frames if "/api/plugins/ui/" in f.url), None)
            assert frame is not None, "the mount never framed"
            # origin + settings + plugins + asset + watchdog = the full picture.
            results = _collect_frame(frame, wanted=6)
            joined = " | ".join(results)
            # 1. the engine really made the origin opaque — the whole claim rests here.
            assert "origin:null" in joined, joined
            # 2. and cannot spend the user's authority from inside the mount.
            assert "settings:BLOCKED" in joined, joined
            assert "plugins:BLOCKED" in joined, joined
            assert "file:BLOCKED" in joined, joined
            assert "settings:LEAK" not in joined, joined
            assert "plugins:LEAK" not in joined, joined
            # 3. the document still loads its own relative asset through the segment.
            assert "asset:loaded" in joined, joined
            # the watchdog entry proves the probe ran to completion and did not hang.
            assert "watchdog" in joined, joined
            # the controls: the unsandboxed parent reads the same bytes back.
            parent_results: list[str] = []
            parent_deadline = time.monotonic() + 8.0
            while time.monotonic() < parent_deadline and len(parent_results) < 2:
                parent_results = page.evaluate("window.__PARENT__ || []")
                time.sleep(0.1)
            assert any("settings:READ" in r for r in parent_results), parent_results
            assert any("plugins:READ" in r for r in parent_results), parent_results
        finally:
            browser.close()


def test_the_mount_response_header_carries_the_isolation_itself(live):
    """The floor under the browser claims, before any engine is asked: the document
    response says `sandbox allow-scripts allow-popups` and never `allow-same-origin`;
    the script the mount derives stays un-sandboxed so it can load."""
    import httpx

    with httpx.Client(base_url=live["base"], timeout=10.0) as client:
        document = client.get(live["surface"])
        assert document.status_code == 200, document.text
        csp = document.headers["content-security-policy"]
        assert "sandbox allow-scripts allow-popups" in csp, csp
        assert "allow-same-origin" not in csp, csp
        asset = client.get(live["surface"] + "app.js")
        assert asset.status_code == 200, asset.text
        assert "sandbox" not in asset.headers["content-security-policy"]
