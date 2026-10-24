"""What happens to the version that was already installed.

The installer verifies a new artifact before it reaches a loadable path. This
module keeps the old version available until the new one commits, puts it back
on rollback with the switch state it had, and removes a package only when no
enabled dependent and no enabled switch stand in the way.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from core import plugin_manifest, plugin_signing
from core.plugin_lockfile import (
    LOCK_FILENAME,
    build_lockfile,
    trust_class_for,
    write_lockfile,
)
from core.plugin_store import (
    REGISTRY_FILENAME,
    _write_registry,
    config_root,
    load_registry,
)

STATE_SUFFIX = ".json"
DATA_DIRNAME = "plugin-data"
BACKUP_PREFIX = ".previous-"
logger = logging.getLogger(__name__)


class VersionError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def plugins_root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else config_root() / plugin_manifest.PLUGINS_DIRNAME


def _sidecar(plugin_dir: Path) -> Path:
    return plugin_dir.parent / f"{BACKUP_PREFIX}{plugin_dir.name}{STATE_SUFFIX}"


def _read_manifest(directory: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(
            (directory / plugin_manifest.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_sidecar(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(body, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _registry_enabled(name: str) -> bool | None:
    for item in load_registry():
        if str(item.get("name")) == name:
            return item.get("enabled") is not False
    return None


def _effective_enabled(name: str) -> bool | None:
    try:
        from core import plugin_runtime

        lifecycle = plugin_runtime.lifecycle()
        if lifecycle.has_committed_state(name):
            return lifecycle.snapshot(name).enabled
    except Exception:
        logger.debug("lifecycle switch state read failed", exc_info=True)
    return _registry_enabled(name)


def _set_registry_enabled(name: str, enabled: bool) -> None:
    try:
        from core import plugin_runtime

        plugin_runtime.lifecycle().set_enabled(
            name, bool(enabled), actor="marketplace", reason="rollback"
        )
    except Exception:
        logger.warning("lifecycle switch write failed; registry updated", exc_info=True)
    items = load_registry()
    found = False
    for item in items:
        if str(item.get("name")) == name:
            item["enabled"] = bool(enabled)
            found = True
    if not found:
        items.append({"name": name, "enabled": bool(enabled)})
    _write_registry(items, config_root() / REGISTRY_FILENAME)


def _drop_registry(name: str) -> None:
    items = [item for item in load_registry() if str(item.get("name")) != name]
    _write_registry(items, config_root() / REGISTRY_FILENAME)


def _write_lockfile(root: Path) -> str:
    try:
        write_lockfile(config_root() / LOCK_FILENAME, build_lockfile(root))
        return ""
    except Exception as exc:  # noqa: BLE001 — the package change already happened
        return str(exc)[:200]


def _audit(kind: str, name: str, decision: str, detail: str) -> None:
    try:
        from core.audit_log import audit_event

        audit_event(kind, tool=name, decision=decision, status="ok", detail=detail)
    except Exception:  # noqa: BLE001 — an audit sink never undoes a package change
        return


def backup_current(plugin_dir: Path, *, trust_class: str | None = None) -> Path | None:
    """Move the installed directory to its one-slot backup and remember its switch.

    The sidecar also records the key class the version was installed under, so
    a later rollback verifies against that class instead of every trusted key.
    """
    plugin_dir = Path(plugin_dir)
    if not plugin_dir.is_dir():
        return None
    name = plugin_dir.name
    previous = plugin_dir.parent / f"{BACKUP_PREFIX}{name}"
    sidecar = _sidecar(plugin_dir)
    manifest = _read_manifest(plugin_dir)
    version = str(manifest.get("version") or "") if manifest else ""
    if previous.exists():
        shutil.rmtree(previous, ignore_errors=True)
    _write_sidecar(
        sidecar,
        {
            "name": name,
            "version": version,
            "enabled": _effective_enabled(name),
            "trust_class": trust_class or trust_class_for(name, plugin_dir),
        },
    )
    try:
        plugin_dir.rename(previous)
    except OSError:
        sidecar.unlink(missing_ok=True)
        return None
    return previous


def restore_backup(backup: Path | None, plugin_dir: Path) -> None:
    """Put the backup back after a failed commit, replacing any partial directory."""
    if backup is None or not Path(backup).is_dir():
        return
    target = Path(plugin_dir)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    Path(backup).rename(target)
    _sidecar(target).unlink(missing_ok=True)


def commit_backup(plugin_dir: Path) -> None:
    """The new version is committed; the backup and its state sidecar both stay.

    Deleting the sidecar here made the rollback read the class of the *new*
    version: the one record that says which key class the backup was installed
    under was removed at the only moment it is ever written.
    """


def _recorded_class(name: str, backup: Path, context: dict[str, Any]) -> str:
    recorded = str(context.get("trust_class") or "")
    if recorded in (plugin_signing.FIRST_PARTY, plugin_signing.USER):
        return recorded
    return trust_class_for(name, backup)


def rollback_plugin(name: str, *, root: Path | None = None) -> dict[str, Any]:
    installed_root = plugins_root(root)
    previous = installed_root / f"{BACKUP_PREFIX}{name}"
    sidecar = installed_root / f"{BACKUP_PREFIX}{name}{STATE_SUFFIX}"
    if not previous.is_dir():
        return {"status": "no_previous", "name": name}
    manifest = _read_manifest(previous)
    if manifest is None:
        return {"status": "invalid_backup", "name": name, "error": "no manifest in backup"}
    if str(manifest.get("name")) != name:
        return {"status": "invalid_backup", "name": name, "error": "name does not match"}

    context: dict[str, Any] = {}
    if sidecar.is_file():
        try:
            loaded = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            context = loaded

    signature = None
    rollback_class = ""
    sig_file = previous / plugin_manifest.SIG_FILENAME
    if sig_file.is_file():
        try:
            signature = json.loads(sig_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            signature = None
        if not isinstance(signature, dict):
            return {"status": "invalid_backup", "name": name, "error": "unreadable signature"}
        # The class the version was installed under, not every trusted key: a
        # first-party rollback must not be signed by a user key. A sidecar from
        # before TS-09 has no field and is migrated from source/trust.
        rollback_class = _recorded_class(name, previous, context)
        ok, reason = plugin_signing.verify_plugin_dir(
            previous,
            signature,
            trust_class=rollback_class,
            require_dir_name=False,
        )
        if not ok:
            return {"status": "invalid_backup", "name": name, "error": reason}

    final = installed_root / name
    temp = installed_root / f".rolledback-{name}-{os.getpid()}"
    try:
        if final.exists():
            final.rename(temp)
        previous.rename(final)
    except OSError as exc:
        if temp.exists() and not final.exists():
            temp.rename(final)
        return {"status": "rollback_failed", "name": name, "error": str(exc)}

    if temp.exists():
        shutil.rmtree(temp, ignore_errors=True)
    if isinstance(context.get("enabled"), bool):
        _set_registry_enabled(name, bool(context["enabled"]))
    if isinstance(signature, dict):
        try:
            plugin_signing.record_pin(
                name, signature, trust_class=rollback_class or None
            )
        except OSError:
            pass
    else:
        plugin_signing.clear_pin(name)
    sidecar.unlink(missing_ok=True)
    lock_error = _write_lockfile(installed_root)
    version = str(manifest.get("version") or "")
    _audit("plugin_rollback", name, "rolled_back", f"version={version}")
    result: dict[str, Any] = {
        "status": "rolled_back",
        "name": name,
        "version": version,
    }
    if lock_error:
        result["lockfile_error"] = lock_error
    return result


def _enabled_dependents(name: str, root: Path) -> list[str]:
    out: list[str] = []
    for entry in plugin_manifest.scan_plugins(root):
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        dependent = str(manifest.get("name") or "")
        if not dependent or dependent == name:
            continue
        dependencies = manifest.get("dependencies") or []
        if name not in [str(dep) for dep in dependencies]:
            continue
        if _effective_enabled(dependent) is not False:
            out.append(dependent)
    return sorted(set(out))


def remove_plugin(
    name: str, *, root: Path | None = None, delete_data: bool = False
) -> dict[str, Any]:
    installed_root = plugins_root(root)
    final = installed_root / name
    if not final.is_dir():
        return {"status": "not_installed", "name": name}
    dependents = _enabled_dependents(name, installed_root)
    if dependents:
        return {
            "status": "dependents_enabled",
            "name": name,
            "dependents": dependents,
        }
    if _effective_enabled(name) is not False:
        return {"status": "plugin_enabled", "name": name}

    shutil.rmtree(final, ignore_errors=True)
    previous = installed_root / f"{BACKUP_PREFIX}{name}"
    if previous.exists():
        shutil.rmtree(previous, ignore_errors=True)
    (installed_root / f"{BACKUP_PREFIX}{name}{STATE_SUFFIX}").unlink(missing_ok=True)
    plugin_signing.clear_pin(name)
    _drop_registry(name)
    data_removed = False
    if delete_data:
        data = config_root() / DATA_DIRNAME / name
        if data.exists():
            shutil.rmtree(data, ignore_errors=True)
            data_removed = True
    lock_error = _write_lockfile(installed_root)
    _audit(
        "plugin_remove",
        name,
        "removed",
        f"delete_data={str(bool(delete_data)).lower()}",
    )
    result: dict[str, Any] = {
        "status": "removed",
        "name": name,
        "data_removed": data_removed,
    }
    if lock_error:
        result["lockfile_error"] = lock_error
    return result
