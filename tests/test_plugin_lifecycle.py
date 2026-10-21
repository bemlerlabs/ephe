"""P1 — the plugin lifecycle state machine.

The switch is server-confirmed: the committed state lives in the state file, a
repeat of the same request has no second effect, a stale expected version is
rejected, and a failed write never reports success. These tests pin the core
service; the HTTP route and the UI switch are wired in later slices.
"""

from __future__ import annotations

import json
import stat
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_lifecycle import (
    LifecycleError,
    PluginLifecycle,
    PluginSnapshot,
    PluginState,
    Scope,
)


@pytest.fixture()
def lifecycle(tmp_path, monkeypatch):
    state_file = tmp_path / "plugin-state.json"
    audit: list[dict] = []
    calls: list[str] = []

    def default_activator(name: str) -> None:
        calls.append(name)

    def factory(activator=None, versions=None, audit_sink=None):
        return PluginLifecycle(
            state_file,
            versions=versions or {"acme-research": "1.4.0", "web-research": "2.0.0"},
            activator=activator or default_activator,
            audit_sink=audit_sink if audit_sink is not None else audit.append,
        )

    factory.path = state_file
    factory.audit = audit
    factory.calls = calls
    return factory


def test_disable_then_enable_commits_after_activation(lifecycle) -> None:
    lc = lifecycle()
    off = lc.set_enabled("acme-research", False)
    assert off.state is PluginState.DISABLED
    assert off.enabled is False

    on = lc.set_enabled("acme-research", True)
    assert on.state is PluginState.ENABLED
    assert on.enabled is True
    assert lifecycle.calls == ["acme-research"]
    assert [entry["status"] for entry in lifecycle.audit] == ["committed", "committed"]
    assert lifecycle.audit[1]["previous_state"] == "disabled"
    assert lifecycle.audit[1]["requested_state"] == "enabled"


def test_a_missing_state_keeps_the_current_effective_behavior(lifecycle) -> None:
    snap = lifecycle().snapshot("acme-research")
    assert snap.state is PluginState.ENABLED
    assert snap.enabled is True
    assert snap.version == "1.4.0"
    assert not lifecycle.path.exists()


def test_repeating_the_same_state_has_no_second_effect(lifecycle) -> None:
    lc = lifecycle()
    first = lc.set_enabled("acme-research", False)
    second = lc.set_enabled("acme-research", False)
    assert first == second
    assert len(lifecycle.audit) == 1


def test_an_idempotency_key_deduplicates_a_retry(lifecycle) -> None:
    lc = lifecycle()
    first = lc.set_enabled("acme-research", False, idempotency_key="toggle-1")
    second = lc.set_enabled("acme-research", False, idempotency_key="toggle-1")
    assert first == second
    assert len(lifecycle.audit) == 1


def test_an_idempotency_key_cannot_be_reused_for_a_different_request(lifecycle) -> None:
    lc = lifecycle()
    lc.set_enabled("acme-research", False, idempotency_key="toggle-1")
    with pytest.raises(LifecycleError) as err:
        lc.set_enabled("acme-research", True, idempotency_key="toggle-1")
    assert err.value.status == 409
    assert err.value.code == "idempotency_conflict"


def test_a_stale_expected_version_is_rejected(lifecycle) -> None:
    lc = lifecycle(versions={"acme-research": "2.0.0"})
    with pytest.raises(LifecycleError) as err:
        lc.set_enabled("acme-research", False, expected_version="1.4.0")
    assert err.value.status == 409
    assert err.value.code == "stale_state"
    assert err.value.snapshot.version == "2.0.0"
    assert err.value.snapshot.state is PluginState.ENABLED
    assert lifecycle.audit == []
    assert lifecycle.calls == []


def test_an_unknown_plugin_is_refused(lifecycle) -> None:
    with pytest.raises(LifecycleError) as err:
        lifecycle().set_enabled("not-installed", True)
    assert err.value.status == 404
    assert err.value.code == "unknown_plugin"


def test_an_unknown_scope_is_refused(lifecycle) -> None:
    with pytest.raises(LifecycleError) as err:
        lifecycle().set_enabled("acme-research", False, scope="machine")
    assert err.value.status == 400
    assert err.value.code == "invalid_request"


def test_a_failed_activation_reverts_to_off_and_is_audited(lifecycle) -> None:
    def explode(name: str) -> None:
        raise RuntimeError("registry vanished")

    lc = lifecycle(activator=explode)
    lc.set_enabled("acme-research", False)
    with pytest.raises(LifecycleError) as err:
        lc.set_enabled("acme-research", True)
    assert err.value.status == 500
    assert err.value.code == "activation_failed"
    assert err.value.snapshot.state is PluginState.FAILED
    assert err.value.snapshot.enabled is False
    assert lifecycle.audit[-1]["status"] == "failed"
    assert "registry vanished" in lifecycle.audit[-1]["reason"]
    assert lc.snapshot("acme-research").state is PluginState.FAILED


