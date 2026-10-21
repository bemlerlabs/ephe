"""FLAG-01 (owner decision O-10, 2026-10-21): the read-only switch brake.

The brake blocks every switch mutation route with HTTP 423
``plugin_lifecycle_read_only``, writes one audit entry per refusal, changes no
state and calls no activator. Reads, SSE and command discovery stay available.
It is not the old ``master_enabled`` bypass and never disables a plugin.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

READ_ONLY_CODE = "plugin_lifecycle_read_only"


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import audit_log, plugin_runtime

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    plugin_runtime.invalidate_ownership_cache()
    yield config, log
    plugin_runtime.invalidate_ownership_cache()


@pytest.fixture()
def client(device):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client


def _set_read_only(value: bool) -> None:
    from core.settings_schema import save_deep_settings

    assert save_deep_settings(
        {"plugins": {"plugins.plugin_lifecycle_read_only": value}}
    )


def _refusals(log: Path) -> list[dict]:
    if not log.exists():
        return []
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line.get("decision") == "read_only_refused"]


def _four_mutations(client) -> list:
    return [
        client.put("/api/plugins/web-research/enabled", json={"enabled": False}),
        client.post("/api/plugins/web-research/enable", json={"enabled": True}),
        client.post("/api/plugins/master", json={"enabled": False}),
        client.post("/api/plugins/web-research/cancel", json={"scope": "user"}),
    ]


def test_read_only_off_keeps_the_normal_switch(client) -> None:
    _set_read_only(False)
    response = client.put("/api/plugins/web-research/enabled", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_read_only_on_refuses_all_four_mutation_routes(client, device) -> None:
    _set_read_only(True)
    responses = _four_mutations(client)
    assert [response.status_code for response in responses] == [423, 423, 423, 423]
    for response in responses:
        assert response.json()["error"]["detail"]["code"] == READ_ONLY_CODE

    refusals = _refusals(device[1])
    assert len(refusals) == 4
    assert all(line["status"] == "refused" for line in refusals)
    assert all(READ_ONLY_CODE in line["detail"] for line in refusals)
    assert {line["tool"] for line in refusals} == {"", "web-research"}
    assert all("action=" in line["detail"] for line in refusals)


def test_read_only_on_writes_nothing_and_calls_no_activator(
    client, device, monkeypatch
) -> None:
    from core import plugin_runtime

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(plugin_runtime, "_activate", lambda name: calls.append(("on", name)))
    monkeypatch.setattr(
        plugin_runtime, "_deactivate", lambda name: calls.append(("off", name))
    )
    plugin_runtime.invalidate_ownership_cache()

    _set_read_only(True)
    state_file = device[0] / "plugin-state.json"
    before = state_file.read_bytes() if state_file.exists() else None

    assert [r.status_code for r in _four_mutations(client)] == [423, 423, 423, 423]

    after = state_file.read_bytes() if state_file.exists() else None
    assert after == before
    assert calls == []
    assert plugin_runtime.lifecycle().snapshot("web-research").enabled is True


def test_reads_and_sse_stay_available(client, device) -> None:
    _set_read_only(True)
    view = client.get("/api/plugins")
    assert view.status_code == 200
    assert view.json()["read_only"] is True
    assert client.get("/api/plugins/commands").status_code == 200

    from fastapi.responses import StreamingResponse

    from server.routes.plugins import get_plugin_events

    events = get_plugin_events()
    assert isinstance(events, StreamingResponse)
    assert events.status_code == 200


def test_a_malformed_state_is_unproven_and_never_falls_back_to_legacy(
    client, device
) -> None:
    config = device[0]
    config.mkdir(parents=True, exist_ok=True)
    (config / "plugin-state.json").write_text(
        json.dumps({"schema": 1, "plugins": "not-a-dict"}), encoding="utf-8"
    )
    (config / "plugins.json").write_text(
        json.dumps(
            {
                "master_enabled": False,
                "plugins": [{"name": "web-research", "enabled": True}],
            }
        ),
        encoding="utf-8",
    )

    view = client.get("/api/plugins").json()

    assert view["unproven"] is True
    assert view["read_only"] is False
    assert all(entry["enabled"] is False for entry in view["public"])
    assert view["master_enabled"] is True
    assert any(
        notice["code"] == "plugin_state_unproven" for notice in view["notices"]
    )


def test_a_state_read_error_is_unproven_and_never_falls_back_to_legacy(
    client, device, monkeypatch
) -> None:
    from core import plugin_runtime

    config = device[0]
    config.mkdir(parents=True, exist_ok=True)
    (config / "plugins.json").write_text(
        json.dumps(
            {
                "master_enabled": True,
                "plugins": [{"name": "web-research", "enabled": True}],
            }
        ),
        encoding="utf-8",
    )

    def unavailable(names, registry_file=None):
        raise RuntimeError("state read failed")

    monkeypatch.setattr(plugin_runtime, "store_state", unavailable)

    view = client.get("/api/plugins").json()

    assert view["unproven"] is True
    assert view["master_enabled"] is False
    assert all(entry["enabled"] is False for entry in view["public"])
    assert any(
        notice["code"] == "plugin_state_unproven" for notice in view["notices"]
    )


def test_the_setting_flip_takes_effect_on_the_next_request(client) -> None:
    _set_read_only(True)
    assert client.put(
        "/api/plugins/web-research/enabled", json={"enabled": False}
    ).status_code == 423

    _set_read_only(False)
    assert client.put(
        "/api/plugins/web-research/enabled", json={"enabled": False}
    ).status_code == 200


def test_the_legacy_routes_cannot_bypass_read_only(client) -> None:
    _set_read_only(True)
    legacy = client.post("/api/plugins/web-research/enable", json={"enabled": True})
    master = client.post("/api/plugins/master", json={"enabled": True})
    assert legacy.status_code == 423
    assert master.status_code == 423
    assert legacy.json()["error"]["detail"]["code"] == READ_ONLY_CODE
    assert master.json()["error"]["detail"]["code"] == READ_ONLY_CODE


def test_an_inflight_transition_may_finish_but_no_new_one_starts(
    client, device, monkeypatch
) -> None:
    from core import plugin_runtime

    started = threading.Event()
    release = threading.Event()

    def slow_activate(name: str) -> None:
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(plugin_runtime, "_activate", slow_activate)
    plugin_runtime.invalidate_ownership_cache()

    lifecycle = plugin_runtime.lifecycle()
    assert lifecycle.set_enabled("web-research", False).state.value == "disabled"

    result: dict[str, object] = {}
    thread = threading.Thread(
        target=lambda: result.update(snap=lifecycle.set_enabled("web-research", True))
    )
    thread.start()
    assert started.wait(timeout=5)

    _set_read_only(True)
    refused = client.put(
        "/api/plugins/web-research/enabled", json={"enabled": False}
    )
    assert refused.status_code == 423

    release.set()
    thread.join(timeout=5)
    assert result["snap"].state.value == "enabled"
    view = client.get("/api/plugins").json()
    assert view["read_only"] is True
    assert next(
        p for p in view["public"] if p["name"] == "web-research"
    )["enabled"] is True


def test_install_autorun_does_not_bypass_read_only(device, monkeypatch) -> None:
    from core import plugin_market, plugin_runtime
    from core.settings_schema import save_deep_settings

    config = device[0]
    plugin_dir = config / "plugins" / "acme-research"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "acme-research",
                "version": "1.0.0",
                "description": "Acme research",
                "permissions": {"tool_families": [], "data_roots": []},
                "components": {"skills": [], "commands": [], "tools": []},
            }
        ),
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()
    assert save_deep_settings(
        {
            "plugins": {
                "plugins.plugin_autorun": True,
                "plugins.plugin_lifecycle_read_only": True,
            }
        }
    )

    plugin_market._register_installed("acme-research")

    registry = json.loads((config / "plugins.json").read_text(encoding="utf-8"))
    installed = next(p for p in registry["plugins"] if p["name"] == "acme-research")
    assert installed["enabled"] is False
    assert plugin_dir.is_dir()
    assert (
        plugin_runtime.lifecycle().snapshot("acme-research").state.value
        == "disabled"
    )
