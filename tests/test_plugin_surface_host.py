"""The host half of a plugin surface, beside the mount record.

Slot, box, and whether the window is open are the whole record. A page
field is refused. A damaged section leaves the committed switches alone.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLUGIN = "web-research"


def _record(**over: object) -> dict:
    body = {
        "slot": "overlay",
        "x": 120,
        "y": 40,
        "width": 360,
        "height": 240,
        "open": True,
        "minimized": False,
        "placed": True,
    }
    body.update(over)
    return body


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


@pytest.fixture()
def client(device):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client


def test_a_page_field_is_refused_and_stores_nothing(client, device) -> None:
    body = _record()
    body["url"] = "http://127.0.0.1:8765/api/plugins/ui/web-research/n0nce/"
    body["scroll"] = 80
    response = client.put(f"/api/plugins/{PLUGIN}/surface-host", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["reason_code"] == "invalid_request"
    state = device / "plugin-state.json"
    if state.exists():
        raw = json.loads(state.read_text(encoding="utf-8"))
        assert PLUGIN not in (raw.get("surfaces") or {})
        assert "n0nce" not in state.read_text(encoding="utf-8")


def test_the_host_record_survives_a_new_process(client, device) -> None:
    response = client.put(f"/api/plugins/{PLUGIN}/surface-host", json=_record())
    assert response.status_code == 200
    assert response.json()["surface"]["slot"] == "overlay"

    from core.plugin_lifecycle import PluginLifecycle

    fresh = PluginLifecycle(
        device / "plugin-state.json",
        versions={PLUGIN: "1"},
        audit_sink=lambda _entry: None,
    )
    stored = fresh.surface_hosts()[PLUGIN]
    assert stored == _record()
    listed = client.get("/api/plugins/surface-hosts").json()["surfaces"][PLUGIN]
    assert listed == _record()


def test_a_canvas_overlay_is_a_record_the_shell_can_keep(client) -> None:
    response = client.put(
        f"/api/plugins/{PLUGIN}/surface-host", json=_record(slot="canvas-overlay")
    )
    assert response.status_code == 200
    assert response.json()["surface"]["slot"] == "canvas-overlay"


def test_a_dock_panel_is_not_a_placement_the_shell_can_keep(client) -> None:
    response = client.put(
        f"/api/plugins/{PLUGIN}/surface-host", json=_record(slot="dock-panel")
    )
    assert response.status_code == 400
    assert response.json()["error"]["reason_code"] == "invalid_request"


def test_the_slot_vocabulary_is_the_one_the_shell_carries() -> None:
    from core.plugin_surface_host import SLOTS

    assert SLOTS == frozenset({"overlay", "native", "canvas-overlay"})


def test_an_unknown_bundle_is_refused(client) -> None:
    response = client.put("/api/plugins/not-a-bundle/surface-host", json=_record())
    assert response.status_code == 404
    assert response.json()["error"]["reason_code"] == "plugin_unknown"


def test_the_read_only_brake_leaves_placement_writable(client) -> None:
    from core.settings_schema import save_deep_settings

    assert save_deep_settings({"plugins": {"plugins.plugin_lifecycle_read_only": True}})
    response = client.put(
        f"/api/plugins/{PLUGIN}/surface-host",
        json=_record(slot="native", open=False, placed=False),
    )
    assert response.status_code == 200
    assert response.json()["surface"]["open"] is False


def test_a_damaged_surfaces_section_leaves_the_switch(device) -> None:
    path = device / "plugin-state.json"
    valid = _record()
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "plugins": {PLUGIN: {"user": {"committed": "enabled"}}},
                "surfaces": {
                    PLUGIN: valid,
                    "other-plugin": {**valid, "url": "http://evil.example/page"},
                    "broken": "nope",
                },
            }
        ),
        encoding="utf-8",
    )
    from core.plugin_lifecycle import PluginLifecycle

    life = PluginLifecycle(path, versions={PLUGIN: "1"}, audit_sink=lambda _entry: None)
    assert life.snapshot(PLUGIN).enabled is True
    assert set(life.surface_hosts()) == {PLUGIN}
    assert life.surface_hosts()[PLUGIN] == valid