def test_a_second_toggle_while_pending_is_ignored(lifecycle) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def slow(name: str) -> None:
        calls.append(name)
        started.set()
        release.wait(timeout=5)

    lc = lifecycle(activator=slow)
    lc.set_enabled("acme-research", False)
    result: dict[str, PluginSnapshot] = {}

    def enable() -> None:
        result["snap"] = lc.set_enabled("acme-research", True)

    thread = threading.Thread(target=enable)
    thread.start()
    assert started.wait(timeout=5)
    pending = lc.set_enabled("acme-research", True)
    assert pending.state is PluginState.ENABLING
    release.set()
    thread.join(timeout=5)
    assert len(calls) == 1
    assert result["snap"].state is PluginState.ENABLED
    assert lc.snapshot("acme-research").state is PluginState.ENABLED


def test_cancelling_a_pending_activation_leaves_the_plugin_off(lifecycle) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow(name: str) -> None:
        started.set()
        release.wait(timeout=5)

    lc = lifecycle(activator=slow)
    lc.set_enabled("acme-research", False)
    thread = threading.Thread(target=lambda: lc.set_enabled("acme-research", True))
    thread.start()
    assert started.wait(timeout=5)
    cancelled = lc.cancel("acme-research")
    assert cancelled.state is PluginState.DISABLED
    release.set()
    thread.join(timeout=5)
    assert lc.snapshot("acme-research").state is PluginState.DISABLED
    actions = [entry["action"] for entry in lifecycle.audit]
    assert "cancel" in actions
    assert lifecycle.audit[-1]["action"] == "rollback"
    assert lifecycle.audit[-1]["status"] == "committed"


def test_workspace_state_overrides_user_state(lifecycle) -> None:
    lc = lifecycle()
    lc.set_enabled("acme-research", False, scope=Scope.USER)
    effective_off = lc.effective("acme-research")
    assert effective_off.enabled is False
    assert effective_off.scope == "user"

    lc.set_enabled("acme-research", True, scope=Scope.WORKSPACE)
    effective_on = lc.effective("acme-research")
    assert effective_on.enabled is True
    assert effective_on.scope == "workspace"
    assert lc.snapshot("acme-research", Scope.USER).enabled is False


def test_pause_all_preserves_every_per_plugin_state(lifecycle) -> None:
    lc = lifecycle()
    lc.set_enabled("acme-research", False)
    lc.set_enabled("web-research", True)
    lc.set_pause_all(True)
    paused = lc.effective("acme-research")
    assert paused.state is PluginState.PAUSED
    lc.set_pause_all(False)
    assert lc.effective("acme-research").state is PluginState.DISABLED
    assert lc.effective("web-research").state is PluginState.ENABLED


def test_a_write_keeps_other_plugins_and_the_pause_state(lifecycle) -> None:
    lc = lifecycle()
    lc.set_pause_all(True)
    lc.set_enabled("acme-research", False)
    lc.set_enabled("web-research", False)
    raw = json.loads(lifecycle.path.read_text(encoding="utf-8"))
    assert raw["pause_all"] is True
    assert raw["plugins"]["acme-research"]["user"]["committed"] == "disabled"
    assert raw["plugins"]["web-research"]["user"]["committed"] == "disabled"


def test_a_failed_write_keeps_the_previous_file_and_reports_an_error(
    lifecycle, monkeypatch
) -> None:
    lc = lifecycle()
    lc.set_enabled("acme-research", False)
    before = lifecycle.path.read_text(encoding="utf-8")

    from core import plugin_lifecycle_store as module

    def refuse(src, dst) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "replace", refuse)
    with pytest.raises(LifecycleError) as err:
        lc.set_enabled("acme-research", True)
    assert err.value.status == 500
    assert err.value.code == "state_write_failed"
    assert lifecycle.path.read_text(encoding="utf-8") == before
    monkeypatch.undo()
    assert lc.snapshot("acme-research").state is PluginState.DISABLED


