"""Marketplace service: plan one install, then commit that exact artifact.

A plan pins version, hash, trust and the permission delta the user approves.
The commit re-reads the source, refuses a changed index, and passes an inspect
hook into staging so the bytes must still match the plan before they replace
the running version.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import shutil
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
from core.plugin_lockfile import LOCK_FILENAME, rebuild_lockfile
from core.plugin_store import config_root

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
ARTIFACT_TIMEOUT_S = 30

#: The inspect hook's refusal for a high-severity static finding. The installer removes
#: the staging directory on any inspect refusal, so the value names the refusal back to
#: the caller without a second table of codes.
STATIC_CHECK_REFUSAL = "static_check_failed"


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
    static_check: bool = True,
    verdict_out: dict[str, Any] | None = None,
) -> Callable[[Path, dict[str, Any]], str | None]:
    """The plan's checks over the *staged* candidate, before it is committed.

    F2 (QA 2026-11-10): the static verification ran after the installer had already
    moved the artifact into the plugins root, so a refusal left the directory (and the
    inventory row) behind. It belongs here with the other checks: the installer drops
    the staging directory on a refusal, which is the "quarantined (directory removed)"
    `docs/PLUGINS.md` promises — and an update that is refused leaves the installed
    version untouched instead of replacing it with one that was then found unsafe.
    """

    def inspect(candidate: Path, manifest: dict[str, Any]) -> str | None:
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
        if static_check:
            from core.marketplace_verify import verify_artifact, write_verdict

            verdict = verify_artifact(candidate)
            if verdict_out is not None:
                verdict_out.clear()
                verdict_out.update(verdict)
            if verdict["verdict"] == "refused":
                return STATIC_CHECK_REFUSAL
            # Written into the staged directory, so the verdict file lands beside the
            # artifact the accept path commits — the installed row keeps showing it.
            write_verdict(candidate, verdict)
        return None

    return inspect


def _invalidate() -> None:
    from core import plugin_runtime
    from core.skills import invalidate_skill_cache

    invalidate_skill_cache()
    plugin_runtime.invalidate_ownership_cache()


def _write_lock() -> str:
    try:
        rebuild_lockfile(config_root() / LOCK_FILENAME)
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
    # A bundled pack ships with this repository and was reviewed with it; the scan
    # exists for artifacts that arrive from outside. Our own agent instructions
    # legitimately say "system prompt", and refusing them would be the scanner
    # reading its own product as an attack.
    # One gate for every artifact. The trust class used to skip bundled packs because the scan
    # read their required "## System Prompt" heading as an attack; the check reads directive
    # phrases now, so a first-party bundle passes on its text rather than on its name - and a
    # bundled bundle that smuggles an instruction is refused like any other (F1, QA 2026-11-10).
    static_check = True
    verdict_holder: dict[str, Any] = {}
    inspect = _make_inspect(
        name=name,
        version=version,
        old_manifest=old_manifest,
        approved_delta=approved_delta,
        static_check=static_check,
        verdict_out=verdict_holder,
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
    if result.get("status") == "refused" and str(result.get("error", "")) == STATIC_CHECK_REFUSAL:
        # The check ran in staging and the installer removed that directory again, so
        # this refusal left the plugins root exactly as it found it: nothing for a
        # first install, the installed version for a refused update. F2 (QA
        # 2026-11-10) was the opposite: a refused artifact on disk, listed as
        # installed with `verification: "refused"`.
        _audit(name, "refused", STATIC_CHECK_REFUSAL)
        return {
            "status": "refused",
            "code": STATIC_CHECK_REFUSAL,
            "error": "the artifact's text carries instruction or download shapes",
            "findings": verdict_holder.get("findings", []),
            "verification": verdict_holder,
            "quarantined": True,
        }
    if result.get("status") == "extracted":
        if verdict_holder:
            result["verification"] = dict(verdict_holder)
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
            # The switch a fresh install lands on is `plugins.plugin_autorun` (E5), the same
            # value the registry row carries - not "on". A fresh install used to answer
            # enabled:true while the registry said false, and the two disagreed everywhere.
            from core import plugin_switch_policy
            from core.settings_schema import deep_bool

            land_on = deep_bool("plugins.plugin_autorun") and not plugin_switch_policy.read_only()
            try:
                from core import plugin_runtime

                plugin_runtime.lifecycle().set_enabled(
                    name, land_on, actor="marketplace", reason="install"
                )
                result["enabled"] = land_on
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


def _plugin_directory(name: str) -> Path | None:
    """The installed folder for one id, or None when the id is not a slug."""
    try:
        return plugin_versions.plugin_dir(plugin_versions.plugins_root(), str(name))
    except ValueError:
        return None


def _state_home(name: str) -> Path | None:
    """The bundle's own state folder (`mcp/homes/plugin_<id>`), or None if unprovable."""
    from core import plugin_state

    try:
        return plugin_state.state_home(str(name))
    except ValueError:
        return None


