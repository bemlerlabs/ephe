"""The mount's sandbox and the page storage a bundle asks for.

Three bundles of the paid creation run wrote `localStorage` from inside the mount.
The mount document carries `sandbox allow-scripts allow-popups` from
`server/plugin_surface_policy.py`, so its origin is opaque and the engine refuses
the storage API with a `SecurityError` that names the missing flag. This file pins
that measured refusal: the write raises, the value never reaches the app origin's
storage, and the same call from an unsandboxed document on that origin succeeds.

The engine is skipped by name when it cannot boot, so a green row is never a row
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

PLUGIN_ID = "acme-page-storage"

#: The key the mount's document tries to write, and the one the parent writes as a
#: control. Separate keys so the frame's attempt cannot be confused with the parent's.
FRAME_KEY = "ephe-frame-storage-probe"
PARENT_KEY = "ephe-parent-storage-probe"

SURFACE_ENTRY = """<!doctype html><title>Page Storage Surface</title>
<h1>Storage probe</h1>
<script src="probe.js"></script>
"""

#: The probe mirrors a generated bundle: one uncaught write at the end is what a
#: bundle without a `try` produces, and the listener above it records the message
#: the eval's own error hook would collect.
PROBE_SCRIPT = """
window.__STORAGE__ = [];
window.addEventListener("error", function (event) {
  window.__STORAGE__.push("uncaught:" + String((event && event.message) || ""));
});
window.__STORAGE__.push("origin:" + String(window.origin));
try {
  window.localStorage.setItem("__FRAME_KEY__", "written");
  window.__STORAGE__.push("write:OK");
} catch (error) {
  window.__STORAGE__.push("write:" + String(error && error.name) + " " + String(error && error.message));
}
try {
  window.__STORAGE__.push("read:" + String(window.localStorage.getItem("__FRAME_KEY__")));
} catch (error) {
  window.__STORAGE__.push("read:" + String(error && error.name) + " " + String(error && error.message));
}
window.__STORAGE__.push(
  "content:" + String(((document.body && document.body.innerText) || "").replace(/\\s+/g, "").length)
);
window.localStorage.removeItem("__FRAME_KEY__");
"""

#: The control document: same engine, same app origin, no sandbox on its own
#: response. The frame around the surface carries the embedder's own sandbox list,
#: so the mounted document gets both the attribute and the response header.
PARENT_PAGE = """<!doctype html><title>Parent</title>
<iframe id="f" src="__SURFACE_URL__" sandbox="allow-scripts allow-popups"></iframe>
<script>
window.__PARENT__ = {};
try {
  window.localStorage.setItem("__PARENT_KEY__", "parent-value");
  window.__PARENT__.write = "OK";
  window.__PARENT__.read = String(window.localStorage.getItem("__PARENT_KEY__"));
} catch (error) {
  window.__PARENT__.write = String(error && error.name) + " " + String(error && error.message);
}
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
    """The real app on a loopback port, with one installed bundle that uses storage."""
    from core import plugin_runtime
    from core.engine_config import artifact_output_dir
    from server import plugin_surface_nonce
    from server.main import create_app
    from server.middleware import init_auth
    import uvicorn

    config = tmp_path_factory.mktemp("storage-home")
    previous = os.environ.get("EPHE_CONFIG_DIR")
    os.environ["EPHE_CONFIG_DIR"] = str(config)
    os.environ["EPHE_OFFLINE"] = "1"
    plugin = config / "plugins" / PLUGIN_ID
    (plugin / "ui").mkdir(parents=True)
    (plugin / "ui" / "index.html").write_text(SURFACE_ENTRY, encoding="utf-8")
    (plugin / "ui" / "probe.js").write_text(
        PROBE_SCRIPT.replace("__FRAME_KEY__", FRAME_KEY), encoding="utf-8"
    )
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
    assert server.started, "the storage server never started"
    nonce = plugin_surface_nonce.mint_surface_nonce(PLUGIN_ID).nonce
    surface = f"/api/plugins/ui/{PLUGIN_ID}/{nonce}/"
    charts = artifact_output_dir()
    parent_name = "storage-parent.html"
    (charts / parent_name).write_text(
        PARENT_PAGE.replace("__SURFACE_URL__", surface).replace("__PARENT_KEY__", PARENT_KEY),
        encoding="utf-8",
    )
    yield {
        "base": f"http://127.0.0.1:{port}",
        "surface": surface,
        "parent": f"/charts/{parent_name}",
        "home": str(config),
    }
    server.should_exit = True
    thread.join(timeout=15.0)
    assert not thread.is_alive(), "the storage server thread outlived the test"
    gone = False
    for _ in range(20):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        except (ConnectionRefusedError, OSError):
            gone = True
            break
        time.sleep(0.1)
    assert gone, "the storage server still answers on its port after teardown"
    if previous is None:
        os.environ.pop("EPHE_CONFIG_DIR", None)
    else:
        os.environ["EPHE_CONFIG_DIR"] = previous


@pytest.fixture(autouse=True)
def _keep_the_storage_home(live, monkeypatch):
    """The suite's autouse home fixture redirects the config root per test; the live
    server resolves its plugin root per request, so the last `setenv` before the
    request decides which home it reads."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", live["home"])
    monkeypatch.setenv("EPHE_OFFLINE", "1")


def _frame_results(frame, wanted: int, timeout: float = 15.0) -> list[str]:
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


def test_the_mount_refuses_page_storage_and_names_the_missing_flag(live):
    """Pin: the write raises, the value never lands, and the control document keeps
    the same API on the same origin."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as refused:
            pytest.skip(f"chromium is not drivable in this lane: {refused}")
        try:
            page = browser.new_page()
            page.goto(live["base"] + live["parent"], wait_until="load")
            frame = next((f for f in page.frames if "/api/plugins/ui/" in f.url), None)
            assert frame is not None, "the mount never framed"
            # The record's combination: the embedder mounts the frame with its own
            # sandbox list, so the pin mounts that attribute beside the header.
            assert page.locator("#f").get_attribute("sandbox") == "allow-scripts allow-popups"
            # origin, write, read, content, the uncaught write = the full picture.
            results = _frame_results(frame, wanted=5)
            joined = " | ".join(results)
            assert "origin:null" in joined, joined
            # the write and the read both raise, and the engine names the reason.
            assert "write:SecurityError" in joined, joined
            assert "sandboxed" in joined.lower(), joined
            assert "allow-same-origin" in joined, joined
            assert "read:SecurityError" in joined, joined
            # a bundle without a `try` produces an uncaught error event as well; its
            # message arrives masked as "Script error." across the opaque origin.
            assert "uncaught:Script error." in joined, joined
            # the document still renders, and the record quotes this exact row.
            assert "content:12" in joined, joined

            # the control: the unsandboxed document on the app origin keeps the API.
            parent = page.evaluate("window.__PARENT__ || {}")
            assert parent.get("write") == "OK", parent
            assert parent.get("read") == "parent-value", parent
            # and the mount's write reached no key in that origin's storage.
            landed = page.evaluate(f"window.localStorage.getItem({FRAME_KEY!r})")
            assert landed is None, landed

            # the mechanism under the measurement: the header grants a sandbox and
            # withholds the one token that would give the document this origin back.
            import httpx

            with httpx.Client(base_url=live["base"], timeout=10.0) as client:
                document = client.get(live["surface"])
                assert document.status_code == 200, document.text
                csp = document.headers["content-security-policy"]
                assert "sandbox allow-scripts allow-popups" in csp, csp
                assert "allow-same-origin" not in csp, csp
        finally:
            browser.close()
