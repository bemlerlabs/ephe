"""The marketplace switch: install-if-needed, then set the lifecycle state."""

from __future__ import annotations

from typing import Any

from core import marketplace_service
from core.marketplace_service import _audit, _audit_refusal, _refused, install, plan

def switch(
    name: str,
    *,
    enabled: bool,
    source_id: str = "",
    version: str = "",
    approve_permissions: bool = False,
    allow_local_trust: bool = False,
) -> dict[str, Any]:
    """One switch: install-if-needed, then set the lifecycle state.

    The marketplace card used to split this into "Install" on the card and the
    real on/off switch somewhere else in settings. The call is idempotent: an
    installed plugin is only switched, a missing one is planned and installed
    first, and a refusal travels back as data so the surface can show exactly
    one consent instead of guessing from a stack trace.
    """
    from core.plugin_lifecycle_types import LifecycleError
    from core import plugin_runtime

    name = str(name or "").strip()
    if not name:
        return _refused("unknown_plugin", "a plugin name is required")
    lifecycle = plugin_runtime.lifecycle()
    try:
        snapshot = lifecycle.snapshot(name)
        installed = True
    except LifecycleError as exc:
        if exc.code != "unknown_plugin":
            raise
        installed = False
        snapshot = None

    if not installed:
        if not enabled:
            return {"status": "not_installed", "name": name, "enabled": False}
        planned = plan(
            source_id,
            name,
            version,
            approve_permissions=approve_permissions,
            allow_local_trust=allow_local_trust,
        )
        if planned.get("status") != "ready":
            _audit_refusal(name, planned)
            return planned
        result = install(planned)
        if result.get("status") != "extracted":
            return result
        active = bool(result.get("enabled", True))
        _audit(name, "switch_on", f"installed v{result.get('version', '')}")
        return {
            "status": "enabled" if active else "installed_disabled",
            "name": name,
            "version": str(result.get("version") or ""),
            "enabled": active,
            "phase": "enabled" if active else "installed",
            "activation_error": result.get("activation_error") or "",
        }

    if snapshot is not None and snapshot.enabled is enabled:
        # Idempotent: the switch is already where the user put it.
        return {
            "status": "enabled" if enabled else "disabled",
            "name": name,
            "version": snapshot.version,
            "enabled": snapshot.enabled,
            "phase": "enabled" if enabled else "disabled",
        }
    try:
        updated = lifecycle.set_enabled(name, enabled)
    except LifecycleError as exc:
        _audit(name, "switch_on" if enabled else "switch_off", exc.code)
        return {
            "status": "installed_disabled" if enabled else "error",
            "name": name,
            "version": snapshot.version if snapshot else "",
            "enabled": bool(exc.snapshot.enabled) if exc.snapshot else False,
            "phase": "installed",
            "code": exc.code,
            "activation_error": exc.detail or exc.code,
        }
    _audit(name, "switch_on" if enabled else "switch_off", f"v{updated.version}")
    return {
        "status": "enabled" if updated.enabled else "disabled",
        "name": name,
        "version": updated.version,
        "enabled": updated.enabled,
        "phase": "enabled" if updated.enabled else "disabled",
    }
