"""A transition is announced only after its committed state is on disk."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.plugin_lifecycle_events import publish
from core.plugin_lifecycle_types import (
    LifecycleError,
    PluginSnapshot,
    PluginState,
    _Pending,
    _Staged,
)


class LifecycleTransitions:
    _versions: dict[str, str]
    _pending: dict[tuple[str, str], _Pending]
    _token: int
    _data: dict[str, Any]
    _path: Path | None
    _activator: Callable[[str], None]
    _deactivator: Callable[[str], None]
    _clock: Callable[[], float]
    _lock: threading.RLock
    _flight_locks: dict[str, threading.Lock]
    _unproven: bool

    def _begin_staged(
        self,
        plugin: str,
        scope: str,
        enabled: bool,
        *,
        actor: str,
        reason: str,
        key: str,
        request: dict[str, Any],
    ) -> _Staged:
        entry = self._entry(plugin, scope, create=True)
        previous = (
            "disabled"
            if self._unproven
            else str(
                entry.get("committed")
                or ("enabled" if self._default_on() else "disabled")
            )
        )
        pending_state = PluginState.ENABLING if enabled else PluginState.DISABLING
        self._token += 1
        flight = _Pending(
            requested_enabled=enabled,
            state=pending_state,
            version=self._versions[plugin],
            token=self._token,
            previous=previous,
            actor=actor,
            started=self._clock(),
        )
        self._pending[(plugin, scope)] = flight
        entry["pending"] = {
            "state": pending_state.value,
            "requested_enabled": enabled,
            "version": self._versions[plugin],
            "actor": actor,
            "started": flight.started,
            "token": flight.token,
        }
        try:
            self._persist()
        except LifecycleError:
            self._pending.pop((plugin, scope), None)
            entry.pop("pending", None)
            raise
        self._publish(
            "plugin.pending",
            {
                "name": plugin,
                "token": flight.token,
                "phase": pending_state.value,
                "progress": 0,
            },
        )
        return _Staged(
            plugin=plugin,
            scope=scope,
            enabled=enabled,
            actor=actor,
            reason=reason,
            key=key,
            request=request,
            flight=flight,
            previous=previous,
        )

    def _finish_staged(self, staged: _Staged) -> PluginSnapshot:
        """Runs the activation under a per-plugin flight lock.

        A cancel removes the pending intent while the activation is still
        running. The lock keeps the canceled flight from unwinding beside a newer
        activation: the re-enable waits, the old flight rolls back its own
        resource, and only then does the new activation start.
        """
        with self._flight_lock(staged.plugin):
            return self._finish_flight(staged)

    def _finish_flight(self, staged: _Staged) -> PluginSnapshot:
        if staged.flight.cancelled:
            # Cancelled before the activation started: nothing was opened, so
            # there is nothing to tear down.
            with self._lock:
                if self._pending.get((staged.plugin, staged.scope)) is staged.flight:
                    self._pending.pop((staged.plugin, staged.scope), None)
                entry = self._entry(staged.plugin, staged.scope)
                if entry is not None:
                    self._pop_pending_intent(entry, staged.flight)
                return self._snapshot_locked(staged.plugin, staged.scope)

        try:
            if staged.enabled:
                self._activator(staged.plugin)
            else:
                self._deactivator(staged.plugin)
        except Exception as exc:
            return self._flight_failed(staged, exc)

        with self._lock:
            if staged.flight.cancelled:
                return self._rollback_cancelled(
                    staged, reason="activation completed after cancel"
                )
            if self._pending.get((staged.plugin, staged.scope)) is not staged.flight:
                # No cancel flag, but this flight no longer owns the switch. Its
                # activation is still the one it opened; undo exactly that.
                self._rollback_activation(staged.plugin)
                return self._snapshot_locked(staged.plugin, staged.scope)
            entry = self._entry(staged.plugin, staged.scope, create=True)
            self._pending.pop((staged.plugin, staged.scope), None)
            self._pop_pending_intent(entry, staged.flight)
            entry["committed"] = (
                PluginState.ENABLED.value
                if staged.enabled
                else PluginState.DISABLED.value
            )
            entry["version"] = self._versions[staged.plugin]
            try:
                self._persist()
            except LifecycleError as exc:
                entry["committed"] = staged.previous
                if staged.enabled:
                    self._rollback_activation(staged.plugin)
                else:
                    self._reactivate(staged.plugin)
                self._audit_entry(
                    action="enable" if staged.enabled else "disable",
                    plugin=staged.plugin,
                    scope=staged.scope,
                    actor=staged.actor,
                    previous_state=staged.previous,
                    requested_state="enabled" if staged.enabled else "disabled",
                    state=staged.previous,
                    version=self._versions[staged.plugin],
                    duration_ms=self._elapsed(staged.flight.started),
                    reason=str(exc),
                    status="failed",
                )
                self._publish(
                    "plugin.failed",
                    {
                        "name": staged.plugin,
                        "code": "state_write_failed",
                        "detail": str(exc),
                        "state": staged.previous,
                    },
                )
                raise
            snap = self._snapshot_locked(staged.plugin, staged.scope)
            if staged.key:
                self._remember(staged.key, staged.request, snap)
            self._audit_entry(
                action="enable" if staged.enabled else "disable",
                plugin=staged.plugin,
                scope=staged.scope,
                actor=staged.actor,
                previous_state=staged.previous,
                requested_state="enabled" if staged.enabled else "disabled",
                state=snap.state.value,
                version=self._versions[staged.plugin],
                duration_ms=self._elapsed(staged.flight.started),
                reason=staged.reason,
                status="committed",
            )
            self._publish("plugin.state", snap.as_dict())
            return snap

    def _flight_failed(self, staged: _Staged, exc: Exception) -> PluginSnapshot:
        key = (staged.plugin, staged.scope)
        with self._lock:
            cancelled = staged.flight.cancelled
            own = self._pending.get(key) is staged.flight
            entry = self._entry(staged.plugin, staged.scope, create=True) if own else None
            if own:
                self._pending.pop(key, None)
                self._pop_pending_intent(entry, staged.flight)
            if staged.enabled:
                rolled_back = self._rollback_activation(staged.plugin)
                if own and not cancelled:
                    entry["committed"] = PluginState.FAILED.value
                    entry["version"] = self._versions[staged.plugin]
                if cancelled:
                    self._audit_entry(
                        action="rollback",
                        plugin=staged.plugin,
                        scope=staged.scope,
                        actor=staged.actor,
                        previous_state=staged.previous,
                        requested_state="disabled",
                        state=PluginState.DISABLED.value,
                        version=self._versions[staged.plugin],
                        duration_ms=self._elapsed(staged.flight.started),
                        reason="cancelled activation rolled back",
                        status="committed" if rolled_back else "failed",
                    )
            try:
                if own:
                    self._persist()
            except LifecycleError:
                pass
            snap = self._snapshot_locked(staged.plugin, staged.scope)
            code = "activation_failed" if staged.enabled else "deactivation_failed"
            reason = f"{staged.reason}: {exc}" if staged.reason else str(exc)
            if cancelled:
                reason = f"cancelled: {reason}"
            self._audit_entry(
                action="enable" if staged.enabled else "disable",
                plugin=staged.plugin,
                scope=staged.scope,
                actor=staged.actor,
                previous_state=staged.previous,
                requested_state="enabled" if staged.enabled else "disabled",
                state=snap.state.value,
                version=self._versions[staged.plugin],
                duration_ms=self._elapsed(staged.flight.started),
                reason=reason,
                status="failed",
            )
            if not cancelled:
                self._publish(
                    "plugin.failed",
                    {
                        "name": staged.plugin,
                        "code": code,
                        "detail": str(exc),
                        "state": snap.state.value,
                    },
                )
            raise LifecycleError(code, 500, str(exc), snap) from exc

    def _rollback_cancelled(self, staged: _Staged, *, reason: str) -> PluginSnapshot:
        key = (staged.plugin, staged.scope)
        with self._lock:
            if self._pending.get(key) is staged.flight:
                self._pending.pop(key, None)
            entry = self._entry(staged.plugin, staged.scope)
            if entry is not None:
                self._pop_pending_intent(entry, staged.flight)
            rolled_back = self._rollback_activation(staged.plugin)
            if entry is not None and not rolled_back:
                entry["committed"] = PluginState.FAILED.value
                entry["version"] = self._versions[staged.plugin]
                with contextlib.suppress(LifecycleError):
                    self._persist()
            snap = self._snapshot_locked(staged.plugin, staged.scope)
            self._audit_entry(
                action="rollback",
                plugin=staged.plugin,
                scope=staged.scope,
                actor=staged.actor,
                previous_state=staged.previous,
                requested_state="disabled",
                state=snap.state.value,
                version=self._versions[staged.plugin],
                duration_ms=self._elapsed(staged.flight.started),
                reason=reason,
                status="committed" if rolled_back else "failed",
            )
            return snap

    def _flight_lock(self, plugin: str) -> threading.Lock:
        with self._lock:
            lock = self._flight_locks.get(plugin)
            if lock is None:
                lock = threading.Lock()
                self._flight_locks[plugin] = lock
            return lock

    @staticmethod
    def _pop_pending_intent(entry: dict[str, Any], flight: _Pending) -> None:
        pending = entry.get("pending")
        if isinstance(pending, dict) and pending.get("token") == flight.token:
            entry.pop("pending", None)

    def _commit(
        self,
        plugin: str,
        scope: str,
        enabled: bool,
        *,
        actor: str,
        reason: str,
        key: str,
        request: dict[str, Any],
    ) -> PluginSnapshot:
        entry = self._entry(plugin, scope, create=True)
        previous = (
            "disabled"
            if self._unproven
            else str(
                entry.get("committed")
                or ("enabled" if self._default_on() else "disabled")
            )
        )
        entry["committed"] = (
            PluginState.ENABLED.value if enabled else PluginState.DISABLED.value
        )
        entry["version"] = self._versions[plugin]
        try:
            self._persist()
        except LifecycleError:
            entry["committed"] = previous
            raise
        snap = self._snapshot_locked(plugin, scope)
        if key:
            self._remember(key, request, snap)
        self._audit_entry(
            action="enable" if enabled else "disable",
            plugin=plugin,
            scope=scope,
            actor=actor,
            previous_state=previous,
            requested_state="enabled" if enabled else "disabled",
            state=snap.state.value,
            version=self._versions[plugin],
            duration_ms=0,
            reason=reason,
            status="committed",
        )
        self._publish("plugin.state", snap.as_dict())
        return snap

    def _rollback_activation(self, plugin: str) -> bool:
        try:
            self._deactivator(plugin)
        except Exception:
            return False
        return True

    def _reactivate(self, plugin: str) -> None:
        with contextlib.suppress(Exception):
            self._activator(plugin)

    def _remember(
        self, key: str, request: dict[str, Any], snap: PluginSnapshot
    ) -> None:
        self._data["idempotency"][key] = {
            "request": request,
            "response": snap.as_dict(),
        }

    def _audit_entry(
        self,
        *,
        action: str,
        plugin: str,
        scope: str,
        actor: str,
        previous_state: str,
        requested_state: str,
        state: str,
        version: str,
        duration_ms: int,
        reason: str,
        status: str,
    ) -> None:
        self._audit(
            {
                "action": action,
                "plugin": plugin,
                "scope": scope,
                "actor": actor,
                "previous_state": previous_state,
                "requested_state": requested_state,
                "state": state,
                "version": version,
                "duration_ms": duration_ms,
                "reason": reason,
                "status": status,
            }
        )

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        publish(self._path, event, data)
