"""Planning one marketplace install.

A plan pins exact version, hash, trust and the permission delta the user sees.
Nothing is downloaded here; the plan is a comparison of the source index with
what is installed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core import __version__, marketplace_index, marketplace_sources, plugin_manifest


class ServiceError(ValueError):
    def __init__(self, code: str, detail: str = "", status: int = 400) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail
        self.status = status


def _source(source_id: str) -> dict[str, Any]:
    for source in marketplace_sources.load_sources()["sources"]:
        if source["id"] == source_id:
            return source
    raise ServiceError("unknown_source", source_id, 404)


def _installed_manifest(name: str) -> dict[str, Any] | None:
    directory = plugin_manifest.plugins_root() / name
    manifest, _error = plugin_manifest.load_manifest(directory)
    return manifest


def _installed_version(name: str) -> str:
    manifest = _installed_manifest(name)
    return str(manifest.get("version") or "") if manifest else ""


def _permissions(raw: Any) -> dict[str, list[str]]:
    data = raw if isinstance(raw, dict) else {}
    families = data.get("tool_families")
    roots = data.get("data_roots")
    return {
        "tool_families": [str(item) for item in families] if isinstance(families, list) else [],
        "data_roots": [str(item) for item in roots] if isinstance(roots, list) else [],
    }


def permission_delta(old_manifest: dict[str, Any] | None, new_raw: Any) -> dict[str, Any]:
    old = _permissions((old_manifest or {}).get("permissions"))
    new = _permissions(new_raw)
    families_added = sorted(set(new["tool_families"]) - set(old["tool_families"]))
    families_removed = sorted(set(old["tool_families"]) - set(new["tool_families"]))
    roots_added = sorted(set(new["data_roots"]) - set(old["data_roots"]))
    roots_removed = sorted(set(old["data_roots"]) - set(new["data_roots"]))
    core = {
        "tool_families_added": families_added,
        "tool_families_removed": families_removed,
        "data_roots_added": roots_added,
        "data_roots_removed": roots_removed,
    }
    core["digest"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return core


def _refused(code: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": "refused", "code": code, "error": detail, **extra}


def _plan_meta(entry: dict[str, Any]) -> dict[str, Any]:
    plugin = entry.get("plugin", {})
    return {
        "name": plugin.get("name") or "",
        "displayName": plugin.get("displayName") or "",
        "description": plugin.get("description") or "",
        "publisher": plugin.get("publisher") or {},
        "trust": plugin.get("trust") or "local",
        "categories": plugin.get("categories") or [],
        "icon": plugin.get("icon") or {},
    }


def plan(
    source_id: str,
    name: str,
    version: str = "",
    *,
    approve_permissions: bool = False,
    allow_local_trust: bool = False,
) -> dict[str, Any]:
    source = _source(source_id)
    read = marketplace_sources.read_source(source)
    index = read.get("index")
    if not isinstance(index, dict):
        return _refused("source_unavailable", read.get("error") or "no index")
    try:
        entry = marketplace_index.resolve_version(
            index, name, version, ephe_version=__version__
        )
    except marketplace_index.IndexError as exc:
        return _refused(exc.code, exc.detail or str(exc), path=exc.path)

    if (
        entry["plugin"].get("kind") == "skill-pack"
        and entry["plugin"].get("provenance") != "third-party"
    ):
        return _refused("bundled_not_installable", "skill packs ship with the app")

    old_manifest = _installed_manifest(name)
    installed = str(old_manifest.get("version") or "") if old_manifest else ""
    new_version = str(entry["version"])
    if installed == new_version:
        return {
            "status": "already_installed",
            "name": name,
            "version": new_version,
            "installed_version": installed,
        }
    old_key = marketplace_index.parse_semver(installed) or (0, 0, 0)
    new_key = marketplace_index.parse_semver(new_version) or (0, 0, 0)
    if installed and new_key < old_key:
        return _refused("downgrade", f"installed {installed}, offered {new_version}")

    delta = permission_delta(old_manifest, entry.get("permissions"))
    signature = entry["source"].get("signature")
    plugin_trust = str(entry["plugin"].get("trust") or "local")
    local_unsigned = plugin_trust in {"local", "bundled"} and not isinstance(signature, dict)
    if local_unsigned and not allow_local_trust:
        return _refused("local_trust_required", "this artifact carries no signature")
    added = bool(delta["tool_families_added"] or delta["data_roots_added"])
    if added and old_manifest is not None and not approve_permissions:
        return {
            "status": "permission_review",
            "name": name,
            "version": new_version,
            "installed_version": installed,
            "delta": delta,
            **_plan_meta(entry),
        }

    return {
        "status": "ready",
        "name": name,
        "version": new_version,
        "installed_version": installed,
        "sha256": entry["source"]["sha256"],
        "url": entry["source"]["url"],
        "trust": plugin_trust,
        "signature": signature if isinstance(signature, dict) else None,
        "permissions": entry.get("permissions") or {},
        "components": entry.get("components") or [],
        "delta": delta,
        "approved_delta": delta["digest"] if approve_permissions and added else "",
        "allow_local_trust": allow_local_trust,
        "source_id": source["id"],
        "source_title": source["title"],
        "stale": bool(read.get("error")),
        **_plan_meta(entry),
    }


