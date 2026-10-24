"""Read-side helpers for the plugin lifecycle."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, Literal, overload

from core.plugin_lifecycle_types import (
    SCOPES,
    LifecycleError,
    PluginSnapshot,
    PluginState,
    Scope,
    _Pending,
    _scope_value,
)


class LifecycleReads:
    _data: dict[str, Any]
    _versions: dict[str, str]
    _pending: dict[tuple[str, str], _Pending]
    _unproven: bool
    _clock: Callable[[], float]

    def _snapshot_locked(self, plugin: str, scope: str) -> PluginSnapshot:
        entry = self._entry(plugin, scope)
        pending = self._pending.get((plugin, scope))
        if pending is not None:
            state = pending.state
            enabled = pending.requested_enabled
        elif self._unproven:
            state, enabled = PluginState.DISABLED, False
        elif entry is not None:
            # An entry that exists but carries no committed value is a damaged
            # or half-written record, not a fresh install: it reads off.
            committed = str(entry.get("committed") or "")
            if committed == PluginState.FAILED.value:
                state, enabled = PluginState.FAILED, False
            elif committed == PluginState.ENABLED.value:
                state, enabled = PluginState.ENABLED, True
            else:
                state, enabled = PluginState.DISABLED, False
        else:
            state, enabled = PluginState.ENABLED, True
        paused = bool(self._data.get("pause_all"))
        if paused:
            state = PluginState.PAUSED
        version = self._versions[plugin]
        etag = f'"state-{version}-{scope}-{"true" if enabled else "false"}"'
        return PluginSnapshot(
            name=plugin,
            state=state,
            enabled=enabled,
            version=version,
            scope=scope,
            etag=etag,
            pause_all=paused,
        )

    def _preview_effective(self, plugin: str, scope: str, enabled: bool) -> bool:
        if scope == Scope.WORKSPACE.value:
            return enabled
        workspace = self._entry(plugin, Scope.WORKSPACE.value)
        if workspace is not None and not self._unproven:
            return str(workspace.get("committed")) == PluginState.ENABLED.value
        return enabled

    def _default_on(self) -> bool:
        return not self._unproven

    def _known(self, name: str) -> str:
        if name not in self._versions:
            raise LifecycleError(
                "unknown_plugin", 404, f"plugin '{name}' is not installed"
            )
        return name

    @staticmethod
    def _scope(scope: str | Scope) -> str:
        value = _scope_value(scope)
        if value not in SCOPES:
            raise LifecycleError(
                "invalid_request", 400, f"scope must be one of {SCOPES}"
            )
        return value

    @overload
    def _entry(
        self, plugin: str, scope: str, *, create: Literal[True]
    ) -> dict[str, Any]: ...

    @overload
    def _entry(
        self, plugin: str, scope: str, *, create: Literal[False] = False
    ) -> dict[str, Any] | None: ...

    def _entry(
        self, plugin: str, scope: str, *, create: bool = False
    ) -> dict[str, Any] | None:
        scopes = self._data["plugins"].get(plugin)
        if not isinstance(scopes, dict):
            if not create:
                return None
            scopes = {}
            self._data["plugins"][plugin] = scopes
        entry = scopes.get(scope)
        if not isinstance(entry, dict):
            if not create:
                return None
            entry = {}
            scopes[scope] = entry
        return entry

    def _elapsed(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))

    @staticmethod
    def _idempotency_hash(plugin: str, scope: str, actor: str, key: str) -> str:
        raw = f"{actor}|{plugin}|{scope}|{key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
