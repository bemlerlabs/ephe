"""Read-only plugin_manager tool (P1).

The agent can list, search, inspect and health-check installed plugins. It
cannot install, enable, disable, update or remove: those actions stay with the
user approval gate and the lifecycle endpoint. The tool reads the same registry
and committed state the server uses, so an answer never invents a switch state.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from core.plugin_lifecycle import (
    STATE_FILENAME,
    LifecycleError,
    PluginLifecycle,
    PluginState,
)
from core.plugin_lockfile import LockfileError, build_lockfile, dependency_order
from core.plugin_registry import CapabilityKind, PluginRegistry
from core.plugin_store import config_root

_ACTIONS = ("list", "search", "inspect", "health")


def _repo_skills_root() -> Path:
    return Path(__file__).resolve().parents[2] / "skills"


def _registry() -> PluginRegistry:
    return PluginRegistry.load(None, _repo_skills_root())


def _lifecycle(versions: dict[str, str]) -> PluginLifecycle:
    return PluginLifecycle(config_root() / STATE_FILENAME, versions=versions)


def _versions(registry: PluginRegistry) -> dict[str, str]:
    return {plugin.id: plugin.version for plugin in registry.plugins}


def _plugin_entry(
    registry: PluginRegistry,
    lifecycle: PluginLifecycle,
    plugin_id: str,
) -> dict[str, Any]:
    plugin = next(item for item in registry.plugins if item.id == plugin_id)
    snapshot = lifecycle.effective(plugin_id)
    kinds = Counter(
        cap.kind.value for cap in registry.capabilities() if cap.owner == plugin_id
    )
    activated = sorted(
        tool for tool, owner in registry.tool_activations() if owner == plugin_id
    )
    return {
        "name": plugin.id,
        "version": plugin.version,
        "description": str(plugin.manifest.get("description", "")),
        "source": plugin.source,
        "state": snapshot.state.value,
        "enabled": snapshot.enabled,
        "scope": snapshot.scope,
        "etag": snapshot.etag,
        "capabilities": dict(sorted(kinds.items())),
        "activated_tools": activated,
        "dependencies": [str(dep) for dep in plugin.manifest.get("dependencies", [])],
    }


def _list() -> dict[str, Any]:
    registry = _registry()
    versions = _versions(registry)
    lifecycle = _lifecycle(versions)
    plugins = [
        _plugin_entry(registry, lifecycle, plugin.id) for plugin in registry.plugins
    ]
    return {
        "read_only": True,
        "counts": {
            "plugins": len(registry.plugins),
            "skills": len(registry.capabilities(CapabilityKind.SKILL)),
            "mcp": len(registry.capabilities(CapabilityKind.MCP_SERVER)),
            "commands": len(registry.capabilities(CapabilityKind.COMMAND)),
        },
        "plugins": plugins,
    }


def _search(query: str) -> dict[str, Any]:
    payload = _list()
    needle = (query or "").strip().lower()
    if needle:
        payload["plugins"] = [
            plugin
            for plugin in payload["plugins"]
            if needle in f"{plugin['name']} {plugin['description']}".lower()
        ]
    payload["query"] = query
    return payload


def _inspect(name: str) -> dict[str, Any]:
    registry = _registry()
    plugin = next((item for item in registry.plugins if item.id == name), None)
    if plugin is None:
        return {
            "read_only": True,
            "error": "unknown_plugin",
            "name": name,
            "detail": "no installed plugin has that id",
        }
    lifecycle = _lifecycle(_versions(registry))
    snapshot = lifecycle.effective(name)
    commands = [
        {
            "name": str(command["name"]),
            "description": str(command.get("description", "")),
        }
        for command in plugin.manifest.get("components", {}).get("commands", [])
    ]
    return {
        "read_only": True,
        "plugin": {
            "name": plugin.id,
            "version": plugin.version,
            "description": str(plugin.manifest.get("description", "")),
            "source": plugin.source,
            "state": snapshot.state.value,
            "enabled": snapshot.enabled,
            "scope": snapshot.scope,
            "etag": snapshot.etag,
        },
        "declared_commands": commands,
        "capabilities": sorted(
            cap.id for cap in registry.capabilities() if cap.owner == name
        ),
        "activated_tools": sorted(
            tool for tool, owner in registry.tool_activations() if owner == name
        ),
        "dependencies": [str(dep) for dep in plugin.manifest.get("dependencies", [])],
    }


def _health() -> dict[str, Any]:
    lock = build_lockfile(None)
    issues: list[dict[str, str]] = []
    for entry in lock["quarantined"]:
        issues.append({"name": str(entry["name"]), "kind": "quarantined"})
    names = {str(entry["name"]) for entry in lock["plugins"]}
    for entry in lock["plugins"]:
        for dependency in entry["dependencies"]:
            if dependency not in names:
                issues.append(
                    {
                        "name": str(entry["name"]),
                        "kind": "missing_dependency",
                        "detail": str(dependency),
                    }
                )
    try:
        dependency_order(lock["plugins"])
    except LockfileError as exc:
        if exc.code == "dependency_cycle":
            issues.append(
                {"name": "", "kind": "dependency_cycle", "detail": exc.detail}
            )

    versions = {str(entry["name"]): str(entry["version"]) for entry in lock["plugins"]}
    lifecycle = _lifecycle(versions)
    for name in versions:
        try:
            snapshot = lifecycle.effective(name)
        except LifecycleError:
            continue
        if snapshot.state is PluginState.FAILED:
            issues.append({"name": name, "kind": "failed_state"})
    issues.sort(key=lambda item: (item["name"], item["kind"]))
    return {
        "read_only": True,
        "status": "ok" if not issues else "degraded",
        "checked": len(lock["plugins"]),
        "issues": issues,
    }


def plugin_manager(action: str, query: str = "", name: str = "") -> str:
    """Read-only view of installed plugins, capabilities and switch state.

    Args:
        action: 'list', 'search', 'inspect' or 'health'.
        query: search text for 'search' (matches name and description).
        name: plugin id for 'inspect'.

    Returns:
        A JSON document. Unknown or mutating actions return a read_only error.
    """
    normalized = (action or "").strip().lower()
    if normalized not in _ACTIONS:
        return json.dumps(
            {
                "read_only": True,
                "error": "read_only",
                "action": normalized,
                "allowed": list(_ACTIONS),
                "detail": (
                    "plugin_manager only reads; install, enable, disable, update "
                    "and remove need explicit user approval through the lifecycle endpoint"
                ),
            },
            ensure_ascii=False,
        )
    if normalized == "list":
        payload = _list()
    elif normalized == "search":
        payload = _search(query)
    elif normalized == "inspect":
        if not name:
            payload = {
                "read_only": True,
                "error": "invalid_request",
                "detail": "inspect needs a plugin name",
            }
        else:
            payload = _inspect(name)
    else:
        payload = _health()
    return json.dumps(payload, ensure_ascii=False)


PLUGIN_MANAGER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "plugin_manager",
        "description": (
            "Read-only view of installed plugins, their capabilities, switch state "
            "and health. Actions: 'list' (whole portfolio), 'search' (name and "
            "description), 'inspect' (one plugin), 'health' (quarantine, missing "
            "dependencies, failed switches). It never installs, enables, disables, "
            "updates or removes a plugin — those need explicit user approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(_ACTIONS),
                    "description": "Read action to run.",
                },
                "query": {
                    "type": "string",
                    "description": "Search text for action='search'.",
                },
                "name": {
                    "type": "string",
                    "description": "Plugin id for action='inspect'.",
                },
            },
            "required": ["action"],
        },
    },
}
