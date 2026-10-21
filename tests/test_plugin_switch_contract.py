"""SW-01..16 / OWN-02 — the switch contract at the service boundary.

One request commits; stale version and ETag conflict; a cross-origin mutation
without the XHR marker is refused; double clicks serialize; a pending
activation can be cancelled; an idempotency key has one effect; startup
reconciles; a write is atomic; an in-flight call is cancelled.
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

from core.plugin_lifecycle import (
    STATE_FILENAME,
    LifecycleError,
    PluginLifecycle,
    PluginState,
)


def _lifecycle(tmp_path, activator=None, deactivator=None, audit=None):
    return PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.0.0"},
        activator=activator,
        deactivator=deactivator,
        audit_sink=audit.append if audit is not None else (lambda entry: None),
    )


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


def test_one_click(client) -> None:
    response = client.put(
        "/api/plugins/web-research/enabled", json={"enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "disabled"
    view = client.get("/api/plugins").json()
    assert next(p for p in view["public"] if p["name"] == "web-research")["enabled"] is False


def test_stale_version(client) -> None:
    response = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": False, "expected_version": "9.9.9"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["detail"]["code"] == "stale_state"

    stale_etag = client.put(
        "/api/plugins/web-research/enabled", json={"enabled": False}
    ).json()["etag"]
    assert (
        client.put(
            "/api/plugins/web-research/enabled", json={"enabled": True}
        ).status_code
        == 200
    )
    etag_conflict = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": True},
        headers={"If-Match": stale_etag},
    )
    assert etag_conflict.status_code == 409
    assert etag_conflict.json()["error"]["detail"]["code"] == "stale_state"


def test_dependency_blocked(tmp_path) -> None:
    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.0.0", "base-pack": "1.0.0"},
        dependencies={"acme-research": ("base-pack",)},
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)
    lifecycle.set_enabled("base-pack", False)
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", True)
    assert err.value.code == "dependency_blocked"


def test_toggle_authorization(device) -> None:
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as bare:
        refused = bare.put(
            "/api/plugins/web-research/enabled", json={"enabled": False}
        )
        assert refused.status_code == 403
        assert refused.json()["error"]["detail"]["code"] == "unauthorized"
        assert bare.get("/api/plugins").status_code == 200


def test_rapid_clicks_serialize(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def slow(name: str) -> None:
        calls.append(name)
        started.set()
        release.wait(timeout=5)

    lifecycle = _lifecycle(tmp_path, activator=slow)
    lifecycle.set_enabled("acme-research", False)
    result: dict[str, PluginState] = {}

    thread = threading.Thread(
        target=lambda: result.update(
            snap=lifecycle.set_enabled("acme-research", True)
        )
    )
    thread.start()
    assert started.wait(timeout=5)
    pending = lifecycle.set_enabled("acme-research", True)
    assert pending.state is PluginState.ENABLING
    release.set()
    thread.join(timeout=5)
    assert calls == ["acme-research"]
    assert lifecycle.snapshot("acme-research").state is PluginState.ENABLED


def test_cancel_pending(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    torn_down: list[str] = []

    def slow(name: str) -> None:
        started.set()
        release.wait(timeout=5)

    lifecycle = _lifecycle(
        tmp_path, activator=slow, deactivator=lambda name: torn_down.append(name)
    )
    lifecycle.set_enabled("acme-research", False)
    torn_down.clear()
    thread = threading.Thread(
        target=lambda: lifecycle.set_enabled("acme-research", True)
    )
    thread.start()
    assert started.wait(timeout=5)
    assert lifecycle.cancel("acme-research").state is PluginState.DISABLED
    release.set()
    thread.join(timeout=5)
    assert torn_down == ["acme-research"]
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED


def test_idempotency(device) -> None:
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        first = client.put(
            "/api/plugins/web-research/enabled",
            json={"enabled": False},
            headers={"Idempotency-Key": "switch-1"},
        )
        second = client.put(
            "/api/plugins/web-research/enabled",
            json={"enabled": False},
            headers={"Idempotency-Key": "switch-1"},
        )
    assert first.status_code == second.status_code == 200
    assert first.json()["etag"] == second.json()["etag"]
    lines = device[1].read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    assert len([e for e in entries if e.get("kind") == "plugin_lifecycle"]) == 1


def test_startup_reconciliation(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "schema": 1,
                "pause_all": False,
                "plugins": {
                    "acme-research": {
                        "user": {
                            "committed": "disabled",
                            "version": "1.0.0",
                            "pending": {"state": "enabling", "requested_enabled": True},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    audit: list[dict] = []
    lifecycle = PluginLifecycle(
        state,
        versions={"acme-research": "1.0.0"},
        audit_sink=audit.append,
    )
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED
    assert audit[-1]["action"] == "reconcile"


def test_atomic_write(tmp_path, monkeypatch) -> None:
    lifecycle = _lifecycle(tmp_path)
    lifecycle.set_enabled("acme-research", False)
    before = (tmp_path / "state.json").read_text(encoding="utf-8")
    from core import plugin_lifecycle_store as store

    monkeypatch.setattr(
        store.os,
        "replace",
        lambda src, dst: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", True)
    assert err.value.code == "state_write_failed"
    assert (tmp_path / "state.json").read_text(encoding="utf-8") == before


@pytest.mark.asyncio
async def test_inflight_cancelled() -> None:
    from core.plugin_activity import begin_call, cancel_calls, end_call

    async def call() -> None:
        guard = begin_call("acme-research")
        try:
            await asyncio.sleep(5)
        finally:
            end_call(guard)

    task = asyncio.create_task(call())
    await asyncio.sleep(0.05)
    assert cancel_calls("acme-research") == 1
    with pytest.raises(asyncio.CancelledError):
        await task



@pytest.mark.asyncio
async def test_a_gate_error_denies_execution(device, monkeypatch) -> None:
    import core.tools.registry as registry
    from core import plugin_runtime

    ran: list[str] = []

    async def probe() -> str:
        ran.append("executed")
        return "EXECUTED"

    monkeypatch.setitem(registry.TOOL_MAP, "__probe__", probe)

    def unavailable(name: str, path=None):
        raise RuntimeError("gate unavailable")

    monkeypatch.setattr(plugin_runtime, "tool_gate", unavailable)

    result = await registry.execute_tool("__probe__", {})

    assert "EXECUTED" not in result
    assert ran == []
    assert "refused" in result.lower()
    lines = [json.loads(line) for line in device[1].read_text(encoding="utf-8").splitlines()]
    assert any(
        line["kind"] == "plugin_gate"
        and line["decision"] == "gate_unavailable"
        and line["status"] == "denied"
        for line in lines
    )


@pytest.mark.asyncio
async def test_a_guard_error_denies_execution(device, monkeypatch) -> None:
    import core.tools.registry as registry
    from core import plugin_activity, plugin_runtime

    ran: list[str] = []

    async def probe() -> str:
        ran.append("executed")
        return "EXECUTED"

    monkeypatch.setitem(registry.TOOL_MAP, "__probe__", probe)
    monkeypatch.setattr(
        plugin_runtime,
        "tool_gate",
        lambda name, path=None: plugin_runtime.Gate(True, "acme-research"),
    )

    def unavailable(plugin: str):
        raise RuntimeError("guard unavailable")

    monkeypatch.setattr(plugin_activity, "begin_call", unavailable)

    result = await registry.execute_tool("__probe__", {})

    assert "EXECUTED" not in result
    assert ran == []
    assert "refused" in result.lower()
    lines = [json.loads(line) for line in device[1].read_text(encoding="utf-8").splitlines()]
    assert any(
        line["kind"] == "plugin_gate"
        and line["decision"] == "guard_unavailable"
        and line["status"] == "denied"
        for line in lines
    )


MALFORMED_STATES = [
    {"schema": 1, "plugins": "not-a-dict"},
    {"schema": 1, "plugins": None},
    {"schema": 1, "plugins": {"acme-research": "not-a-dict"}},
    {"schema": 1, "plugins": {"acme-research": {"user": "not-a-dict"}}},
    {"schema": 1, "plugins": {"acme-research": {"machine": {"committed": "enabled"}}}},
    {"schema": 1, "plugins": {"acme-research": {"user": {"committed": "sometimes"}}}},
    {"schema": 1, "plugins": {}, "pause_all": "yes"},
    {"schema": 2, "plugins": {}},
    {"schema": 1, "plugins": {}, "idempotency": []},
    {"schema": 1, "plugins": {"acme-research": {"user": {"pending": "soon"}}}},
]


@pytest.mark.parametrize("payload", MALFORMED_STATES)
def test_malformed_state_reads_off_and_unproven(tmp_path, payload) -> None:
    activated: list[str] = []
    state = tmp_path / "state.json"
    state.write_text(json.dumps(payload), encoding="utf-8")
    lifecycle = PluginLifecycle(
        state,
        versions={"acme-research": "1.0.0"},
        activator=activated.append,
        audit_sink=lambda entry: None,
    )

    snapshot = lifecycle.snapshot("acme-research")

    assert snapshot.enabled is False
    assert snapshot.state in (PluginState.DISABLED, PluginState.PAUSED)
    assert lifecycle.unproven is True
    assert activated == []


def test_a_malformed_pause_all_stays_paused_instead_of_unpausing(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"schema": 1, "plugins": {}, "pause_all": "yes"}), encoding="utf-8"
    )
    lifecycle = PluginLifecycle(
        state, versions={"acme-research": "1.0.0"}, audit_sink=lambda entry: None
    )

    assert lifecycle.pause_all() is True
    assert lifecycle.snapshot("acme-research").state is PluginState.PAUSED


def test_a_valid_empty_state_keeps_the_current_behavior_for_one_release(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema": 1, "plugins": {}}), encoding="utf-8")
    lifecycle = PluginLifecycle(
        state, versions={"acme-research": "1.0.0"}, audit_sink=lambda entry: None
    )

    assert lifecycle.unproven is False
    assert lifecycle.snapshot("acme-research").enabled is True


def test_an_unknown_committed_value_is_never_enabled(tmp_path) -> None:
    lifecycle = _lifecycle(tmp_path)
    lifecycle.set_enabled("acme-research", True)

    lifecycle._data["plugins"]["acme-research"]["user"]["committed"] = "surprise"

    assert lifecycle.snapshot("acme-research").enabled is False
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED


def test_cancel_then_reenable_keeps_the_new_activation(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    active: list[str] = []
    calls: list[str] = []
    flights = {"count": 0}

    def activator(name: str) -> None:
        flights["count"] += 1
        if flights["count"] == 1:
            calls.append("first-start")
            active.append("first")
            started.set()
            assert release.wait(timeout=5)
            calls.append("first-end")
        else:
            calls.append("second-start")
            active.append("second")

    def deactivator(name: str) -> None:
        calls.append("deactivate")
        if active:
            active.pop()

    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.0.0"},
        activator=activator,
        deactivator=deactivator,
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)
    calls.clear()

    first = threading.Thread(target=lambda: lifecycle.set_enabled("acme-research", True))
    first.start()
    assert started.wait(timeout=5)
    lifecycle.cancel("acme-research")

    second_result: dict[str, object] = {}
    second = threading.Thread(
        target=lambda: second_result.update(
            snapshot=lifecycle.set_enabled("acme-research", True)
        )
    )
    second.start()
    second.join(timeout=0.2)
    assert second.is_alive(), "a re-enable must wait for the canceled flight to unwind"

    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert second_result["snapshot"].state is PluginState.ENABLED
    assert lifecycle.snapshot("acme-research").state is PluginState.ENABLED
    assert active == ["second"]
    assert calls == ["first-start", "first-end", "deactivate", "second-start"]


def test_cancel_then_activation_failure_rolls_back_the_resource(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    active: list[str] = []
    calls: list[str] = []

    def activator(name: str) -> None:
        active.append("resource")
        calls.append("activate")
        started.set()
        assert release.wait(timeout=5)
        raise RuntimeError("boom after cancel")

    def deactivator(name: str) -> None:
        calls.append("deactivate")
        if active:
            active.pop()

    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.0.0"},
        activator=activator,
        deactivator=deactivator,
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)
    calls.clear()

    failure: dict[str, object] = {}

    def enable() -> None:
        try:
            lifecycle.set_enabled("acme-research", True)
        except LifecycleError as exc:
            failure["error"] = exc

    thread = threading.Thread(target=enable)
    thread.start()
    assert started.wait(timeout=5)
    lifecycle.cancel("acme-research")
    release.set()
    thread.join(timeout=5)

    assert active == []
    assert calls == ["activate", "deactivate"]
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED
    assert failure["error"].code == "activation_failed"


def test_cancel_then_a_successful_activation_rolls_back_once(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    active: list[str] = []

    def activator(name: str) -> None:
        active.append("resource")
        started.set()
        assert release.wait(timeout=5)

    def deactivator(name: str) -> None:
        if active:
            active.pop()

    audit: list[dict] = []
    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.0.0"},
        activator=activator,
        deactivator=deactivator,
        audit_sink=audit.append,
    )
    lifecycle.set_enabled("acme-research", False)

    thread = threading.Thread(target=lambda: lifecycle.set_enabled("acme-research", True))
    thread.start()
    assert started.wait(timeout=5)
    lifecycle.cancel("acme-research")
    release.set()
    thread.join(timeout=5)

    assert active == []
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED
    assert [entry["action"] for entry in audit].count("rollback") == 1


def test_a_disable_while_an_enable_is_pending_does_not_start_a_second_flight(
    tmp_path,
) -> None:
    started = threading.Event()
    release = threading.Event()
    active: list[str] = []

    def activator(name: str) -> None:
        active.append("resource")
        started.set()
        assert release.wait(timeout=5)

    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.0.0"},
        activator=activator,
        deactivator=lambda name: active.pop() if active else None,
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)

    thread = threading.Thread(target=lambda: lifecycle.set_enabled("acme-research", True))
    thread.start()
    assert started.wait(timeout=5)

    during = lifecycle.set_enabled("acme-research", False)
    assert during.state is PluginState.ENABLING

    release.set()
    thread.join(timeout=5)
    assert lifecycle.snapshot("acme-research").state is PluginState.ENABLED
    assert active == ["resource"]
