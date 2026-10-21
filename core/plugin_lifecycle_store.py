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
        if reconciled and not self._unproven:
            with contextlib.suppress(LifecycleError):
                self._persist()
        self._seen_signature = self._file_signature()

    def _persist(self) -> None:
        if self._path is None:
            return
        body = json.dumps(self._data, ensure_ascii=False, indent=2)
        parent = self._path.parent
        tmp = self._path.with_name(
            f".{self._path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            parent.mkdir(parents=True, exist_ok=True)
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
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise LifecycleError("state_write_failed", 500, str(exc)) from exc
