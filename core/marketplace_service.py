"""Marketplace service: plan one install, then commit that exact artifact.

A plan pins version, hash, trust and the permission delta the user approves.
The commit re-reads the source, refuses a changed index, and passes an inspect
hook into staging so the bytes must still match the plan before they replace
the running version.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core import (
    __version__,
    guarded_fetch,
    marketplace_index,
    marketplace_sources,
    path_guard,
    plugin_market,
    plugin_versions,
)
from core.marketplace_planner import (
    ServiceError,
    _installed_manifest,
    _installed_version,
    _permissions,
    _refused,
    _source,
    permission_delta,
    plan,
)
from core.plugin_lockfile import LOCK_FILENAME, build_lockfile, write_lockfile
from core.plugin_store import config_root

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
ARTIFACT_TIMEOUT_S = 30


def _dependency_state(name: str) -> str:
    from core import plugin_runtime

    try:
        snapshot = plugin_runtime.lifecycle().snapshot(name)
    except Exception:  # noqa: BLE001 — an unknown dependency is a missing one
        return "missing"
    return "ok" if snapshot.enabled else "disabled"


def _local_fetcher(index_path: Path) -> Callable[[str], bytes]:
    base = index_path.parent

    def fetch(url: str) -> bytes:
        target = path_guard.confine(base / url, base)
        if target is None or not target.is_file():
            raise ServiceError("artifact_missing", url, 404)
        payload = target.read_bytes()
        if len(payload) > MAX_ARTIFACT_BYTES:
            raise ServiceError("artifact_too_large", url, 422)
        return payload

    return fetch


def _https_fetcher(source_url: str) -> Callable[[str], bytes]:
    def fetch(url: str) -> bytes:
        target = urllib.parse.urljoin(source_url, url)
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ServiceError("artifact_insecure", "artifact URL must be https", 422)
        try:
            return guarded_fetch.fetch_https(
                target,
                max_bytes=MAX_ARTIFACT_BYTES,
                timeout=ARTIFACT_TIMEOUT_S,
                accept="application/zip",
            )
        except guarded_fetch.GuardedFetchError as exc:
            raise ServiceError(exc.code, exc.detail, 422) from exc

    return fetch


def _make_inspect(
    *,
    name: str,
    version: str,
    old_manifest: dict[str, Any] | None,
    approved_delta: str,
) -> Callable[[Path, dict[str, Any]], str | None]:
    def inspect(_candidate: Path, manifest: dict[str, Any]) -> str | None:
        if str(manifest.get("name")) != name:
            return f"identity_mismatch: name {manifest.get('name')}"
        if str(manifest.get("version")) != version:
            return f"identity_mismatch: version {manifest.get('version')}"
        engine = manifest.get("engines")
        if (
            isinstance(engine, dict)
            and engine.get("ephe")
            and not marketplace_index.compatible(str(engine["ephe"]), __version__)
        ):
            return f"incompatible: needs Ephe {engine['ephe']}"
        dependencies = manifest.get("dependencies") or []
        for dependency in dependencies if isinstance(dependencies, list) else []:
            state = _dependency_state(str(dependency))
            if state != "ok":
                return f"dependency_{state}: {dependency}"
        actual = permission_delta(old_manifest, manifest.get("permissions"))
        if (
            (actual["tool_families_added"] or actual["data_roots_added"])
            and (not approved_delta or actual["digest"] != approved_delta)
        ):
            return "permission_delta: " + json.dumps(actual, separators=(",", ":"))
        return None

    return inspect


def _invalidate() -> None:
    from core import plugin_runtime
    from core.skills import invalidate_skill_cache

    invalidate_skill_cache()
    plugin_runtime.invalidate_ownership_cache()


def _write_lock() -> str:
    try:
        write_lockfile(config_root() / LOCK_FILENAME, build_lockfile())
        return ""
    except Exception:  # noqa: BLE001 — the package change already happened
        return "lockfile_update_failed"


def _audit(name: str, action: str, detail: str) -> None:
    try:
        from core.audit_log import audit_event

        audit_event("marketplace", tool=name, decision=action, status="ok", detail=detail)
    except Exception:  # noqa: BLE001
        return


def _audit_refusal(name: str, result: dict[str, Any]) -> dict[str, Any]:
    """A refusal before the install wrapper is still a refusal and gets a line.

    The wrapper audits what it decided; what never reached it — a stale plan, a
    changed index, a dependency that blocks a removal — used to leave nothing.
    """
    try:
        from core.audit_log import audit_event

        audit_event(
            "marketplace",
            tool=name,
            decision=str(result.get("code") or result.get("status") or "refused"),
            status="denied",
            detail=str(result.get("error") or "")[:200],
        )
    except Exception:  # noqa: BLE001
        pass
    return result


def install(plan_data: dict[str, Any]) -> dict[str, Any]:
    if plan_data.get("status") != "ready":
        return _audit_refusal(str(plan_data.get("name") or ""), plan_data)
    name = str(plan_data["name"])
    version = str(plan_data["version"])
    source = _source(str(plan_data["source_id"]))
    read = marketplace_sources.read_source(source)
    index = read.get("index")
    if not isinstance(index, dict):
        return _audit_refusal(
            name, _refused("source_unavailable", read.get("error") or "no index")
        )
    try:
        entry = marketplace_index.resolve_version(
            index, name, version, ephe_version=__version__
        )
    except marketplace_index.IndexError as exc:
        return _audit_refusal(name, _refused(exc.code, exc.detail or str(exc)))
    if (
        entry["source"]["sha256"] != plan_data["sha256"]
        or entry["source"]["url"] != plan_data["url"]
        or entry["plugin"].get("trust") != plan_data["trust"]
    ):
        return _audit_refusal(
            name, _refused("index_changed", "the index changed since the plan was made")
        )
    if _installed_version(name) != str(plan_data.get("installed_version") or ""):
        return _audit_refusal(
            name, _refused("state_changed", "the installed version changed since the plan")
        )

    old_manifest = _installed_manifest(name)
    approved_delta = str(plan_data.get("approved_delta") or "")
    inspect = _make_inspect(
        name=name,
        version=version,
        old_manifest=old_manifest,
        approved_delta=approved_delta,
    )
    signature = plan_data.get("signature")
    listing_entry = {
        "name": name,
        "version": version,
        "url": plan_data["url"],
        "sha256": plan_data["sha256"],
        "trust": "local" if not isinstance(signature, dict) else plan_data["trust"],
    }
    if isinstance(signature, dict):
        listing_entry["signature"] = signature
    if source["kind"] in {"local", "bundled"}:
        fetcher = _local_fetcher(Path(source["url"]))
    else:
        fetcher = _https_fetcher(source["url"])
    result = plugin_market.install_from_marketplace(
        name,
        marketplace={"plugins": [listing_entry]},
        fetcher=fetcher,
        allow_local_trust=bool(plan_data.get("allow_local_trust")),
        inspect=inspect,
    )
    if result.get("status") == "refused" and str(result.get("error", "")).startswith(
        "permission_delta:"
    ):
        payload = str(result["error"]).split(":", 1)[1].strip()
        try:
            delta = json.loads(payload)
        except ValueError:
            delta = {}
        # The install wrapper already wrote this refusal; a second line here
        # would make one refusal look like two.
        if old_manifest is None:
            return {
                "status": "permission_review",
                "code": "permission_delta",
                "error": "the artifact adds permissions the plan did not approve",
                "delta": delta,
                "name": name,
                "version": version,
            }
        return {
            "status": "refused",
            "code": "permission_delta",
            "error": "the artifact adds permissions the plan did not approve",
            "delta": delta,
        }
    if result.get("status") == "extracted":
        _invalidate()
        lock_error = _write_lock()
        _audit(
            name,
            "updated" if old_manifest is not None else "installed",
            f"version={version} trust={result.get('trust')}",
        )
        result["permissions"] = _permissions(
            (_installed_manifest(name) or {}).get("permissions")
        )
        if old_manifest is None:
            try:
                from core import plugin_runtime

                plugin_runtime.lifecycle().set_enabled(
                    name, True, actor="marketplace", reason="install"
                )
                result["enabled"] = True
            except Exception:  # noqa: BLE001 — installed is still a success
                result["enabled"] = False
                result["activation_error"] = "activation_failed"
        if lock_error:
            result["lockfile_error"] = lock_error
    return result


def rollback(name: str) -> dict[str, Any]:
    result = plugin_versions.rollback_plugin(name)
    if result.get("status") == "rolled_back":
        _invalidate()
    else:
        _audit_refusal(name, result)
    return result


def remove(name: str, *, delete_data: bool = False) -> dict[str, Any]:
    from core import plugin_runtime
    from core.plugin_lifecycle import LifecycleError

    try:
        snapshot = plugin_runtime.lifecycle().snapshot(name)
        if snapshot.enabled:
            plugin_runtime.lifecycle().set_enabled(
                name, False, actor="marketplace", reason="remove"
            )
    except LifecycleError as exc:
        return _audit_refusal(name, _refused(exc.code, exc.detail))
    result = plugin_versions.remove_plugin(name, delete_data=delete_data)
    if result.get("status") == "removed":
        _invalidate()
    else:
        _audit_refusal(name, result)
    return result


from core.marketplace_inventory import (
    installed,
    updates,
)

__all__ = [
    "ServiceError",
    "install",
    "installed",
    "permission_delta",
    "plan",
    "remove",
    "rollback",
    "updates",
]


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
