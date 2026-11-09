"""Page storage inside a real sandboxed mount: a write that a read survives.

The mount document carries `sandbox allow-scripts allow-popups`, so its origin is
opaque (`tests/test_plugin_surface_storage_refusal.py` pins the engine's refusal).
The product answer is not `allow-same-origin` — that would hand the bundle the
app's origin and its tokens — but the storage shim: synchronous reads from a
snapshot embedded in the document, writes over the `ephe.sdk` bridge to the
bundle's own state root.

The whole loop runs in a real engine here: the document's origin stays
still `null`; `localStorage.setItem` followed at once by `getItem` returns the
written value; the write reached the server's store for *this* plugin; the parent
origin's own storage did not receive it; and a reload of the same mount reads the
value back out of the snapshot. The parent stands in for the shell's overlay and
answers the bridge with the product's own storage route, so the write travels the
same path `attachPluginClient` uses.

An engine that cannot boot is skipped by name, so a green row is never a row
nobody watched.
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

PLUGIN_ID = "acme-page-shim"

SURFACE_ENTRY = """<!doctype html><title>Page Storage Shim</title>
<h1>Shim probe</h1>
<script src="probe.js"></script>
"""

#: A bundle written against the Storage API, which is what the three paid-run
#: bundles were. `before` is read first, so a second load proves the value came
#: back from the store rather than from this run's own write.
PROBE_SCRIPT = """
window.__STORAGE__ = [];
function note(name, value) {
  window.__STORAGE__.push(name + ":" + String(value));
}
try {
  note("origin", window.origin);
} catch (error) {
  note("origin", "error");
}
note("shim", typeof window.EpheStorageShim === "object" ? "loaded" : "missing");
var before = null;
try {
  before = window.localStorage.getItem("theme");
  note("seeded", window.localStorage.getItem("seeded"));
} catch (error) {
  note("read", String(error && error.name) + " " + String(error && error.code));
}
note("before", before === null ? "none" : before);
if (before === null) {
  try {
    window.localStorage.setItem("theme", "dark");
    note("write", "OK");
  } catch (error) {
    note("write", String(error && error.name) + " " + String(error && error.code));
  }
  note("read", window.localStorage.getItem("theme"));
}
try {
  note("length", window.localStorage.length);
  note("key0", window.localStorage.key(0));
} catch (error) {
  note("length", String(error && error.name));
}
try {
  window.sessionStorage.setItem("wizard", "step-2");
  note("session", window.sessionStorage.getItem("wizard"));
} catch (error) {
  note("session", String(error && error.name));
}
"""

#: The host side, cut to the one method this probe writes with. It answers on the
#: product's own storage route, so a green run is the route's answer and not a
#: mock's. The reply goes back to `event.source`, the frame that asked.
PARENT_PAGE = """<!doctype html><title>Parent</title>
<script>
window.__HOST__ = [];
window.addEventListener("message", function (event) {
  var data = event.data;
  if (!data || data.channel !== "ephe.sdk" || !data.id || data.method !== "storage.set") return;
  fetch("/api/plugins/__PLUGIN__/client/storage", {
    method: "PUT",
    headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    body: JSON.stringify({key: data.key, value: data.value})
  }).then(function (response) {
    return response.json().then(function (body) { return {status: response.status, body: body}; });
  }).then(function (answer) {
    window.__HOST__.push(data.key + ":" + answer.status);
    event.source.postMessage({
      channel: "ephe.sdk", id: data.id, ok: answer.status === 200,
      result: answer.body, message: "refused"
    }, "*");
  }).catch(function (error) {
    window.__HOST__.push(data.key + ":FAIL");
    event.source.postMessage({
      channel: "ephe.sdk", id: data.id, ok: false,
      code: "sdk_refused", message: String(error)
    }, "*");
  });
});
</script>
<iframe id="f" src="__SURFACE_URL__" sandbox="allow-scripts allow-popups"></iframe>
"""


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """The real app on a loopback port, with one bundle that writes localStorage."""
    import uvicorn

    from core import plugin_runtime
    from core.engine_config import artifact_output_dir
    from server import plugin_surface_nonce
    from server.main import create_app
    from server.middleware import init_auth

    config = tmp_path_factory.mktemp("shim-home")
    previous = os.environ.get("EPHE_CONFIG_DIR")
    os.environ["EPHE_CONFIG_DIR"] = str(config)
    os.environ["EPHE_OFFLINE"] = "1"
    plugin = config / "plugins" / PLUGIN_ID
    (plugin / "ui").mkdir(parents=True)
    (plugin / "ui" / "index.html").write_text(SURFACE_ENTRY, encoding="utf-8")
    (plugin / "ui" / "probe.js").write_text(PROBE_SCRIPT, encoding="utf-8")
    manifest = {
        "manifest_version": 1, "name": PLUGIN_ID, "version": "1.0.0",
        "description": "A bundle whose only client state is page storage",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": [], "ui": {
            "type": "floating-window", "entry": "ui/index.html", "title": "Storage",
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
    assert server.started, "the shim server never started"
    base = f"http://127.0.0.1:{port}"
    nonce = plugin_surface_nonce.mint_surface_nonce(PLUGIN_ID).nonce
    surface = f"/api/plugins/ui/{PLUGIN_ID}/{nonce}/"
    charts = artifact_output_dir()
    parent_name = "shim-parent.html"
    (charts / parent_name).write_text(
        PARENT_PAGE.replace("__SURFACE_URL__", surface).replace("__PLUGIN__", PLUGIN_ID),
        encoding="utf-8",
    )
    yield {
        "base": base,
        "surface": surface,
        "parent": f"/charts/{parent_name}",
        "home": str(config),
    }
    server.should_exit = True
    thread.join(timeout=15.0)
    assert not thread.is_alive(), "the shim server thread outlived the test"
    if previous is None:
        os.environ.pop("EPHE_CONFIG_DIR", None)
    else:
        os.environ["EPHE_CONFIG_DIR"] = previous


@pytest.fixture(autouse=True)
def _keep_the_shim_home(live, monkeypatch):
    """The shim server's own environment for the length of a test.

    The suite's autouse env fixture drops `EPHE_PORT`, so the free port this server bound is
    named as a dev origin instead: the parent page is a legitimate same-origin caller and the
    origin allow-set has to say so.
    """
    for name, value in (
        ("EPHE_CONFIG_DIR", live["home"]),
        ("EPHE_OFFLINE", "1"),
        ("EPHE_DEV_ORIGINS", live["base"]),
    ):
        monkeypatch.setenv(name, value)


def _seed(live, key: str, value: object) -> None:
    """One value in this bundle's own store, before the document is ever mounted."""
    import httpx

    with httpx.Client(base_url=live["base"], timeout=10.0) as client:
        saved = client.put(
            f"/api/plugins/{PLUGIN_ID}/client/storage",
            json={"key": key, "value": value},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Origin": live["base"],
            },
        )
    assert saved.status_code == 200, saved.text