def _legacy_data_directory(name: str) -> Path:
    return config_root() / plugin_versions.DATA_DIRNAME / str(name)


def _data_present(name: str) -> bool:
    """Whether any folder this product hands a bundle for storage is still there."""
    state_home = _state_home(name)
    return _legacy_data_directory(name).is_dir() or (
        state_home is not None and state_home.is_dir()
    )


def _creator_draft(name: str) -> Path:
    from core.tools.creator_tools import STAGING_DIRNAME

    return config_root() / STAGING_DIRNAME / "plugins" / str(name)


def _bundled_directory(name: str) -> Path | None:
    """The first-party folder for one id, which a removal never deletes."""
    from core import plugin_manifest
    from core.plugin_store import PLUGIN_NAME_RE

    if not PLUGIN_NAME_RE.match(str(name)):
        return None
    return plugin_manifest.builtin_plugins_root() / str(name)


def removal_facts(name: str) -> dict[str, Any]:
    """What a removal finds on this device, without removing anything.

    One reader for the preview and the commit: the CLI asks before it writes and the
    route answers with the same facts afterwards, so a preview cannot promise a
    cleanup the product path does not perform.
    """
    from core import plugin_runtime
    from core.plugin_lifecycle import SCOPES
    from core.plugin_store import load_registry

    name = str(name)
    directory = _plugin_directory(name)
    mounts: dict[str, Any] = {}
    surfaces: dict[str, Any] = {}
    committed = False
    lifecycle = None
    try:
        lifecycle = plugin_runtime.lifecycle()
    except Exception:  # noqa: BLE001 — the preview still answers the disk facts
        lifecycle = None
    if lifecycle is not None:
        try:
            mounts = lifecycle.mount_records()
        except Exception:  # noqa: BLE001
            mounts = {}
        try:
            surfaces = lifecycle.surface_hosts()
        except Exception:  # noqa: BLE001
            surfaces = {}
        committed = any(
            lifecycle.has_committed_state(name, scope) for scope in SCOPES
        )
    bundled = _bundled_directory(name)
    return {
        "bundle": directory is not None and directory.is_dir(),
        "bundled": bundled is not None and bundled.is_dir(),
        "registry": any(
            str(item.get("name")) == name for item in load_registry()
        ),
        "mount": name in mounts,
        "state_record": committed,
        "surface_record": name in surfaces,
        "data": _data_present(name),
        "creator_draft": _creator_draft(name).is_dir(),
    }


def _switch_now(name: str) -> tuple[str, bool]:
    """The current switch word and position, falling back to the registry."""
    from core import plugin_runtime

    try:
        snapshot = plugin_runtime.lifecycle().snapshot(name)
        return snapshot.state.value, bool(snapshot.enabled)
    except Exception:  # noqa: BLE001 — a folder the process has not scanned yet
        from core.plugin_store import load_registry

        enabled = next(
            (
                item.get("enabled") is not False
                for item in load_registry()
                if str(item.get("name")) == name
            ),
            True,
        )
        return ("enabled" if enabled else "disabled"), enabled


