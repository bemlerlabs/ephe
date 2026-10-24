"""Installed inventory and available updates.

Read-only views for the Extension Center: what is on this device and which
newer compatible version a source offers. Installed rows carry the registry
switch state; updates never install anything.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core import __version__, marketplace_index, marketplace_sources, plugin_manifest
from core.plugin_store import load_registry

logger = logging.getLogger(__name__)


def _permissions(raw: Any) -> dict[str, list[str]]:
    data = raw if isinstance(raw, dict) else {}
    families = data.get("tool_families")
    roots = data.get("data_roots")
    return {
        "tool_families": [str(item) for item in families] if isinstance(families, list) else [],
        "data_roots": [str(item) for item in roots] if isinstance(roots, list) else [],
    }


def installed() -> dict[str, Any]:
    registry = {str(item.get("name")): item.get("enabled") is not False for item in load_registry()}

    def enabled_state(name: str) -> bool:
        try:
            from core import plugin_runtime

            lifecycle = plugin_runtime.lifecycle()
            if lifecycle.has_committed_state(name):
                return lifecycle.snapshot(name).enabled
        except Exception:
            logger.debug("lifecycle switch state read failed", exc_info=True)
        return registry.get(name, True)

    rows: list[dict[str, Any]] = []
    builtin_root = plugin_manifest.BUILTIN_PLUGINS_ROOT.resolve()
    for entry in plugin_manifest.scan_plugins():
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        name = str(manifest["name"])
        directory = Path(entry["dir"]).resolve()
        rows.append(
            {
                "name": name,
                "version": str(manifest.get("version") or ""),
                "description": str(manifest.get("description") or ""),
                "enabled": enabled_state(name),
                "origin": "bundled" if directory.is_relative_to(builtin_root) else "user",
                "components": sorted(
                    key
                    for key, value in (manifest.get("components") or {}).items()
                    if value
                ),
                "permissions": _permissions(manifest.get("permissions")),
            }
        )
    return {"plugins": sorted(rows, key=lambda row: row["name"])}


def updates() -> dict[str, Any]:
    current = {row["name"]: row for row in installed()["plugins"]}
    found: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for source in marketplace_sources.load_sources()["sources"]:
        read = marketplace_sources.read_source(source)
        index = read.get("index")
        if not isinstance(index, dict):
            errors.append({"source": source["title"], "error": str(read.get("error") or "")})
            continue
        for name, row in current.items():
            try:
                entry = marketplace_index.resolve_version(
                    index, name, ephe_version=__version__
                )
            except marketplace_index.IndexError:
                continue
            installed_key = marketplace_index.parse_semver(row["version"]) or (0, 0, 0)
            offered_key = marketplace_index.parse_semver(entry["version"]) or (0, 0, 0)
            if offered_key <= installed_key:
                continue
            candidate = {
                "name": name,
                "version": entry["version"],
                "installed_version": row["version"],
                "trust": entry["plugin"].get("trust"),
                "source_id": source["id"],
                "source_title": source["title"],
            }
            previous = found.get(name)
            if previous is None or (marketplace_index.parse_semver(candidate["version"]) or (0, 0, 0)) > (
                marketplace_index.parse_semver(previous["version"]) or (0, 0, 0)
            ):
                found[name] = candidate
    return {"updates": sorted(found.values(), key=lambda row: row["name"]), "errors": errors}