def test_startup_reconciliation_drops_a_pending_intent(lifecycle) -> None:
    payload = {
        "schema": 1,
        "pause_all": False,
        "plugins": {
            "acme-research": {
                "user": {
                    "committed": "disabled",
                    "version": "1.4.0",
                    "pending": {"state": "enabling", "requested_state": "enabled"},
                }
            }
        },
    }
    lifecycle.path.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.path.write_text(json.dumps(payload), encoding="utf-8")
    lc = lifecycle()
    assert lc.snapshot("acme-research").state is PluginState.DISABLED
    assert lifecycle.audit[-1]["action"] == "reconcile"
    assert lifecycle.audit[-1]["status"] == "committed"


def test_a_stale_etag_is_rejected(lifecycle) -> None:
    lc = lifecycle()
    before = lc.snapshot("acme-research").etag
    lc.set_enabled("acme-research", False)
    with pytest.raises(LifecycleError) as err:
        lc.set_enabled("acme-research", True, expected_etag=before)
    assert err.value.status == 409
    assert err.value.code == "stale_state"
    assert err.value.snapshot.enabled is False


def _event(queue, name: str) -> dict:
    while True:
        event = queue.get(timeout=1)
        if event["event"] == name:
            return event


def test_a_committed_toggle_is_published(lifecycle) -> None:
    from core.plugin_lifecycle import subscribe, unsubscribe

    queue = subscribe(lifecycle.path)
    try:
        lifecycle().set_enabled("acme-research", False)
        pending = _event(queue, "plugin.pending")
        assert pending["data"]["phase"] == "disabling"
        event = _event(queue, "plugin.state")
        assert event["data"]["name"] == "acme-research"
        assert event["data"]["state"] == "disabled"
        assert event["data"]["enabled"] is False
        assert isinstance(event["id"], int)
    finally:
        unsubscribe(queue)


def test_pause_all_is_published(lifecycle) -> None:
    from core.plugin_lifecycle import subscribe, unsubscribe

    queue = subscribe(lifecycle.path)
    try:
        lifecycle().set_pause_all(True)
        event = queue.get(timeout=1)
        assert event["event"] == "plugin.paused"
        assert event["data"]["pause_all"] is True
    finally:
        unsubscribe(queue)


def test_a_failed_activation_is_published(lifecycle) -> None:
    from core.plugin_lifecycle import subscribe, unsubscribe

    def explode(name: str) -> None:
        raise RuntimeError("activation failed")

    lc = lifecycle(activator=explode)
    lc.set_enabled("acme-research", False)
    queue = subscribe(lifecycle.path)
    try:
        with pytest.raises(LifecycleError):
            lc.set_enabled("acme-research", True)
        event = _event(queue, "plugin.failed")
        assert event["data"]["name"] == "acme-research"
        assert event["data"]["state"] == "failed"
    finally:
        unsubscribe(queue)


def _deps_lifecycle(tmp_path, dependencies):
    return PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.0.0", "base-pack": "1.0.0"},
        dependencies=dependencies,
        audit_sink=lambda entry: None,
    )


def test_a_disabled_dependency_blocks_enable(tmp_path) -> None:
    lifecycle = _deps_lifecycle(tmp_path, {"acme-research": ("base-pack",)})
    lifecycle.set_enabled("acme-research", False)
    lifecycle.set_enabled("base-pack", False)
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", True)
    assert err.value.status == 409
    assert err.value.code == "dependency_blocked"
    assert "base-pack" in err.value.detail

    lifecycle.set_enabled("base-pack", True)
    assert lifecycle.set_enabled("acme-research", True).enabled is True


def test_a_missing_dependency_blocks_enable(tmp_path) -> None:
    lifecycle = _deps_lifecycle(tmp_path, {"acme-research": ("absent-pack",)})
    lifecycle.set_enabled("acme-research", False)
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", True)
    assert err.value.code == "dependency_blocked"
    assert "absent-pack" in err.value.detail


def test_disabling_a_plugin_with_enabled_dependents_is_blocked(tmp_path) -> None:
    lifecycle = _deps_lifecycle(tmp_path, {"acme-research": ("base-pack",)})
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("base-pack", False)
    assert err.value.code == "dependents_enabled"
    assert "acme-research" in err.value.detail

    lifecycle.set_enabled("acme-research", False)
    assert lifecycle.set_enabled("base-pack", False).enabled is False


def test_a_dependency_cycle_fails_closed(tmp_path) -> None:
    lifecycle = _deps_lifecycle(
        tmp_path,
        {"acme-research": ("base-pack",), "base-pack": ("acme-research",)},
    )
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("base-pack", False)
    assert err.value.code == "dependents_enabled"


def test_a_normal_disable_tears_down_exactly_once(tmp_path) -> None:
    calls: list[str] = []
    audit: list[dict] = []
    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.0.0"},
        deactivator=calls.append,
        audit_sink=audit.append,
    )
    lifecycle.set_enabled("acme-research", False)
    lifecycle.set_enabled("acme-research", False)
    assert calls == ["acme-research"]
    assert audit[-1]["action"] == "disable"
    assert audit[-1]["status"] == "committed"


