"""Enable means usable: the switch and the mount are one step.

Measured against the running 0.6.4 build (owner test):
`PUT /api/plugins/live-probe/enabled {"enabled": true}` answered 200, the tool was missing
from the offer, and only `POST /api/plugins/{id}/hot-mount` made it usable. A reader who
switches a bundle on reads that 200 as "it works", so the switch owes the mount in the
same answer.

What this file pins:

- an enable that settled on `enabled` has mounted the bundle — the names are in the tool
  gate, in the offer and in the lifecycle's own mount record;
- a mount that refuses answers a coded `mount_failed` with the reason and the move, and
  the switch does not stay half set: an enable that flipped the switch takes it back to
  where it was, and an enable of an already-on bundle leaves it on with the tool set the
  last accepted mount published;
- a disable takes the names back — gate, offer and the surface a held credential still
  points at;
- the legacy `POST .../enable` shim runs the same two movements, with the one-release
  payload it has always answered;
- `POST .../surface-token` on a switched-off bundle is a coded conflict that names the
  switch, not a bare 401;
- both directions are idempotent: two enables, two disables and an enable → disable →
  enable end in one unambiguous state.

The members this file does not re-pin are the ones it must not weaken: the ETag and the
stale-If-Match refusal, the read-only brake and the signature gate still answer before
anything is published, and the 202 path is untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.plugin_lifecycle import LifecycleError
from core.plugin_lifecycle_types import REFUSE_REGISTRY
from core.tools.dynamic_registry import default_registry, served_tool_name
from core.tools.registry import get_tool_schemas, invalidate_tool_schema_cache

_PLUGIN = "mount-probe"
_TOOL = "tick"
_SERVED = served_tool_name(_PLUGIN, _TOOL)
_HEADER = {"X-Requested-With": "XMLHttpRequest"}


def _manifest() -> dict:
    return {
        "manifest_version": 2,
        "name": _PLUGIN,
        "version": "0.1.0",
        "description": "A bundle that declares one tool and one surface.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "tools": [
                {
                    "name": _TOOL,
                    "entry": "handlers.py:run",
                    "family": "read",
                    "description": "Report the seconds left.",
                    "parameters": {
                        "type": "object",
                        "properties": {"unit": {"type": "string"}},
                        "required": ["unit"],
                    },
                }
            ],
            "ui": {
                "type": "floating-window",
                "entry": "ui/index.html",
                "title": "Probe",
                "capabilities": [],
            },
        },
    }


def _write_bundle(root: Path) -> Path:
    directory = root / _PLUGIN
    (directory / "ui").mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(_manifest(), indent=2), encoding="utf-8"
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    return {'unit': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    (directory / "ui" / "index.html").write_text(
        "<!doctype html><title>Probe</title>", encoding="utf-8"
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
        test_client.headers.update(_HEADER)
        yield test_client


def _enable(client, **extra):
    return client.put(
        f"/api/plugins/{_PLUGIN}/enabled", json={"enabled": True, **extra}
    )


def _disable(client, **extra):
    return client.put(
        f"/api/plugins/{_PLUGIN}/enabled", json={"enabled": False, **extra}
    )


def _detail(response) -> dict:
    payload = response.json()
    inner = payload.get("error", payload)
    detail = inner.get("detail", inner)
    return detail if isinstance(detail, dict) else {}


def _rows(log: Path, kind: str = "plugin_lifecycle") -> list[dict]:
    if not log.exists():
        return []
    entries = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [entry for entry in entries if entry.get("kind") == kind]


def _served() -> tuple[str, ...]:
    return default_registry().names()


def _offered() -> set[str]:
    """The names the model is offered, which is what a missing tool actually broke."""
    return {
        str(entry.get("function", {}).get("name") or "")
        for entry in get_tool_schemas()
    }


def _mount_record(lane) -> dict:
    return plugin_runtime.lifecycle().mount_records().get(_PLUGIN) or {}


def _state_file(lane) -> dict:
    return json.loads((lane["config"] / "plugin-state.json").read_text(encoding="utf-8"))


def _switch_rows(lane, decision: str) -> list[dict]:
    return [
        row
        for row in _rows(lane["log"])
        if row.get("decision") == decision
        and row.get("tool") == _PLUGIN
        and row.get("status") == "committed"
    ]


def test_an_enable_mounts_the_bundle_in_one_step(client, lane):
    """GIVEN a bundle on disk that nobody mounted
    WHEN the switch is turned on
    THEN the answer says it is mounted, the name is in the gate and the offer, and the
    answer keeps the ETag of the switch it committed."""
    _write_bundle(lane["root"])

    response = _enable(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "enabled"
    assert body["mounted"] is True
    assert body["names"] == [_SERVED]
    assert response.headers["etag"] == body["etag"]
    assert _SERVED in _served()
    assert _SERVED in _offered()
    assert plugin_runtime.tool_gate(_SERVED).visible is True


def test_the_lifecycle_snapshot_keeps_the_names_the_enable_published(client, lane):
    """The mount records what it published, so a restart replays a switch that was on."""
    _write_bundle(lane["root"])

    assert _enable(client).status_code == 200

    record = _mount_record(lane)
    assert record["names"] == [_SERVED]
    assert record["version"] == "0.1.0"
    assert _state_file(lane)["mounts"][_PLUGIN]["names"] == [_SERVED]


def test_a_second_enable_leaves_one_served_set_and_one_switch_row(client, lane):
    """GIVEN a bundle already on and mounted
    WHEN the same enable arrives again
    THEN nothing doubles: one name, one mounted set, one committed switch row."""
    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200

    again = _enable(client)

    assert again.status_code == 200, again.text
    assert again.json()["mounted"] is True
    assert _served().count(_SERVED) == 1
    assert len(_switch_rows(lane, "enable")) == 1
    assert _mount_record(lane)["names"] == [_SERVED]


def test_a_failed_mount_answers_a_coded_refusal_and_takes_the_switch_back(
    client, lane, monkeypatch
):
    """GIVEN a switched-off bundle whose mount refuses at the registry step
    WHEN the switch is turned on
    THEN the answer is a coded `mount_failed` naming the cause and the move, the switch is
    back where it was, and nothing is published anywhere."""
    from core.plugin_lifecycle import PluginLifecycle

    _write_bundle(lane["root"])
    assert _disable(client).status_code == 200

    def _refuse(_self, _plugin, _descriptors):
        raise LifecycleError(REFUSE_REGISTRY, 409, "injected: the batch was refused")

    monkeypatch.setattr(PluginLifecycle, "_mount_publish_descriptors", _refuse)

    response = _enable(client)

    assert response.status_code == 409, response.text
    detail = _detail(response)
    assert detail["code"] == "mount_failed"
    assert detail["cause"] == REFUSE_REGISTRY
    assert detail["rolled_back"] is True
    assert detail["next"], "a failed enable has to leave the reader a move"
    assert detail["current"]["enabled"] is False
    assert detail["current"]["state"] == "disabled"
    assert _SERVED not in _served()
    assert _SERVED not in _offered()
    assert plugin_runtime.tool_gate(_SERVED).visible is False
    assert _mount_record(lane) == {}
    assert _state_file(lane)["plugins"][_PLUGIN]["user"]["committed"] == "disabled"
    # The rollback of the mount restored the lockfile the pins were written to.
    assert not (lane["config"] / "plugin-lock.json").exists()


def test_a_failed_mount_never_switches_off_a_bundle_that_read_on(client, lane, monkeypatch):
    """A bundle with no switch record reads as on (the lifecycle's documented default).

    An enable of such a bundle writes the explicit value; it did not move the effective
    position, so a refused mount takes nothing back and the answer says so. Switching it
    off here would be this route changing a state the caller never set.
    """
    from core.plugin_lifecycle import PluginLifecycle

    _write_bundle(lane["root"])

    def _refuse(_self, _plugin, _descriptors):
        raise LifecycleError(REFUSE_REGISTRY, 409, "injected: the batch was refused")

    monkeypatch.setattr(PluginLifecycle, "_mount_publish_descriptors", _refuse)

    response = _enable(client)

    assert response.status_code == 409, response.text
    detail = _detail(response)
    assert detail["code"] == "mount_failed"
    assert detail["rolled_back"] is False
    assert detail["current"]["enabled"] is True
    assert _SERVED not in _served()
    assert _SERVED not in _offered()


def test_a_failed_remount_leaves_an_already_on_bundle_serving(client, lane, monkeypatch):
    """GIVEN an enabled bundle that is already mounted
    WHEN a second enable's mount refuses
    THEN the answer is the same coded refusal, the switch stays on, and the tool set the
    last accepted mount published is still served."""
    from core.plugin_lifecycle import PluginLifecycle

    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200

    def _refuse(_self, _plugin, _descriptors):
        raise LifecycleError(REFUSE_REGISTRY, 409, "injected: the batch was refused")

    monkeypatch.setattr(PluginLifecycle, "_mount_publish_descriptors", _refuse)

    response = _enable(client)

    assert response.status_code == 409, response.text
    detail = _detail(response)
    assert detail["code"] == "mount_failed"
    assert detail["rolled_back"] is False
    assert detail["current"]["enabled"] is True
    assert _SERVED in _served()
    assert _SERVED in _offered()
    assert plugin_runtime.tool_gate(_SERVED).visible is True


def test_a_refused_switch_mounts_nothing(client, lane):
    """The ETag guard still answers first: a stale If-Match publishes no tool."""
    _write_bundle(lane["root"])

    response = client.put(
        f"/api/plugins/{_PLUGIN}/enabled",
        json={"enabled": True},
        headers={"If-Match": "9.9.9"},
    )

    assert response.status_code == 409
    assert _detail(response)["code"] == "stale_state"
    assert _SERVED not in _served()
    assert _SERVED not in _offered()
    assert _mount_record(lane) == {}
    assert not (lane["config"] / "plugin-lock.json").exists()
    assert not (lane["config"] / "plugin-state.json").exists()


def test_a_changed_tool_contract_refuses_the_enable_and_carries_the_diff(client, lane):
    """The pin alarm #4 raises on a mount is not lost on the way through the switch.

    GIVEN a bundle whose declared tool description moved after the accepted mount
    WHEN it is switched on again
    THEN the answer is `mount_failed` with the mount's own code and the structured diff,
    and the switch is back off — the reader accepts the change, then enables."""
    directory = _write_bundle(lane["root"])
    assert _enable(client).status_code == 200
    manifest = json.loads((directory / "ephe-plugin.json").read_text(encoding="utf-8"))
    manifest["components"]["tools"][0]["description"] = "Now it also deletes the workspace."
    (directory / "ephe-plugin.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    plugin_runtime.invalidate_ownership_cache()
    assert _disable(client).status_code == 200

    response = _enable(client)

    assert response.status_code == 409, response.text
    detail = _detail(response)
    assert detail["code"] == "mount_failed"
    assert detail["cause"] == "mount_change_unacknowledged"
    assert [item["name"] for item in detail["diff"]] == [_SERVED]
    assert "description" in detail["diff"][0]["changed"]
    assert detail["rolled_back"] is True
    assert _SERVED not in _served()
    assert _SERVED not in _offered()


def test_the_read_only_brake_stops_the_mount_too(client, lane, monkeypatch):
    """The brake answers before the switch, so nothing is published on its way out."""
    from core import plugin_switch_policy

    _write_bundle(lane["root"])
    monkeypatch.setattr(plugin_switch_policy, "read_only", lambda: True)

    response = _enable(client)

    assert response.status_code == 423
    assert _detail(response)["code"] == plugin_switch_policy.READ_ONLY_CODE
    assert _SERVED not in _served()
    assert _SERVED not in _offered()
    assert _mount_record(lane) == {}


def test_a_bundle_with_no_tool_is_enabled_without_a_mount_claim(client, lane):
    """An enable that published nothing says so."""
    root = lane["root"]
    directory = root / _PLUGIN
    (directory / "ui").mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    manifest["components"]["tools"] = []
    (directory / "ephe-plugin.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (directory / "ui" / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    plugin_runtime.invalidate_ownership_cache()

    response = _enable(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "enabled"
    assert body["mounted"] is False
    assert body["names"] == []


def test_the_signature_gate_answers_before_the_mount(client, lane, monkeypatch):
    """A refused bundle is not published on the way to the refusal."""
    from core import plugin_signing

    _write_bundle(lane["root"])
    monkeypatch.setattr(
        plugin_signing,
        "verify_enable",
        lambda _plugin: (False, "signature_record_missing"),
    )

    response = _enable(client)

    assert response.status_code == 409
    assert _detail(response)["code"] == "signature_denied"
    assert _SERVED not in _served()
    assert _mount_record(lane) == {}


def test_a_disable_takes_the_tools_and_the_surface_back(client, lane):
    """GIVEN an enabled, mounted bundle whose surface holds a live credential
    WHEN it is switched off
    THEN the name leaves the gate and the offer, the record is gone, and the surface a
    held credential points at answers 404."""
    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200
    minted = client.post(f"/api/plugins/{_PLUGIN}/surface-token", json={})
    assert minted.status_code == 200, minted.text
    nonce = minted.json()["surface"]

    response = _disable(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "disabled"
    assert body["mounted"] is False
    assert body["names"] == []
    assert _SERVED not in _served()
    assert _SERVED not in _offered()
    assert plugin_runtime.tool_gate(_SERVED).visible is False
    assert _mount_record(lane) == {}
    document = client.get(f"/api/plugins/ui/{_PLUGIN}/{nonce}/")
    assert document.status_code == 404, document.text
    assert document.json()["error"]["reason_code"] == "plugin_ui_unavailable"


def test_a_disable_whose_cleanup_cannot_be_written_answers_the_write_that_failed(
    client, lane, monkeypatch
):
    """The switch is off either way; the record is what did not move.

    GIVEN an enabled, mounted bundle
    WHEN the state file refuses the removal of the mount record
    THEN the switch stays off, the tools stay withheld, and the answer is the coded write
    failure with the state it did commit — never a 200 claiming a cleanup that failed."""
    from core.plugin_lifecycle_store import LifecyclePersistence

    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200
    written = LifecyclePersistence._persist

    def _refuse_removal(self, *, keep=None):
        if _PLUGIN not in (self._data.get("mounts") or {}):
            raise LifecycleError("state_write_failed", 500, "injected: no write")
        return written(self, keep=keep)

    monkeypatch.setattr(LifecyclePersistence, "_persist", _refuse_removal)

    response = _disable(client)

    assert response.status_code == 500, response.text
    detail = _detail(response)
    assert detail["code"] == "state_write_failed"
    assert detail["current"]["enabled"] is False
    assert _SERVED not in _offered()
    assert plugin_runtime.tool_gate(_SERVED).visible is False


def test_a_disable_is_idempotent(client, lane):
    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200

    first = _disable(client)
    second = _disable(client)

    assert first.status_code == second.status_code == 200
    assert second.json()["mounted"] is False
    assert _SERVED not in _served()
    assert len(_switch_rows(lane, "disable")) == 1


def test_the_legacy_enable_shim_mounts_and_unmounts(client, lane):
    """The one-release shim answers its own payload and runs the same two movements."""
    _write_bundle(lane["root"])

    enabled = client.post(f"/api/plugins/{_PLUGIN}/enable", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json() == {"id": _PLUGIN, "enabled": True, "saved": True}
    assert _SERVED in _served()
    assert _SERVED in _offered()
    assert _mount_record(lane)["names"] == [_SERVED]

    disabled = client.post(f"/api/plugins/{_PLUGIN}/enable", json={"enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json() == {"id": _PLUGIN, "enabled": False, "saved": True}
    assert _SERVED not in _served()
    assert _SERVED not in _offered()
    assert _mount_record(lane) == {}


def test_the_surface_token_on_a_switched_off_bundle_names_the_switch(client, lane):
    """A bare 401 is the wrong answer: the surface exists and the switch is the reason."""
    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200
    assert _disable(client).status_code == 200

    response = client.post(f"/api/plugins/{_PLUGIN}/surface-token", json={})
    again = client.post(f"/api/plugins/{_PLUGIN}/surface-token", json={})

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["reason_code"] == "plugin_ui_unavailable"
    assert "switched off" in error["message"]
    assert "switch it on" in error["next"]
    assert again.status_code == 409
    assert again.json()["error"]["reason_code"] == error["reason_code"]


def test_enable_disable_enable_ends_mounted(client, lane):
    """GIVEN a bundle that went on, off and on again
    WHEN the last enable settled
    THEN exactly one state is left: enabled, mounted, one served name."""
    _write_bundle(lane["root"])
    assert _enable(client).status_code == 200
    assert _disable(client).status_code == 200

    response = _enable(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "enabled"
    assert body["mounted"] is True
    assert body["names"] == [_SERVED]
    assert _served().count(_SERVED) == 1
    assert _mount_record(lane)["names"] == [_SERVED]
    assert plugin_runtime.tool_gate(_SERVED).visible is True
    # The surface is open again on the same switch: the mint the disable refused works.
    minted = client.post(f"/api/plugins/{_PLUGIN}/surface-token", json={})
    assert minted.status_code == 200, minted.text
