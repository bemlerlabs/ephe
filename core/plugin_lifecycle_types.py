"""Types and constants shared by the plugin lifecycle modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATE_FILENAME = "plugin-state.json"

DEFAULT_SCOPE = "user"
SCOPES = ("user", "workspace")


class PluginState(str, Enum):
    DISABLED = "disabled"
    ENABLING = "enabling"
    ENABLED = "enabled"
    DEGRADED = "degraded"
    DISABLING = "disabling"
    FAILED = "failed"
    UPDATING = "updating"
    LOCKED = "locked"
    PAUSED = "paused"


class Scope(str, Enum):
    USER = "user"
    WORKSPACE = "workspace"


@dataclass(frozen=True)
class PluginSnapshot:
    name: str
    state: PluginState
    enabled: bool
    version: str
    scope: str
    etag: str
    pause_all: bool = False

    @property
    def active(self) -> bool:
        return self.state in (
            PluginState.ENABLED,
            PluginState.DEGRADED,
            PluginState.UPDATING,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "enabled": self.enabled,
            "version": self.version,
            "scope": self.scope,
            "etag": self.etag,
            "pause_all": self.pause_all,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], pause_all: bool) -> PluginSnapshot:
        return cls(
            name=str(raw["name"]),
            state=PluginState(str(raw["state"])),
            enabled=bool(raw["enabled"]),
            version=str(raw["version"]),
            scope=str(raw["scope"]),
            etag=str(raw["etag"]),
            pause_all=pause_all,
        )


class LifecycleError(Exception):
    def __init__(
        self,
        code: str,
        status: int,
        detail: str = "",
        snapshot: PluginSnapshot | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail
        self.snapshot = snapshot


@dataclass
class _Pending:
    requested_enabled: bool
    state: PluginState
    version: str
    token: int
    previous: str
    actor: str
    started: float
    cancelled: bool = False


@dataclass
class _Staged:
    plugin: str
    scope: str
    enabled: bool
    actor: str
    reason: str
    key: str
    request: dict[str, Any]
    flight: _Pending
    previous: str


def _scope_value(scope: str | Scope) -> str:
    return scope.value if isinstance(scope, Scope) else str(scope)


def _default_audit(entry: dict[str, Any]) -> None:
    from core.audit_log import audit_event

    audit_event(
        "plugin_lifecycle",
        tool=str(entry["plugin"]),
        decision=str(entry["action"]),
        status=str(entry["status"]),
        duration_ms=int(entry["duration_ms"]),
        actor=str(entry.get("actor") or ""),
        detail=(
            f"scope={entry['scope']} previous={entry['previous_state']} "
            f"requested={entry['requested_state']} version={entry['version']} "
            f"reason={entry['reason']!r}"
        ),
    )