def test_a_teardown_failure_keeps_the_plugin_enabled_and_audits(tmp_path) -> None:
    audit: list[dict] = []
    fail = {"now": True}

    def deactivator(name: str) -> None:
        if fail["now"]:
            raise RuntimeError("disposer failed")

    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.0.0"},
        deactivator=deactivator,
        audit_sink=audit.append,
    )
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", False)
    assert err.value.status == 500
    assert err.value.code == "deactivation_failed"
    assert err.value.snapshot.state is PluginState.ENABLED
    assert lifecycle.snapshot("acme-research").state is PluginState.ENABLED
    assert audit[-1]["action"] == "disable"
    assert audit[-1]["status"] == "failed"
    assert "disposer failed" in audit[-1]["reason"]

    fail["now"] = False
    assert lifecycle.set_enabled("acme-research", False).state is PluginState.DISABLED


def test_a_failed_activation_rolls_back_once(tmp_path) -> None:
    calls: list[str] = []
    fail = {"now": True}

    def activator(name: str) -> None:
        calls.append("activate")
        if fail["now"]:
            raise RuntimeError("activation failed")

    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.0.0"},
        activator=activator,
        deactivator=lambda name: calls.append("deactivate"),
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)
    calls.clear()

    with pytest.raises(LifecycleError):
        lifecycle.set_enabled("acme-research", True)
    assert calls == ["activate", "deactivate"]
    assert lifecycle.snapshot("acme-research").state is PluginState.FAILED


def test_cancelling_an_activation_rolls_back_once(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def slow(name: str) -> None:
        started.set()
        release.wait(timeout=5)

    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.0.0"},
        activator=slow,
        deactivator=lambda name: calls.append("deactivate"),
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)
    calls.clear()

    thread = threading.Thread(
        target=lambda: lifecycle.set_enabled("acme-research", True)
    )
    thread.start()
    assert started.wait(timeout=5)
    lifecycle.cancel("acme-research")
    release.set()
    thread.join(timeout=5)
    assert calls == ["deactivate"]
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED


def test_cancel_is_refused_while_a_disable_is_tearing_down(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow(name: str) -> None:
        started.set()
        release.wait(timeout=5)

    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.0.0"},
        deactivator=slow,
        audit_sink=lambda entry: None,
    )
    thread = threading.Thread(
        target=lambda: lifecycle.set_enabled("acme-research", False)
    )
    thread.start()
    assert started.wait(timeout=5)
    with pytest.raises(LifecycleError) as err:
        lifecycle.cancel("acme-research")
    assert err.value.status == 409
    assert err.value.code == "not_cancellable"
    release.set()
    thread.join(timeout=5)
    assert lifecycle.snapshot("acme-research").state is PluginState.DISABLED


def test_the_state_file_is_owner_only(lifecycle) -> None:
    lc = lifecycle()
    lc.set_enabled("acme-research", False)
    assert stat.S_IMODE(lifecycle.path.stat().st_mode) == 0o600


def test_the_etag_tracks_the_committed_state(lifecycle) -> None:
    lc = lifecycle()
    on = lc.snapshot("acme-research")
    lc.set_enabled("acme-research", False)
    off = lc.snapshot("acme-research")
    assert on.etag == '"state-1.4.0-user-true"'
    assert off.etag == '"state-1.4.0-user-false"'


def test_a_transient_disposer_failure_is_retried_by_the_next_disable(tmp_path) -> None:
    from core import plugin_activity

    plugin_activity.clear()
    closed: list[str] = []
    fail = {"now": True}

    def disposer() -> None:
        if fail["now"]:
            fail["now"] = False
            raise RuntimeError("transient")
        closed.append("closed")

    plugin_activity.register_disposer("acme-research", disposer)
    audit: list[dict] = []
    lc = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"acme-research": "1.4.0"},
        deactivator=plugin_activity.teardown_plugin,
        audit_sink=audit.append,
    )
    try:
        with pytest.raises(LifecycleError) as err:
            lc.set_enabled("acme-research", False)
        assert err.value.code == "deactivation_failed"
        assert closed == []
        assert lc.snapshot("acme-research").state is PluginState.ENABLED
        assert audit[-1]["status"] == "failed"

        committed = lc.set_enabled("acme-research", False)
        assert committed.state is PluginState.DISABLED
        assert closed == ["closed"]
    finally:
        plugin_activity.clear()