def _stored(live, key: str) -> object:
    import httpx

    with httpx.Client(base_url=live["base"], timeout=10.0) as client:
        read = client.get(f"/api/plugins/{PLUGIN_ID}/client/storage", params={"key": key})
    assert read.status_code == 200, read.text
    return read.json()["value"] if read.json()["present"] else None


def _frame(page):
    return next((f for f in page.frames if "/api/plugins/ui/" in f.url), None)


def _collect(frame, wanted: int, timeout: float = 15.0) -> list[str]:
    deadline = time.monotonic() + timeout
    results: list[str] = []
    while time.monotonic() < deadline:
        try:
            results = frame.evaluate("window.__STORAGE__ || []")
        except Exception:
            results = []
        if len(results) >= wanted:
            break
        time.sleep(0.1)
    return results


@pytest.mark.parametrize("engine_name", ["chromium", "webkit"])
def test_a_local_storage_write_survives_a_read_and_a_reload_without_the_origin(live, engine_name):
    # The module-scoped store outlives one engine's run; each engine starts from
    # the same empty page store, with only the seeded value in it.
    _seed(live, "theme", None)
    _seed(live, "seeded", "from-store")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = getattr(playwright, engine_name).launch()
        except Exception as refused:
            pytest.skip(f"{engine_name} is not drivable in this lane: {refused}")
        try:
            page = browser.new_page()
            page.goto(live["base"] + live["parent"], wait_until="load")
            frame = _frame(page)
            assert frame is not None, "the mount never framed"
            assert page.locator("#f").get_attribute("sandbox") == "allow-scripts allow-popups"

            results = _collect(frame, wanted=9)
            joined = " | ".join(results)
            assert "origin:null" in joined, joined
            assert "shim:loaded" in joined, joined
            # the snapshot is this bundle's own store, delivered before its script
            assert "seeded:from-store" in joined, joined
            assert "before:none" in joined, joined
            # the write-through read: setItem then getItem in the same turn
            assert "write:OK" in joined, joined
            assert "read:dark" in joined, joined
            assert "length:2" in joined, joined
            assert "key0:seeded" in joined, joined
            # sessionStorage is the document's own memory area
            assert "session:step-2" in joined, joined

            # the write crossed the bridge into this plugin's state root
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and _stored(live, "theme") != "dark":
                time.sleep(0.1)
            assert _stored(live, "theme") == "dark"

            # ... and never reached the embedding page's own storage
            assert page.evaluate("window.localStorage.getItem('theme')") is None

            # a reload re-reads the value out of the snapshot, not out of this run
            page.reload(wait_until="load")
            frame = _frame(page)
            assert frame is not None, "the mount never framed after the reload"
            reloaded = _collect(frame, wanted=7)
            joined_again = " | ".join(reloaded)
            assert "before:dark" in joined_again, joined_again
            assert "seeded:from-store" in joined_again, joined_again
            assert "origin:null" in joined_again, joined_again

            # the mechanism: the header still withholds the origin
            import httpx

            with httpx.Client(base_url=live["base"], timeout=10.0) as client:
                document = client.get(live["surface"])
            assert document.status_code == 200, document.text
            csp = document.headers["content-security-policy"]
            assert "sandbox allow-scripts allow-popups" in csp
            assert "allow-same-origin" not in csp
        finally:
            browser.close()
