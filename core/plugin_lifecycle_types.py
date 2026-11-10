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

#: The two classes a mount can publish under. `signed` says a signature record came with
#: the directory and the enable-time gate read it; `local` says the author is the user,
#: which is the ordinary Creator case and is stated rather than implied, because a surface
#: that offers a mount has to say which of the two it is offering.
TRUST_LOCAL = "local"
TRUST_SIGNED = "signed"

#: The mount's steps, in the order they run. Everything up to `pin` refuses without
#: writing; from `lockfile` on, a failure rolls back, and the audit names the step by
#: these words.
STEP_MANIFEST = "manifest"
STEP_DESCRIPTORS = "descriptors"
STEP_CLAIMS = "claims"
STEP_PIN = "pin"
STEP_ARTIFACT = "artifact"
STEP_LOCKFILE = "lockfile"
STEP_ACTIVATION = "activation"
STEP_REGISTRY = "registry"
STEP_NOTIFY = "notify"

#: The steps that mutate. A failure in one of them has work to undo.
MUTATING_STEPS = (STEP_LOCKFILE, STEP_ACTIVATION, STEP_REGISTRY, STEP_NOTIFY)

#: The registry is written second to last, so a failure in it or after it needs the
#: previous descriptor batch put back.
REGISTRY_WRITTEN_STEPS = (STEP_REGISTRY, STEP_NOTIFY)

#: Refusal codes for the mount. A contested or a reserved name reuses the words the rail
#: already speaks (`ToolActivations.reason_for`, `dynamic_registry`'s collision codes), so
#: one refusal never acquires a second spelling.
REFUSE_MANIFEST = "mount_manifest_invalid"
REFUSE_CONFLICT = "mount_tool_conflict"
REFUSE_CHANGE = "mount_change_unacknowledged"
REFUSE_ARTIFACT = "mount_artifact_changed"
REFUSE_REGISTRY = "mount_registry_refused"


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
    """A refused or failed transition.

    ``data`` carries the structured payload a surface has to render rather than read
    out of a sentence — today a hot mount's tool diff (#15), whose fingerprints and
    changed fields are the alarm. It stays out of ``detail`` because the detail is the
    audit line and a reader's card needs the values, not a paragraph about them.
    """

    def __init__(
        self,
        code: str,
        status: int,
        detail: str = "",
        snapshot: PluginSnapshot | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail
        self.snapshot = snapshot
        self.data = data if isinstance(data, dict) else {}


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
