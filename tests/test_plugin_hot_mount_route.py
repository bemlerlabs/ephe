"""W2-16 — the hot-mount route, driven as an HTTP call.

`tests/test_plugin_hot_mount.py` proves the transition; this file proves the seam: that a
request reaches it behind the guards every other plugin mutation has (the XHR marker, the
read-only brake, the signature gate), that a refusal arrives in the envelope the app
already reads, and that the notification a surface waits for is the one an existing
`/api/plugins/events` subscriber receives rather than a second channel to remember.

Two facts only a route can show are pinned here. The alarm a changed contract raises
travels as structured data, because a reader who must accept a change is shown which
field moved. And `If-Match` on this resource is the bundle version, compared inside the
transition against the manifest it just read — a state token of this machine could not
name a bundle the machine has never seen.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.tools.dynamic_registry import default_registry, served_tool_name
from core.tools.registry import execute_tool, invalidate_tool_schema_cache

_PLUGIN = "route-probe"
_TICK = "tick"
_TICK_NAME = served_tool_name(_PLUGIN, _TICK)
_HEADER = {"X-Requested-With": "XMLHttpRequest"}


def _tool(description: str = "Report the seconds left.") -> dict:
    return {
        "name": _TICK,
        "entry": "handlers.py:run",
        "family": "read",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {"unit": {"type": "string"}},
            "required": ["unit"],
        },
    }


def _manifest(tools: list[dict], version: str = "0.1.0") -> dict:
    return {
        "manifest_version": 2,
        "name": _PLUGIN,
        "version": version,
        "description": "A bundle that declares one tool, for the route's own tests.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": tools},
    }


def _write_bundle(root: Path, tools: list[dict], version: str = "0.1.0") -> Path:
    directory = root / _PLUGIN
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(_manifest(tools, version), indent=2), encoding="utf-8"
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    return directory


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(config / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "workspace"))
    from core import audit_log

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    root = tmp_path / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    yield {"root": root, "config": config, "log": log, "tmp": tmp_path}
    default_registry().unregister_plugin(_PLUGIN)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


@pytest.fixture()
def client(lane):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _mount(client, body=None, **extra_headers):
    return client.post(
        f"/api/plugins/{_PLUGIN}/hot-mount",
        json=body if body is not None else {},
        headers={**_HEADER, **extra_headers},
    )


def _detail(response) -> dict:
    payload = response.json()
    inner = payload.get("error", payload)
    detail = inner.get("detail", inner)
    return detail if isinstance(detail, dict) else {}


def _stored(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _served_names() -> list[str]:
    return list(default_registry().names())


def test_a_mount_request_serves_the_tool_and_answers_with_its_version(client, lane):
    """GIVEN a bundle on disk WHEN the route mounts it
    THEN the name is served, the version is the ETag, and a call runs."""
    _write_bundle(lane["root"], [_tool()])

    response = _mount(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["names"] == [_TICK_NAME]
    assert body["first_mount"] is True
    assert body["version"] == "0.1.0"
    assert response.headers["etag"] == "0.1.0"
    payload = json.loads(asyncio.run(execute_tool(_TICK_NAME, {"unit": "seconds"})))
    assert payload["unit"] == "seconds"


def test_a_request_without_the_xhr_marker_is_refused_before_anything_mounts(client, lane):
    """The guard belongs to the router, so a cross-origin form post cannot publish tools."""
    _write_bundle(lane["root"], [_tool()])

    response = client.post(f"/api/plugins/{_PLUGIN}/hot-mount", json={})

    assert response.status_code == 403
    assert _TICK_NAME not in _served_names()


def test_an_if_match_that_does_not_name_the_installed_version_is_a_stale_state(client, lane):
    _write_bundle(lane["root"], [_tool()])

    refused = _mount(client, {"expected_version": "0.1.0"}, **{"If-Match": "9.9.9"})
    accepted = _mount(client, **{"If-Match": "0.1.0"})

    assert refused.status_code == 409
    assert _detail(refused)["code"] == "stale_state"
    assert accepted.status_code == 200, accepted.text


def test_a_changed_contract_is_refused_with_the_diff_and_accepted_by_name(client, lane):
    """The alarm #15 raises arrives as data: a card can show which field moved."""
    directory = _write_bundle(lane["root"], [_tool()])
    assert _mount(client).status_code == 200

    changed = _tool("Now it also deletes the workspace.")
    (directory / "ephe-plugin.json").write_text(
        json.dumps(_manifest([changed]), indent=2), encoding="utf-8"
    )
    plugin_runtime.invalidate_ownership_cache()

    refused = _mount(client)
    assert refused.status_code == 409
    assert _detail(refused)["code"] == "mount_change_unacknowledged"
    diff = _detail(refused)["diff"]
    assert [item["name"] for item in diff] == [_TICK_NAME]
    assert "description" in diff[0]["changed"]
    assert diff[0]["new_description"] == changed["description"]

    acknowledged = _mount(client, {"acknowledge": [_TICK_NAME]})
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["diff"][0]["name"] == _TICK_NAME


