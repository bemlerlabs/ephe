"""Ephe — Plugin runtime gate (P1 ownership).

A plugin owns its activations; the capability stays kernel-owned. The gate maps
each tool to the plugin that declares it in ``components.tools``, and to
``mcp-connector`` for the ``mcp_`` namespace. The manifests and the committed
lifecycle state are the only sources — there is no hardcoded family map.

Honesty contracts:
- Only an explicit committed state gates. A plugin with no entry keeps the
  current effective behavior (enabled) until it is written explicitly.
- The legacy ``plugins.json`` is imported once at the first gate read; after
  that the lifecycle state file is authoritative. The old ``master_enabled``
  bypass retired with O-1: explicit per-plugin states win.
- Pause all hides every plugin-owned capability without rewriting the
  per-plugin states.
- TOOL_MAP stays complete; gating applies to the schema view and execution.
  Unknown tool names and unknown plugin ids never crash.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from core import plugin_manifest
from core.plugin_lifecycle import (
    STATE_FILENAME,
    LifecycleError,
    PluginLifecycle,
)
from core.plugin_registry import ToolActivations, scan_tool_activations
from core.plugin_store import REGISTRY_FILENAME, config_root, migrate_registry_items

MCP_PREFIX = "mcp_"
MCP_CONNECTOR_PLUGIN = "mcp-connector"


@dataclass(frozen=True)
class Gate:
    visible: bool
    plugin: str = ""


@dataclass(frozen=True)
class StoreState:
    enabled: dict[str, bool]
    pause_all: bool
    unproven: bool


# Legacy state (kept for the one-release compatibility route and the store view)


def _read_registry(path=None) -> dict:
    target = path if path is not None else config_root() / REGISTRY_FILENAME
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_master_enabled(path=None) -> bool:
    """Legacy master value; the gate no longer consults it (O-1)."""
    raw = _read_registry(path)
    value = raw.get("master_enabled")
    return bool(value) if isinstance(value, bool) else True


def load_registry_map(path=None) -> dict[str, bool]:
    raw = _read_registry(path)
    items = raw.get("plugins")
    if not isinstance(items, list):
        return {}
    migrated = migrate_registry_items(
        [p for p in items if isinstance(p, dict) and p.get("name")]
    )
    return {str(p["name"]): bool(p["enabled"]) for p in migrated}


def set_master_enabled(enabled: bool, path=None) -> bool:
    """Persists the legacy value for the old route; it does not gate."""
    target = path if path is not None else config_root() / REGISTRY_FILENAME
    raw = _read_registry(target)
    items = raw.get("plugins") if isinstance(raw.get("plugins"), list) else []
    body = {"plugins": items, "master_enabled": bool(enabled)}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        return False
    return True


# Ownership and lifecycle state


def _roots_key() -> tuple[str, str]:
    return (
        str(plugin_manifest.plugins_root()),
        str(plugin_manifest.BUILTIN_PLUGINS_ROOT),
    )


@lru_cache(maxsize=8)
def _activations_cached(user_root: str, builtin_root: str) -> ToolActivations:
    return scan_tool_activations(None)


@lru_cache(maxsize=8)
def _versions_cached(user_root: str, builtin_root: str) -> tuple[tuple[str, str], ...]:
    out = []
    for entry in plugin_manifest.scan_plugins():
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        out.append((str(manifest["name"]), str(manifest["version"])))
    return tuple(sorted(out))


@lru_cache(maxsize=8)
def _dependencies_cached(
    user_root: str, builtin_root: str
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    out = []
    for entry in plugin_manifest.scan_plugins():
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        dependencies = manifest.get("dependencies", [])
        if isinstance(dependencies, list):
            out.append((str(manifest["name"]), tuple(str(dep) for dep in dependencies)))
    return tuple(sorted(out))


def invalidate_ownership_cache() -> None:
    """Drops the manifest-derived view after an install, remove or edit."""
    global _LIFECYCLE, _LIFECYCLE_KEY
    _activations_cached.cache_clear()
    _versions_cached.cache_clear()
    _dependencies_cached.cache_clear()
    with _LIFECYCLE_LOCK:
        _LIFECYCLE = None
        _LIFECYCLE_KEY = None


def _installed_versions() -> dict[str, str]:
    return dict(_versions_cached(*_roots_key()))


def _dependencies() -> dict[str, tuple[str, ...]]:
    return dict(_dependencies_cached(*_roots_key()))


def _activations() -> tuple[dict[str, str], frozenset[str]]:
    scanned = _activations_cached(*_roots_key())
    return dict(scanned.owners), frozenset(scanned.conflicts)


def _activate(plugin: str) -> None:
    from core.skills import invalidate_skill_cache

    invalidate_skill_cache()
    if plugin == MCP_CONNECTOR_PLUGIN:
        from core.tools import mcp_client

        mcp_client.request_mcp_refresh()


def _deactivate(plugin: str) -> None:
    from core import plugin_activity
    from core.skills import invalidate_skill_cache

    plugin_activity.teardown_plugin(plugin)
    if plugin == MCP_CONNECTOR_PLUGIN:
        from core.tools import mcp_client

        mcp_client.teardown_mcp_connector_sync()
    invalidate_skill_cache()


def _manifest_signature() -> str:
    return repr((tuple(_installed_versions().items()), tuple(_dependencies().items())))


_LIFECYCLE_LOCK = threading.Lock()
_LIFECYCLE: PluginLifecycle | None = None
_LIFECYCLE_KEY: tuple[str, str] | None = None


def lifecycle(state_path: Path | None = None) -> PluginLifecycle:
    """One process-wide lifecycle per state file and installed-manifest set.

    A fresh instance per request would read the persisted pending intent as a
    crash leftover and drop it, so two requests could stage the same activation.
    """
    global _LIFECYCLE, _LIFECYCLE_KEY
    path = (
        Path(state_path) if state_path is not None else config_root() / STATE_FILENAME
    )
    key = (str(path.resolve()), _manifest_signature())
    with _LIFECYCLE_LOCK:
        if _LIFECYCLE is None or _LIFECYCLE_KEY != key:
            state = PluginLifecycle(
                path,
                versions=_installed_versions(),
                dependencies=_dependencies(),
                activator=_activate,
                deactivator=_deactivate,
            )
            legacy = path.parent / REGISTRY_FILENAME
            if not path.exists() and legacy.exists():
                try:
                    state.import_legacy(legacy)
                except LifecycleError:
                    pass
            _LIFECYCLE = state
            _LIFECYCLE_KEY = key
        current = _LIFECYCLE
    current.reload_if_changed()
    return current


def active_plugin_ids(path: Path | None = None) -> frozenset[str]:
    """Plugins whose committed state is active and not globally paused."""
    state = lifecycle(path)
    active = set()
    for name in _installed_versions():
        if state.effective(name).active:
            active.add(name)
    return frozenset(active)


def effective_enabled(plugin_id: str, path: Path | None = None) -> bool:
    """The switch position, ignoring pause all."""
    if plugin_id not in _installed_versions():
        return True
    return lifecycle(path).effective(plugin_id).enabled


def pause_all_state(path: Path | None = None) -> bool:
    return lifecycle(path).pause_all()


def notices(registry_file: str | Path | None = None) -> tuple[dict[str, Any], ...]:
    state_path = (
        Path(registry_file).parent / STATE_FILENAME
        if registry_file is not None
        else None
    )
    return lifecycle(state_path).notices()


def store_state(
    names: list[str], registry_file: str | Path | None = None
) -> StoreState:
    """Switch truth for the store view: one lifecycle read for every name.

    ``unproven`` means the state file was structurally invalid. The store view
    then presents every switch as off; it never falls back to the legacy
    ``master_enabled`` value.
    """
    state_path = (
        Path(registry_file).parent / STATE_FILENAME
        if registry_file is not None
        else None
    )
    state = lifecycle(state_path)
    versions = _installed_versions()
    unproven = state.unproven
    enabled: dict[str, bool] = {}
    for raw_name in names:
        name = str(raw_name)
        if not name:
            continue
        if name in versions:
            enabled[name] = state.effective(name).enabled
        else:
            enabled[name] = not unproven
    return StoreState(
        enabled=enabled,
        pause_all=state.pause_all(),
        unproven=state.unproven,
    )


def is_plugin_active(plugin_id: str, path=None) -> bool:
    if plugin_id not in _installed_versions():
        return True
    return plugin_id in active_plugin_ids(Path(path) if path is not None else None)


# Gate decisions


def _gate_with(
    active: frozenset[str],
    activations: dict[str, str],
    conflicts: frozenset[str],
    tool_name: str,
) -> Gate:
    if tool_name in conflicts:
        return Gate(False)
    owner = activations.get(tool_name)
    if owner is not None:
        return Gate(owner in active, owner)
    if tool_name.startswith(MCP_PREFIX):
        return Gate(MCP_CONNECTOR_PLUGIN in active, MCP_CONNECTOR_PLUGIN)
    return Gate(True)


def tool_gate(tool_name: str, path=None) -> Gate:
    activations, conflicts = _activations()
    return _gate_with(
        active_plugin_ids(Path(path) if path is not None else None),
        activations,
        conflicts,
        tool_name,
    )


def is_tool_visible(tool_name: str, path=None) -> bool:
    return tool_gate(tool_name, path).visible


def filter_schemas(schemas: list[dict], path=None) -> list[dict]:
    """Post-filter for get_tool_schemas(), outside the schema cache."""
    active = active_plugin_ids(Path(path) if path is not None else None)
    activations, conflicts = _activations()
    if not conflicts and len(active) == len(_installed_versions()):
        return schemas
    out: list[dict] = []
    for entry in schemas:
        name = entry.get("function", {}).get("name", "")
        if _gate_with(active, activations, conflicts, name).visible:
            out.append(entry)
    return out
