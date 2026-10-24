"""Atomic state persistence for the plugin lifecycle."""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from core.plugin_lifecycle_types import (
    LifecycleError,
    PluginState,
    SCHEMA_VERSION,
    SCOPES,
)

_COMMITTED_STATES = frozenset(
    {
        PluginState.ENABLED.value,
        PluginState.DISABLED.value,
        PluginState.FAILED.value,
    }
)


class LifecyclePersistence:
    _path: Path | None
    _data: dict[str, Any]
    _unproven: bool
    _seen_signature: tuple[int, int] | None

    def _file_signature(self) -> tuple[int, int] | None:
        if self._path is None:
            return None
        try:
            stat = self._path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _has_external_pending(self) -> bool:
        if self._path is None:
            return False
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        plugins = raw.get("plugins") if isinstance(raw, dict) else None
        if not isinstance(plugins, dict):
            return False
        for scopes in plugins.values():
            if not isinstance(scopes, dict):
                continue
            for entry in scopes.values():
                if isinstance(entry, dict) and "pending" in entry:
                    return True
        return False

    def reload_if_changed(self) -> None:
        """Picks up a committed state written by another instance or process.

        In-memory pending flights and a file with a pending intent are left
        alone: those are live operations, not a crash leftover to reconcile.
        """
        with self._lock:
            if self._path is None or self._pending:
                return
            if self._file_signature() == self._seen_signature:
                return
            if self._has_external_pending():
                return
            self._data = {
                "schema": SCHEMA_VERSION,
                "pause_all": False,
                "legacy_imported": False,
                "notices": [],
                "plugins": {},
                "idempotency": {},
            }
            self._unproven = False
            self._load()

    def _load(self) -> None:
        """Reads the state file fail-closed.

        A structural violation marks the whole state unproven: every switch reads
        off until a successful write replaces the damaged file. Valid entries stay
        in memory so a repair write does not drop them; invalid parts are never
        loaded. A non-boolean ``pause_all`` stays paused instead of silently
        opening the global brake.
        """
        self._seen_signature = self._file_signature()
        if self._path is None or not self._path.exists():
            return
        reconciled: list[dict[str, Any]] = []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._unproven = True
            return
        if not isinstance(raw, dict):
            self._unproven = True
            return
        if "schema" in raw and raw.get("schema") != SCHEMA_VERSION:
            self._unproven = True
        if "plugins" in raw:
            plugins = raw["plugins"]
            if not isinstance(plugins, dict):
                self._unproven = True
            else:
                for name, scopes in plugins.items():
                    if not isinstance(scopes, dict):
                        self._unproven = True
                        continue
                    for scope_value, entry in scopes.items():
                        if scope_value not in SCOPES:
                            self._unproven = True
                            continue
                        if not isinstance(entry, dict):
                            self._unproven = True
                            continue
                        committed = entry.get("committed")
                        if committed is not None and committed not in _COMMITTED_STATES:
                            self._unproven = True
                            continue
                        pending = entry.get("pending")
                        if pending is not None and not isinstance(pending, dict):
                            self._unproven = True
                            continue
                        if isinstance(pending, dict):
                            reconciled.append(
                                {
                                    "plugin": str(name),
                                    "scope": scope_value,
                                    "pending": pending,
                                    "committed": str(committed or "disabled"),
                                }
                            )
                            entry.pop("pending", None)
                        self._data["plugins"].setdefault(str(name), {})[scope_value] = (
                            entry
                        )
        if "pause_all" in raw:
            if isinstance(raw["pause_all"], bool):
                self._data["pause_all"] = raw["pause_all"]
            else:
                # The file asked for a pause in a shape we cannot read. Pausing is
                # the closed side of that choice.
                self._data["pause_all"] = True
                self._unproven = True
        if "legacy_imported" in raw:
            if raw["legacy_imported"] is True:
                self._data["legacy_imported"] = True
            elif raw["legacy_imported"] is not False:
                self._unproven = True
        if isinstance(raw.get("notices"), list):
            self._data["notices"] = [
                dict(notice) for notice in raw["notices"] if isinstance(notice, dict)
            ]
        if "idempotency" in raw:
            idempotency = raw["idempotency"]
            if not isinstance(idempotency, dict):
                self._unproven = True
            else:
                for key, cached in idempotency.items():
                    if (
                        isinstance(key, str)
                        and isinstance(cached, dict)
                        and isinstance(cached.get("request"), dict)
                        and isinstance(cached.get("response"), dict)
                    ):
                        self._data["idempotency"][key] = cached
                    else:
                        self._unproven = True
        for item in reconciled:
            self._audit_entry(
                action="reconcile",
                plugin=item["plugin"],
                scope=item["scope"],
                actor="system",
                previous_state=str(item["pending"].get("state") or "pending"),
                requested_state="enabled"
                if item["pending"].get("requested_enabled")
                else "disabled",
                state=item["committed"],
                version=str(item["pending"].get("version") or ""),
                duration_ms=0,
                reason="pending intent discarded at startup",
                status="committed",
            )
        self._loaded_data = json.loads(json.dumps(self._data))
        if reconciled and not self._unproven:
            with contextlib.suppress(LifecycleError):
                self._persist()
        self._loaded_data = json.loads(json.dumps(self._data))
        self._seen_signature = self._file_signature()

    def _quarantine_unproven(
        self, keep: tuple[str, str] | None
    ) -> tuple[dict[str, Any], list[tuple[str, str]]]:
        """A copy of the state with every enabled intent reset, except `keep`.

        The damaged file is untrusted as a whole; a valid-looking enabled entry
        is exactly what T-28 must not resurrect. The one entry the caller is
        explicitly mutating now (`keep`) carries the user's current intent and
        is written as requested.
        """
        data = json.loads(json.dumps(self._data))
        repaired: list[tuple[str, str]] = []
        plugins = data.get("plugins")
        if isinstance(plugins, dict):
            for name, scopes in plugins.items():
                if not isinstance(scopes, dict):
                    continue
                for scope, entry in scopes.items():
                    if not isinstance(entry, dict):
                        continue
                    if keep is not None and keep == (str(name), str(scope)):
                        continue
                    if entry.get("committed") == PluginState.ENABLED.value:
                        entry["committed"] = PluginState.DISABLED.value
                        repaired.append((str(name), str(scope)))
        return data, repaired

    @contextlib.contextmanager
    def _state_lock(self):
        """Cross-process serialisation of the read-merge-write step (POSIX)."""
        if self._path is None:
            yield
            return
        lock_path = self._path.with_name(self._path.name + ".lock")
        handle = None
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(lock_path, "a+", encoding="utf-8")
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            yield
        finally:
            if handle is not None:
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
                handle.close()

    def _read_disk_state(self) -> dict[str, Any] | None:
        if self._path is None:
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def _merge_for_write(
        self, disk: dict[str, Any] | None, local: dict[str, Any]
    ) -> dict[str, Any]:
        """Applies this instance's changes onto the file another instance wrote.

        A whole-document rewrite loses the other writer's plugin; the loaded
        snapshot tells us which entries this instance actually changed. Only
        those are applied, everything else stays what is on disk now.
        """
        if disk is None:
            return json.loads(json.dumps(local))
        merged = json.loads(json.dumps(disk))
        merged["schema"] = SCHEMA_VERSION
        merged.setdefault("pause_all", False)
        merged.setdefault("legacy_imported", False)
        merged.setdefault("notices", [])
        merged.setdefault("idempotency", {})
        plugins = merged.get("plugins")
        if not isinstance(plugins, dict):
            plugins = {}
            merged["plugins"] = plugins
        loaded = getattr(self, "_loaded_data", {})
        loaded_plugins = loaded.get("plugins") if isinstance(loaded, dict) else {}
        if not isinstance(loaded_plugins, dict):
            loaded_plugins = {}
        local_plugins = local.get("plugins") if isinstance(local, dict) else {}
        if isinstance(local_plugins, dict):
            for name, scopes in local_plugins.items():
                if not isinstance(scopes, dict):
                    continue
                loaded_scopes = loaded_plugins.get(name)
                if not isinstance(loaded_scopes, dict):
                    loaded_scopes = {}
                for scope, entry in scopes.items():
                    if loaded_scopes.get(scope) != entry:
                        plugins.setdefault(str(name), {})[str(scope)] = entry
        for key in ("pause_all", "legacy_imported"):
            if local.get(key) != loaded.get(key):
                merged[key] = local.get(key)
        local_notices = local.get("notices") if isinstance(local, dict) else []
        if isinstance(local_notices, list) and local_notices != loaded.get("notices"):
            notices = list(merged.get("notices") or [])
            for notice in local_notices:
                if notice not in notices:
                    notices.append(notice)
            merged["notices"] = notices
        local_idempotency = local.get("idempotency") if isinstance(local, dict) else {}
        loaded_idempotency = (
            loaded.get("idempotency") if isinstance(loaded, dict) else {}
        )
        if isinstance(local_idempotency, dict) and local_idempotency != loaded_idempotency:
            idempotency = dict(merged.get("idempotency") or {})
            for key, value in local_idempotency.items():
                if (
                    not isinstance(loaded_idempotency, dict)
                    or loaded_idempotency.get(key) != value
                ):
                    idempotency[key] = value
            merged["idempotency"] = idempotency
        return merged

    def _persist(self, *, keep: tuple[str, str] | None = None) -> None:
        if self._path is None:
            return
        data = self._data
        repaired: list[tuple[str, str]] = []
        if self._unproven:
            data, repaired = self._quarantine_unproven(keep)
        parent = self._path.parent
        tmp = self._path.with_name(
            f".{self._path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            parent.mkdir(parents=True, exist_ok=True)
            with self._state_lock():
                merged = self._merge_for_write(self._read_disk_state(), data)
                body = json.dumps(merged, ensure_ascii=False, indent=2)
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(body)
                        handle.flush()
                        os.fsync(handle.fileno())
                except BaseException:
                    tmp.unlink(missing_ok=True)
                    raise
                os.replace(tmp, self._path)
            os.chmod(self._path, 0o600)
            self._data = merged
            self._loaded_data = json.loads(json.dumps(merged))
            self._unproven = False
            self._seen_signature = self._file_signature()
            try:
                dir_fd = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
            audit = getattr(self, "_audit_entry", None)
            if audit is not None:
                for name, scope in repaired:
                    audit(
                        action="repair",
                        plugin=name,
                        scope=scope,
                        actor="system",
                        previous_state=PluginState.ENABLED.value,
                        requested_state=PluginState.DISABLED.value,
                        state=PluginState.DISABLED.value,
                        version=str(getattr(self, "_versions", {}).get(name, "")),
                        duration_ms=0,
                        reason="unproven state replaced; enabled intent quarantined",
                        status="committed",
                    )
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise LifecycleError("state_write_failed", 500, str(exc)) from exc