def test_the_read_only_brake_refuses_a_mount_the_way_it_refuses_a_switch(
    client, lane, monkeypatch
):
    from core import plugin_switch_policy

    _write_bundle(lane["root"], [_tool()])
    monkeypatch.setattr(plugin_switch_policy, "read_only", lambda: True)

    response = _mount(client)

    assert response.status_code == 423
    assert _detail(response)["code"] == plugin_switch_policy.READ_ONLY_CODE
    assert _TICK_NAME not in _served_names()


def test_a_bundle_whose_signature_record_went_missing_is_refused_at_the_mount(
    client, lane, monkeypatch
):
    """The route asks the gate enabling asks; the word it answers is that gate's."""
    from core import plugin_signing

    _write_bundle(lane["root"], [_tool()])
    monkeypatch.setattr(
        plugin_signing,
        "verify_enable",
        lambda _plugin: (False, "signature_record_missing"),
    )

    response = _mount(client)

    assert response.status_code == 409
    assert "signature_record_missing" in response.text
    assert _TICK_NAME not in _served_names()


def test_an_unmount_request_removes_the_name_and_a_later_call_is_a_coded_refusal(
    client, lane
):
    _write_bundle(lane["root"], [_tool()])
    assert _mount(client).status_code == 200

    response = client.request(
        "DELETE", f"/api/plugins/{_PLUGIN}/hot-mount", headers=_HEADER
    )

    assert response.status_code == 200, response.text
    assert response.json()["removed"] == [_TICK_NAME]
    assert _TICK_NAME not in _served_names()
    assert "is not available" in asyncio.run(execute_tool(_TICK_NAME, {"unit": "s"}))


def test_a_mount_for_a_bundle_that_is_not_installed_is_a_404(client, lane):
    response = _mount(client)

    assert response.status_code == 404
    assert _detail(response)["code"] == "unknown_plugin"


def test_a_malformed_acknowledge_list_is_a_400_naming_the_field(client, lane):
    _write_bundle(lane["root"], [_tool()])

    response = _mount(client, {"acknowledge": _TICK_NAME})

    assert response.status_code == 400
    assert _detail(response)["code"] == "invalid_request"
    assert _detail(response)["field"] == "acknowledge"


def test_the_mount_notifies_the_existing_plugin_event_stream(client, lane):
    """No second channel: a surface already subscribed to /api/plugins/events sees this."""
    _write_bundle(lane["root"], [_tool()])
    from core.plugin_lifecycle import STATE_FILENAME, subscribe, unsubscribe

    subscriber = subscribe(lane["config"] / STATE_FILENAME)
    seen: list[dict] = []
    stop = threading.Event()

    def pump() -> None:
        while not stop.is_set():
            try:
                seen.append(subscriber.get(timeout=0.2))
            except Exception:  # noqa: BLE001 — an empty queue is this loop's clock
                continue

    worker = threading.Thread(target=pump, daemon=True)
    worker.start()
    try:
        assert _mount(client).status_code == 200
        for _ in range(50):
            if seen:
                break
            threading.Event().wait(0.1)
    finally:
        stop.set()
        worker.join(timeout=1)
        unsubscribe(subscriber)

    assert seen, "the mount published no event on the stream a surface already reads"
    assert any(_PLUGIN in json.dumps(row["data"]) for row in seen), seen


def test_the_mount_writes_one_audit_row_for_the_transition_it_ran(client, lane):
    _write_bundle(lane["root"], [_tool()])

    assert _mount(client).status_code == 200

    rows = [
        row
        for row in _stored(lane["log"])
        if row.get("kind") == "plugin_lifecycle"
        and row.get("decision") == "mount"
        and row.get("tool") == _PLUGIN
    ]
    assert len(rows) == 1, _stored(lane["log"])
    assert rows[0]["status"] == "committed"
    assert "version=0.1.0" in rows[0]["detail"]
    assert "scope=mount" in rows[0]["detail"]
