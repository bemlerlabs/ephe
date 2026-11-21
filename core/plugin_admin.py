"""Install audit rows, version helpers and the registry entry.

These helpers are shared by the installer and the version-history layer; they
touch the device registry and the audit sink, never a staged artifact.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core import plugin_manifest
from core.plugin_listing import load_marketplace
from core.plugin_store import (
    REGISTRY_FILENAME,
    _write_registry,
    config_root,
    load_registry,
)

logger = logging.getLogger(__name__)


def _audit_install(
    name: str, result: dict[str, Any], marketplace: dict[str, Any] | None
) -> None:
    try:
        from core.audit_log import audit_event

        listing = marketplace if isinstance(marketplace, dict) else load_marketplace()
        entry = next(
            (
                item
                for item in listing.get("plugins", [])
                if str(item.get("name")) == str(name)
            ),
            {},
        )
        audit_event(
            "plugin_install",
            tool=str(name),
            decision=str(result.get("status") or ""),
            # A retry of the same artifact is a successful no-op, not a denial:
            # the row a reader audits must not call an unchanged install refused.
            status=(
                "ok"
                if result.get("status") in {"extracted", "already_installed"}
                else "denied"
            ),
            detail=(
                f"version={result.get('version') or entry.get('version') or ''} "
                f"trust={result.get('trust') or entry.get('trust') or ''} "
                f"artifact={str(entry.get('sha256') or '')[:12]} "
                f"error={str(result.get('error') or result.get('code') or '')[:160]}"
            ),
        )
    except Exception:
        logger.exception("plugin install audit write failed")


def _version_key(version: str) -> tuple[int, ...]:
    """The numeric shape of an X.Y.Z manifest version, for the floor comparison."""
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError:
        return ()


def _installed_version(root: Path) -> str:
    """The version of the plugin already at `root`, or empty when none is there."""
    if not root.is_dir():
        return ""
    manifest, _error = plugin_manifest.load_manifest(root)
    return str(manifest.get("version", "")) if manifest else ""


def _register_installed(name: str) -> None:
    """Best-effort: make the installed plugin visible as an explicit registry
    entry. E5 wiring: the deep setting `plugins.plugin_autorun` (default
    OFF, conservative) decides whether a fresh install lands enabled."""
    from core import plugin_switch_policy
    from core.settings_schema import deep_bool

    enabled = deep_bool("plugins.plugin_autorun") and not plugin_switch_policy.read_only()
    items = load_registry()
    existing = next((p for p in items if str(p.get("name")) == name), None)
    if existing is not None:
        # An update keeps the switch the user already set: the row is the position, and a
        # second commit could only move it behind their back.
        enabled = existing.get("enabled") is not False
        if enabled:
            from core import plugin_runtime as _runtime

            try:
                _runtime.lifecycle().set_enabled(
                    name, True, actor="marketplace", reason="marketplace update"
                )
            except Exception:  # noqa: BLE001 — the row already says so; the switch is best-effort
                pass
        return
    items.append({"name": name, "enabled": enabled})
    try:
        _write_registry(items, config_root() / REGISTRY_FILENAME)
    except OSError:
        logger.exception("plugin registry write failed")
    from core import plugin_runtime
    from core.plugin_lifecycle import LifecycleError
    from core.skills import invalidate_skill_cache

    # The lifecycle's installed set comes from the same scan, so it has to be rebuilt
    # before the switch is committed - otherwise `set_enabled` refuses an install it has
    # not seen yet (unknown_plugin) and the registry and the lifecycle disagree.
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()
    try:
        plugin_runtime.lifecycle().set_enabled(
            name, enabled, actor="marketplace", reason="marketplace install"
        )
    except LifecycleError:
        # A failure here would leave registry and lifecycle disagreeing about the switch,
        # which is exactly the state this function exists to prevent - so it is loud.
        logger.exception("lifecycle switch after install failed for %s", name)
