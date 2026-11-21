"""A declared plugin surface's capabilities, observed in a real engine.

`core/plugin_ui_capabilities.py` names the layer that confines `webgl`, `wasm`
and `audio-out`: the surface feature policy. This file is the witness that
record points at. Two bundles go through the real route — one declares the
three, one declares none — and a real engine says what each document can reach:
the undeclared document finds WebGL contexts, WebAssembly and audio output gone,
the declared one finds them present, and its WebAssembly compiles because the
route widened `script-src` for that surface alone.

An engine that cannot boot is skipped by name, so a green row is never a row
nobody watched.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.support.free_port import free_port

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DECLARED = "acme-cap-declared"
PLAIN = "acme-cap-plain"

ENTRY = "<!doctype html><title>Capability probe</title>"

#: Read in the page's own world, after the mount's policy has run. Playwright
#: evaluates over CDP, so the closed `script-src` on the document does not
#: silence this probe the way it silences an inline `<script>`.
PROBE = """
(() => {
  const canvas = document.createElement('canvas');
  let webgl = 'error';
  try { webgl = canvas.getContext('webgl') ? 'present' : 'absent'; } catch (error) { webgl = 'error'; }
  const wasm = typeof WebAssembly === 'undefined' ? 'absent' : 'present';
  let audio = 'absent';
  if (typeof AudioContext !== 'undefined' || typeof webkitAudioContext !== 'undefined') audio = 'present';
  return { webgl, wasm, audio };
})()
"""

COMPILE = (
    "async () => { try { await WebAssembly.compile(new Uint8Array([0,97,115,109,1,0,0,0]));"
    " return 'compiled'; } catch (error) { return 'refused:' + error.name; } }"
)


def _probe(page, url: str) -> dict:
    page.goto(url, wait_until="load")
    return page.evaluate(PROBE)


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """The real app on a loopback port, with one declaring bundle and one plain."""
    import uvicorn

    from core import plugin_runtime
    from server import plugin_surface_nonce
    from server.main import create_app
    from server.middleware import init_auth

    config = tmp_path_factory.mktemp("capability-home")
    previous = os.environ.get("EPHE_CONFIG_DIR")
    os.environ["EPHE_CONFIG_DIR"] = str(config)
    os.environ["EPHE_OFFLINE"] = "1"
    for plugin_id, capabilities in (
        (DECLARED, ["webgl", "wasm", "audio-out"]),
        (PLAIN, []),
    ):
        plugin = config / "plugins" / plugin_id
        (plugin / "ui").mkdir(parents=True)
        (plugin / "ui" / "index.html").write_text(ENTRY, encoding="utf-8")
        manifest = {
            "manifest_version": 1,
            "name": plugin_id,
            "version": "1.0.0",
            "description": "A surface that states the capabilities it reaches for",
            "permissions": {"tool_families": [], "data_roots": []},
            "components": {
                "skills": [],
                "commands": [],
                "ui": {
                    "type": "floating-window",
                    "entry": "ui/index.html",
                    "title": "Capabilities",
                    "capabilities": capabilities,
                },
            },
        }
        (plugin / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (config / "plugin-state.json").write_text(
        json.dumps({"schema": 1, "pause_all": False, "plugins": {}}), encoding="utf-8"
    )
    plugin_runtime.invalidate_ownership_cache()
    init_auth(lan_mode=False)

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20.0
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the capability server never started"
    base = f"http://127.0.0.1:{port}"
    surfaces = {
        plugin_id: (
            f"/api/plugins/ui/{plugin_id}/"
            f"{plugin_surface_nonce.mint_surface_nonce(plugin_id).nonce}/"
        )
        for plugin_id in (DECLARED, PLAIN)
    }
    yield {"base": base, "surfaces": surfaces, "home": str(config)}
    server.should_exit = True
    thread.join(timeout=15.0)
    assert not thread.is_alive(), "the capability server thread outlived the test"
    if previous is None:
        os.environ.pop("EPHE_CONFIG_DIR", None)
    else:
        os.environ["EPHE_CONFIG_DIR"] = previous


@pytest.fixture(autouse=True)
def _keep_the_capability_home(live, monkeypatch):
    """The server's own environment for the length of a test."""
    for name, value in (("EPHE_CONFIG_DIR", live["home"]), ("EPHE_OFFLINE", "1")):
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("engine_name", ["chromium", "webkit"])
def test_an_undeclared_surface_cannot_reach_the_three_capabilities(live, engine_name):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = getattr(playwright, engine_name).launch()
        except Exception as refused:
            pytest.skip(f"{engine_name} is not drivable in this lane: {refused}")
        try:
            page = browser.new_page()
            reached = _probe(page, live["base"] + live["surfaces"][PLAIN])
            assert reached["webgl"] == "absent", reached
            assert reached["wasm"] == "absent", reached
            assert reached["audio"] == "absent", reached
        finally:
            browser.close()


@pytest.mark.parametrize("engine_name", ["chromium", "webkit"])
def test_a_declared_surface_reaches_the_three_capabilities(live, engine_name):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = getattr(playwright, engine_name).launch()
        except Exception as refused:
            pytest.skip(f"{engine_name} is not drivable in this lane: {refused}")
        try:
            page = browser.new_page()
            reached = _probe(page, live["base"] + live["surfaces"][DECLARED])
            assert reached["webgl"] == "present", reached
            assert reached["wasm"] == "present", reached
            assert reached["audio"] == "present", reached
            assert page.evaluate(COMPILE) == "compiled", reached
        finally:
            browser.close()
