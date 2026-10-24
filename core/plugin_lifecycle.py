"""Server-confirmed plugin lifecycle (P1).

One state machine for enable and disable: a request stages a pending intent,
runs the activation hook, commits a versioned state and writes exactly one audit
entry. A stale expected version and a reused idempotency key fail closed. State
writes go through a temp file, fsync and replace, so a crash leaves the old or
the new file and never a truncated one.

The state file is separate from the legacy ``plugins.json``; migration imports
the legacy map once. The HTTP route, SSE and the UI switch map
``LifecycleError`` onto the coded HTTP statuses.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from core.plugin_lifecycle_events import subscribe, unsubscribe
from core.plugin_lifecycle_reads import LifecycleReads
from core.plugin_lifecycle_store import LifecyclePersistence
from core.plugin_lifecycle_transitions import LifecycleTransitions
from core.plugin_lifecycle_types import (
    DEFAULT_SCOPE,
    SCHEMA_VERSION,
    SCOPES,
    STATE_FILENAME,
    LifecycleError,
    PluginSnapshot,
    PluginState,
    Scope,
    _default_audit,
    _Pending,
)

__all__ = [
    "DEFAULT_SCOPE",
    "SCOPES",
    "STATE_FILENAME",
    "LifecycleError",
    "PluginLifecycle",
    "PluginSnapshot",
    "PluginState",
    "subscribe",
    "unsubscribe",
]


logger = logging.getLogger(__name__)


def _audit_refusal(plugin: str, code: str, detail: str) -> None:
    """A refused switch is an event, not a silence: the forensic record needs it."""
    from core.audit_log import audit_event

    audit_event(
        "plugin_refusal", tool=plugin, decision=code, status="refused", detail=detail,
    )


class PluginLifecycle(LifecyclePersistence, LifecycleReads, LifecycleTransitions):
    def __init__(
        self,
        state_path: Path | None,
        *,
        versions: Mapping[str, str],
        dependencies: Mapping[str, Iterable[str]] | None = None,
        activator: Callable[[str], None] | None = None,
        deactivator: Callable[[str], None] | None = None,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._path = Path(state_path) if state_path is not None else None
        self._versions = {str(name): str(version) for name, version in versions.items()}
        self._dependencies = {
            str(name): tuple(str(dep) for dep in deps)
            for name, deps in (dependencies or {}).items()
        }
        self._activator = activator or (lambda name: None)
        self._deactivator = deactivator or (lambda name: None)
        self._audit = audit_sink or _default_audit
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._pending: dict[tuple[str, str], _Pending] = {}
        self._flight_locks: dict[str, threading.Lock] = {}
        self._token = 0
        self._unproven = False
        self._seen_signature = None
        self._loaded_data: dict[str, Any] = {}
        self._data: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "pause_all": False,
            "legacy_imported": False,
            "notices": [],
            "plugins": {},
            "idempotency": {},
        }
        self._load()

    # Public reads

    def snapshot(self, name: str, scope: str | Scope = DEFAULT_SCOPE) -> PluginSnapshot:
        with self._lock:
            return self._snapshot_locked(self._known(name), self._scope(scope))

    def has_committed_state(self, name: str, scope: str | Scope = DEFAULT_SCOPE) -> bool:
        """Whether this plugin has an explicit switch record in the state file.

        A fresh install or a legacy registry entry has none; the caller then
        falls back to the registry rather than the default-on snapshot.
        """
        with self._lock:
            try:
                return self._entry(self._known(name), self._scope(scope)) is not None
            except LifecycleError:
                return False

    def effective(self, name: str) -> PluginSnapshot:
        with self._lock:
            plugin = self._known(name)
            scope = (
                Scope.WORKSPACE.value
                if self._entry(plugin, Scope.WORKSPACE.value) is not None
                else Scope.USER.value
            )
            return self._snapshot_locked(plugin, scope)

    def pause_all(self) -> bool:
        with self._lock:
            return bool(self._data.get("pause_all"))

    @property
    def unproven(self) -> bool:
        """True when the state file was structurally invalid; every switch is off."""
        with self._lock:
            return self._unproven

    # Public mutations

    def set_enabled(
        self,
        name: str,
        enabled: bool,
        *,
        scope: str | Scope = DEFAULT_SCOPE,
        expected_version: str | None = None,
        expected_etag: str | None = None,
        idempotency_key: str | None = None,
        actor: str = "user",
        reason: str = "",
    ) -> PluginSnapshot:
        with self._lock:
            plugin = self._known(name)
            scope_value = self._scope(scope)
            if not isinstance(enabled, bool):
                raise LifecycleError(
                    "invalid_request", 400, "enabled must be a boolean"
                )

            current = self._snapshot_locked(plugin, scope_value)
            if (
                expected_version is not None
                and expected_version != self._versions[plugin]
            ):
                _audit_refusal(plugin, "stale_state", "version mismatch")
                raise LifecycleError(
                    "stale_state",
                    409,
                    f"expected version {expected_version}, installed {self._versions[plugin]}",
                    current,
                )
            if expected_etag is not None and expected_etag != current.etag:
                _audit_refusal(plugin, "stale_state", "etag mismatch")
                raise LifecycleError(
                    "stale_state",
                    409,
                    "etag does not match the committed state",
                    current,
                )
            if enabled:
                # The HTTP route checks before it gets here; this is the gate the
                # CLI and every direct caller also pass through.
                from core import plugin_signing

                ok, reason = plugin_signing.verify_enable(plugin)
                if not ok:
                    from core.audit_log import audit_event

                    audit_event(
                        "plugin_gate",
                        tool=plugin,
                        decision="signature_denied",
                        detail=reason,
                    )
                    raise LifecycleError("signature_denied", 409, reason, current)
                blocked = self._blocked_dependency(plugin)
                if blocked is not None:
                    _audit_refusal(plugin, "dependency_blocked", blocked)
                    raise LifecycleError("dependency_blocked", 409, blocked, current)
                cycle = self._dependency_cycle(plugin)
                if cycle is not None:
                    raise LifecycleError(
                        "dependency_cycle", 409, " -> ".join(cycle), current
                    )

            request = {
                "enabled": enabled,
                "expected_version": expected_version or "",
                "version": self._versions[plugin],
            }
            key = (
                self._idempotency_hash(plugin, scope_value, actor, idempotency_key)
                if idempotency_key
                else ""
            )
            if key:
                cached = self._data["idempotency"].get(key)
                if cached is not None:
                    if cached.get("request") != request:
                        raise LifecycleError(
                            "idempotency_conflict",
                            409,
                            "idempotency key was used for a different request",
                            current,
                        )
                    return PluginSnapshot.from_dict(
                        cached["response"], self.pause_all()
                    )

            pending = self._pending.get((plugin, scope_value))
            if pending is not None:
                return self._snapshot_locked(plugin, scope_value)

            if (
                self._entry(plugin, scope_value) is not None
                and current.enabled is enabled
                and current.state is not PluginState.FAILED
            ):
                if key:
                    self._remember(key, request, current)
                    try:
                        self._persist(keep=(plugin, scope_value))
                    except LifecycleError:
                        self._data["idempotency"].pop(key, None)
                        raise
                return current

            before = self.effective(plugin).enabled
            after = self._preview_effective(plugin, scope_value, enabled)
            if not enabled and before and not after:
                dependents = self._enabled_dependents(plugin)
                if dependents:
                    raise LifecycleError(
                        "dependents_enabled", 409, ", ".join(dependents), current
                    )
            if before is after:
                return self._commit(
                    plugin,
                    scope_value,
                    enabled,
                    actor=actor,
                    reason=reason,
                    key=key,
                    request=request,
                )

            staged = self._begin_staged(
                plugin,
                scope_value,
                enabled,
                actor=actor,
                reason=reason,
                key=key,
                request=request,
            )
        return self._finish_staged(staged)

    def cancel(
        self,
        name: str,
        *,
        scope: str | Scope = DEFAULT_SCOPE,
        actor: str = "user",
        reason: str = "cancelled by user",
    ) -> PluginSnapshot:
        with self._lock:
            plugin = self._known(name)
            scope_value = self._scope(scope)
            pending = self._pending.get((plugin, scope_value))
            if pending is None:
                return self._snapshot_locked(plugin, scope_value)
            if pending.state is PluginState.DISABLING:
                raise LifecycleError(
                    "not_cancellable",
                    409,
                    "a disable is already tearing down",
                    self._snapshot_locked(plugin, scope_value),
                )
            pending.cancelled = True
            del self._pending[(plugin, scope_value)]
            entry = self._entry(plugin, scope_value, create=True)
            entry.pop("pending", None)
            self._persist()
            snap = self._snapshot_locked(plugin, scope_value)
            self._audit_entry(
                action="cancel",
                plugin=plugin,
                scope=scope_value,
                actor=actor,
                previous_state=pending.state.value,
                requested_state="enabled" if pending.requested_enabled else "disabled",
                state=snap.state.value,
                version=self._versions[plugin],
                duration_ms=self._elapsed(pending.started),
                reason=reason,
                status="cancelled",
            )
            self._publish("plugin.state", snap.as_dict())
            return snap

    def set_pause_all(
        self, enabled: bool, *, actor: str = "user", reason: str = ""
    ) -> dict[str, Any]:
        if not isinstance(enabled, bool):
            raise LifecycleError(
                "invalid_request", 400, "pause_all must be a boolean"
            )
        with self._lock:
            previous = bool(self._data.get("pause_all"))
            if previous is enabled:
                return {"pause_all": previous, "changed": False}
            self._data["pause_all"] = enabled
            try:
                self._persist()
            except LifecycleError:
                self._data["pause_all"] = previous
                raise
            self._audit_entry(
                action="pause" if enabled else "unpause",
                plugin="",
                scope="",
                actor=actor,
                previous_state="paused" if previous else "active",
                requested_state="paused" if enabled else "active",
                state="paused" if enabled else "active",
                version="",
                duration_ms=0,
                reason=reason,
                status="committed",
            )
            if not enabled:
                # An enable committed while paused deliberately did not start
                # its resource; unpause is where it starts.
                for name in sorted(self._versions):
                    snapshot = self.effective(name)
                    if snapshot.enabled and snapshot.state is not PluginState.FAILED:
                        try:
                            self._activator(name)
                        except Exception:
                            logger.exception("activating %s on unpause failed", name)
            self._publish("plugin.paused", {"pause_all": enabled})
            return {"pause_all": enabled, "changed": True}

    def import_legacy(self, legacy_path: Path) -> tuple[str, ...]:
        """Imports explicit legacy per-plugin states once (ADR-004, option B2).

        The old global bypass retired with O-1: only explicit ``enabled`` values
        migrate. The import writes state but never activates a capability.
        """
        from core.plugin_store import migrate_registry_items

        with self._lock:
            if self._data.get("legacy_imported"):
                return ()
            try:
                raw = json.loads(Path(legacy_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return ()
            items = raw.get("plugins") if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                return ()
            migrated = migrate_registry_items(
                [item for item in items if isinstance(item, dict) and item.get("name")]
            )
            states = {
                str(item["name"]): bool(item["enabled"])
                for item in migrated
                if isinstance(item.get("enabled"), bool)
            }
            applied = sorted(name for name in states if name in self._versions)
            master_bypass = isinstance(raw, dict) and raw.get("master_enabled") is False
            if master_bypass:
                notices = self._data.setdefault("notices", [])
                if not any(
                    notice.get("code") == "legacy_master_bypass_retired"
                    for notice in notices
                ):
                    notices.append(
                        {
                            "code": "legacy_master_bypass_retired",
                            "message": (
                                "The old global plugin switch was retired; "
                                "explicit per-plugin states are authoritative."
                            ),
                        }
                    )
            before = json.dumps(self._data)
            for name in applied:
                entry = self._entry(name, Scope.USER.value, create=True)
                entry.pop("pending", None)
                entry["committed"] = (
                    PluginState.ENABLED.value
                    if states[name]
                    else PluginState.DISABLED.value
                )
                entry["version"] = self._versions[name]
            self._data["legacy_imported"] = True
            try:
                self._persist()
            except LifecycleError:
                self._data = json.loads(before)
                raise
            for name in applied:
                self._audit_entry(
                    action="migrate",
                    plugin=name,
                    scope=Scope.USER.value,
                    actor="system",
                    previous_state="unproven",
                    requested_state="enabled" if states[name] else "disabled",
                    state=PluginState.ENABLED.value
                    if states[name]
                    else PluginState.DISABLED.value,
                    version=self._versions[name],
                    duration_ms=0,
                    reason="legacy plugins.json imported once",
                    status="committed",
                )
            return tuple(applied)

    def notices(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                dict(notice)
                for notice in self._data.get("notices", [])
                if isinstance(notice, dict)
            )

    def _blocked_dependency(self, plugin: str) -> str | None:
        for dependency in self._dependencies.get(plugin, ()):
            if dependency not in self._versions:
                return f"{dependency} (not installed)"
            if not self.effective(dependency).active:
                return dependency
        return None

    def _dependency_cycle(self, plugin: str) -> list[str] | None:
        def walk(name: str, path: list[str]) -> list[str] | None:
            if name in path:
                return path[path.index(name) :] + [name]
            for dependency in self._dependencies.get(name, ()):
                if dependency not in self._versions:
                    continue
                found = walk(dependency, [*path, name])
                if found is not None:
                    return found
            return None

        return walk(plugin, [])

    def _enabled_dependents(self, plugin: str) -> list[str]:
        return sorted(
            name
            for name, dependencies in self._dependencies.items()
            if plugin in dependencies
            and name in self._versions
            and self.effective(name).enabled
        )