def _deactivate(name: str) -> bool:
    """Switch the bundle off in every scope that carries a committed position.

    A bundle that never had a committed row reads as the product default (on), so the
    user scope is written in that case as well. Returns whether it now reads off.
    """
    from core import plugin_runtime
    from core.plugin_lifecycle import SCOPES, LifecycleError

    lifecycle = plugin_runtime.lifecycle()
    wrote = False
    for scope in SCOPES:
        try:
            if not lifecycle.has_committed_state(name, scope):
                continue
            lifecycle.set_enabled(
                name, False, scope=scope, actor="marketplace", reason="remove"
            )
            wrote = True
        except LifecycleError:
            continue
    if not wrote:
        lifecycle.set_enabled(
            name, False, actor="marketplace", reason="remove"
        )
    return not plugin_runtime.lifecycle().effective(name).enabled


def remove(
    name: str, *, delete_data: bool = False, force: bool = False
) -> dict[str, Any]:
    """Remove one installed bundle through the one product path.

    An enabled bundle is refused with ``still_active`` and the state it is in; the
    caller decides whether to switch it off first. ``force=True`` is that decision:
    the switch is turned off through the lifecycle, then the folder leaves. The
    answer names what was removed and what stayed, because a removal that reports
    "removed" while a state row, a mount record or a data folder survives is the
    scene the reader later trips over.
    """
    from core import plugin_runtime
    from core.plugin_lifecycle import LifecycleError

    name = str(name)
    facts = removal_facts(name)
    if not facts["bundle"]:
        if facts["bundled"]:
            return {"status": "bundled", "name": name}
        return {"status": "not_installed", "name": name}
    version = _installed_version(name)
    state, enabled = _switch_now(name)
    if enabled and not force:
        _audit_refusal(
            name,
            {"status": "still_active", "state": state, "version": version},
        )
        return {
            "status": "still_active",
            "name": name,
            "version": version,
            "state": state,
            "enabled": True,
        }
    result = plugin_versions.remove_plugin(name, delete_data=False)
    deactivated = False
    if result.get("status") == "plugin_enabled":
        if not force:
            _audit_refusal(name, result)
            return {
                "status": "still_active",
                "name": name,
                "version": version,
                "state": state,
                "enabled": True,
            }
        try:
            deactivated = _deactivate(name)
        except LifecycleError as exc:
            return _audit_refusal(name, _refused(exc.code, exc.detail))
        if not deactivated:
            _audit_refusal(name, {"status": "still_active", "state": state})
            return {
                "status": "still_active",
                "name": name,
                "version": version,
                "state": state,
                "enabled": True,
            }
        result = plugin_versions.remove_plugin(name, delete_data=False)
    if result.get("status") != "removed":
        _audit_refusal(name, result)
        return result
    mount_removed = False
    try:
        unmounted = plugin_runtime.lifecycle().unmount(
            name, actor="marketplace", reason="remove"
        )
        mount_removed = facts["mount"] or bool(unmounted.removed)
    except Exception:  # noqa: BLE001 — the folder is gone; a stale record is reported
        mount_removed = False
    if delete_data:
        for folder in (_legacy_data_directory(name), _state_home(name)):
            if folder is not None and folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)
    data_removed = bool(delete_data and facts["data"] and not _data_present(name))
    _invalidate()
    # `removed` says what the removal took (facts read before it ran); `remains` says what
    # is still there, so it is read again after folder, rows and mount are gone.
    after = removal_facts(name)
    lock_error = str(result.get("lockfile_error") or "")
    answer: dict[str, Any] = {
        "status": "removed",
        "name": name,
        "version": version,
        "state": state,
        "deactivated": deactivated,
        "data_removed": data_removed,
        "removed": {
            "bundle": True,
            "registry": bool(facts["registry"]),
            "mount": bool(mount_removed),
            "data": bool(data_removed),
        },
        "remains": {
            "data": bool(after["data"] and not data_removed),
            "state_record": bool(after["state_record"]),
            "surface_record": bool(after["surface_record"]),
            "creator_draft": bool(after["creator_draft"]),
        },
    }
    if lock_error:
        answer["lockfile_error"] = lock_error
    return answer


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
    "removal_facts",
    "rollback",
    "updates",
]
