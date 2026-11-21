"""PERF-BE-FIX 2 — one `GET /api/plugins` reuses one portfolio scan, not three.

`plugins_view` asked the folder scan three times (installed rows, catalogue manifest
facts, state usage) and parsed every manifest in each pass: 3 scans, 69 parses, 117
file opens per request, p50 52 ms in `/tmp/rel/PERF-BE-REPORT.md` §3.3. The view now
scans once per request and keeps that scan for a short window, keyed by a folder
signature so a bundle that appears on disk is still listed on the next request.

The switch truth stays outside the cache: it is read per request from the lifecycle,
so a toggle can never wait for a scan window to expire.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.plugin_bundle import mark_installed, write_bundle


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_BUILTIN_PLUGINS_ROOT", str(builtin))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import plugin_manifest, plugin_runtime

    monkeypatch.setattr(plugin_manifest, "BUILTIN_PLUGINS_ROOT", builtin)
    from core import plugin_scan_cache

    plugin_scan_cache.invalidate()
    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_scan_cache.invalidate()
    plugin_runtime.invalidate_ownership_cache()


def _counted_scans(monkeypatch) -> Counter:
    from core import plugin_manifest

    calls: Counter = Counter()
    real = plugin_manifest.scan_plugins

    def counted(*args, **kwargs):
        calls["scan_plugins"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(plugin_manifest, "scan_plugins", counted)
    return calls


def _client():
    from server.main import create_app

    return TestClient(create_app())


def test_one_request_scans_the_portfolio_once(device, monkeypatch):
    """GIVEN two installed bundles WHEN `/api/plugins` answers THEN the folders were
    walked once (before the change: three times, one per view section)."""
    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)
    write_bundle(device / "plugins", "second-widget", tool="later")
    mark_installed("second-widget", enabled=False)

    from core import plugin_scan_cache

    with _client() as client:
        client.get("/api/plugins")  # warm the ownership view the request reads too
        plugin_scan_cache.invalidate()
        calls = _counted_scans(monkeypatch)
        response = client.get("/api/plugins")

    assert response.status_code == 200
    assert calls["scan_plugins"] == 1, f"one request scanned {calls['scan_plugins']} times"


def test_the_second_request_reuses_the_scan_and_answers_the_same_bytes(device, monkeypatch):
    """GIVEN a warm scan WHEN the same view is requested again THEN the folders are not
    walked and the body is byte-identical."""
    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)

    with _client() as client:
        calls = _counted_scans(monkeypatch)
        first = client.get("/api/plugins")
        after_first = calls["scan_plugins"]
        second = client.get("/api/plugins")

    assert first.status_code == second.status_code == 200
    assert calls["scan_plugins"] == after_first, "the cached scan was not reused"
    assert first.content == second.content, "the cached scan changed the answer"


def test_a_bundle_that_appears_on_disk_is_listed_without_waiting(device, monkeypatch):
    """GIVEN a served view WHEN a folder is written behind the cache THEN the next
    request lists it, because the signature the cache keys on moved."""
    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)

    with _client() as client:
        assert "late-widget" not in [
            row["name"] for row in client.get("/api/plugins").json()["installed"]
        ]
        write_bundle(device / "plugins", "late-widget")
        names = [
            row["name"] for row in client.get("/api/plugins").json()["installed"]
        ]

    assert "late-widget" in names, "the scan window outlived the folder it described"


def test_the_ownership_invalidation_drops_the_scan(device, monkeypatch):
    """GIVEN a warm scan WHEN the ownership cache is invalidated THEN the next read
    walks the folders again."""
    from core import plugin_scan_cache, plugin_runtime

    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)

    plugin_scan_cache.scan()
    calls = _counted_scans(monkeypatch)
    assert plugin_scan_cache.scan() == plugin_scan_cache.scan()
    assert calls["scan_plugins"] == 0, "the warm window walked the folders"

    plugin_runtime.invalidate_ownership_cache()
    plugin_scan_cache.scan()
    assert calls["scan_plugins"] == 1, "the invalidation left the scan in place"


def test_a_toggle_is_not_delayed_by_the_scan_window(device):
    """GIVEN a warm scan WHEN the switch flips THEN the same request reports the new
    state, because the switch is read outside the folder cache."""
    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)

    with _client() as client:
        before = client.get("/api/plugins").json()
        mark_installed("hello-widget", enabled=True)
        after = client.get("/api/plugins").json()

    def enabled(view: dict) -> bool:
        return next(
            row["enabled"] for row in view["installed"] if row["name"] == "hello-widget"
        )

    assert enabled(before) is False
    assert enabled(after) is True, "a switch flip waited for the scan window"
