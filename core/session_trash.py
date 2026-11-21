"""core/session_trash.py — deleted sessions wait here, and come back.

`session_lifecycle.remove_sessions` unlinks. That is the right verb for an
operator prune and the wrong one for a reader who clicked "delete" in the
sidebar: one click should not be final before the click is even noticed. This
module moves a session aside instead — into `~/.ephe/trash/sessions/<stamp>/`,
the tree `core/persistence.py` already declares and `persistence.forget()`
clears with the rest of the device — beside the run folder `ephe doctor --fix`
already uses for quarantined debris. The run folder carries a `manifest.json`
that remembers the registry row verbatim, because a restore that rebuilds the
row from guesswork loses whatever the surface put into it.

Three rules set this module apart from a plain delete, all deliberate:

- Consent is kept while a session waits in the trash. The Creator consent row
  answers which permissions the reader ticked; a session that might come back
  tonight must not silently re-ask them. Emptying the trash is the one path
  that forgets, because only then is the session truly gone.
- The trash lives outside `~/.ephe/sessions/`, always. The lifecycle glob,
  the FTS indexer and the export route all read that directory whole; a
  trashed transcript left among the live ones would keep matching search and
  keep inflating the list.
- The trash is bounded. A store nothing empties grows until the disk notices —
  the shape `core/store_retention.py` measured on 2026-10-14 — so
  `purge_expired` forgets a run once it waited past the window the owner set.
  That is a named control, not a side effect: the window is a field in the
  ephemera section of the settings, and the sweep logs every run it takes.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.session_lifecycle import (
    _drop_from_index,
    _forget_grants,
    _stat,
    known_id,
    namespace_of,
    read_registry,
    save_registry,
)

logger = logging.getLogger(__name__)

#: The declared `trash` tree gains this subfolder for chat; the doctor row stays honest.
TRASH_SUBDIR = "sessions"

#: One run folder per trash call, stamped the way change_set, run_evidence and
#: artifact_store stamp theirs.
_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"

#: How long a run may wait before the sweep forgets it, when the owner left the
#: setting alone. 30 days is a month of undo — long enough to notice a click
#: was wrong, short enough that a folder nobody opens stops growing. The bounds
#: live in the settings register, the one place a control states its range.
DEFAULT_RETENTION_DAYS = 30

#: The sweep runs once at server start and then on this interval.
SWEEP_INTERVAL_S = 24 * 3600


def _sessions_dir() -> Path:
    import core.multi_session as ms

    return Path(ms.SESSIONS_DIR)


def trash_root() -> Path:
    """The live trash root, resolved per call so a test or moved profile retargets it."""
    from core.engine_config import config_root

    return config_root() / "trash" / TRASH_SUBDIR


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime(_STAMP_FORMAT)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _live_target(sdir: Path, session_id: str) -> Path | None:
    """The session file, only when the id names it inside the store.

    `known_id` already bars a separator; the realpath prefix makes containment a
    property of the path itself (py/path-injection), the same shape
    `remove_sessions` uses.
    """
    if not known_id(session_id):
        return None
    root = os.path.realpath(sdir)
    target = os.path.realpath(os.path.join(root, f"{session_id}.json"))
    if not target.startswith(root + os.sep):
        return None
    return Path(target)


def _registry_entry(registry: dict, session_id: str) -> dict | None:
    for entry in registry.get("sessions", []):
        if str(entry.get("id")) == session_id:
            return entry
    return None


def move_sessions_to_trash(ids, *, trashed_by: str = "user") -> dict:
    """Move named sessions from the live store into a run folder of the trash.

    Ids that name no file, or a path that would leave the store, come back in
    ``missing`` instead of raising, so a bulk caller sees the whole outcome.
    """
    sdir = _sessions_dir()
    trashed: list[str] = []
    missing: list[str] = []
    entries: list[dict] = []
    bytes_moved = 0
    registry = None
    registry_changed = False
    run_dir: Path | None = None
    trashed_at = _iso_now()
    for raw in ids:
        session_id = str(raw)
        path = _live_target(sdir, session_id)
        if path is None or not path.exists():
            missing.append(session_id)
            continue
        seen = _stat(path)
        if registry is None:
            registry = read_registry(sdir)
        row = _registry_entry(registry, session_id)
        run_dir = trash_root() / _now_stamp()
        run_dir.mkdir(parents=True, exist_ok=True)
        dest = run_dir / path.name
        step = 1
        while dest.exists():
            dest = run_dir / f"{path.stem}-{step}.json"
            step += 1
        try:
            shutil.move(str(path), str(dest))
        except OSError:
            logger.debug("session trash move refused for %s", session_id, exc_info=True)
            missing.append(session_id)
            continue
        trashed.append(session_id)
        bytes_moved += seen[1] if seen else 0
        entries.append(
            {
                "session_id": session_id,
                "namespace": namespace_of(session_id),
                "title": row.get("title") if row else None,
                "bytes": seen[1] if seen else 0,
                "trashed_by": trashed_by,
                "registry_entry": row,
            }
        )
        _drop_from_index(session_id)
        if row is not None:
            registry["sessions"] = [
                e for e in registry.get("sessions", []) if str(e.get("id")) != session_id
            ]
            registry_changed = True
    if registry is not None and registry_changed:
        save_registry(registry, sdir)
    run = ""
    if run_dir is not None and entries:
        run = run_dir.name
        _write_json(
            run_dir / "manifest.json",
            {"run": run, "trashed_at": trashed_at, "entries": entries},
        )
    return {
        "trashed": trashed,
        "missing": missing,
        "bytes_moved": bytes_moved,
        "run": run,
        "trashed_at": trashed_at if run else "",
    }


def _run_dirs() -> list[Path]:
    root = trash_root()
    try:
        return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
    except OSError:
        return []


def _manifest_of(run_dir: Path) -> dict | None:
    try:
        data = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _entry_file(run_dir: Path, entry: dict) -> Path | None:
    session_id = str(entry.get("session_id") or "")
    if not known_id(session_id):
        return None
    candidate = run_dir / f"{session_id}.json"
    if candidate.exists():
        return candidate
    # A collided move wrote `<id>-<step>.json`; the manifest stem still leads there.
    for path in sorted(run_dir.glob(f"{session_id}-*.json")):
        return path
    return None


def list_trash(limit: int = 100) -> dict:
    """Newest trashed sessions first, whole runs at a time."""
    entries: list[dict] = []
    total = 0
    for run_dir in _run_dirs():
        manifest = _manifest_of(run_dir)
        rows = (manifest or {}).get("entries")
        if not isinstance(rows, list):
            # A run whose manifest never landed still carries files worth listing.
            rows = [{"session_id": p.stem} for p in sorted(run_dir.glob("*.json"))]
        for row in rows:
            total += 1
            if len(entries) < limit:
                entries.append(
                    {
                        "session_id": str(row.get("session_id") or ""),
                        "namespace": row.get("namespace"),
                        "title": row.get("title"),
                        "bytes": row.get("bytes") or 0,
                        "trashed_at": (manifest or {}).get("trashed_at", ""),
                        "run": run_dir.name,
                    }
                )
    return {"entries": entries, "total": total}


def restore_session(session_id: str, run: str | None = None) -> dict:
    """Bring one trashed session back, newest trash first unless a run names it.

    A live file already under the id wins: two copies of one session is a
    corruption, so the second one is reported as a conflict and stays put.
    """
    sdir = _sessions_dir()
    live = _live_target(sdir, str(session_id))
    for run_dir in _run_dirs():
        if run is not None and run_dir.name != run:
            continue
        manifest = _manifest_of(run_dir)
        rows = (manifest or {}).get("entries")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if str(row.get("session_id")) != str(session_id):
                continue
            source = _entry_file(run_dir, row)
            if source is None:
                continue
            if live is not None and live.exists():
                return {"outcome": "conflict", "session_id": session_id, "run": run_dir.name}
            source.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(source), str(live))
            except OSError:
                logger.debug("session restore refused for %s", session_id, exc_info=True)
                continue
            remaining = [e for e in rows if e is not row]
            _write_json(run_dir / "manifest.json", {
                "run": run_dir.name,
                "trashed_at": manifest.get("trashed_at", ""),
                "entries": remaining,
            })
            registry = read_registry(sdir)
            row_entry = row.get("registry_entry")
            if isinstance(row_entry, dict) and _registry_entry(registry, session_id) is None:
                registry.setdefault("sessions", []).append(row_entry)
                save_registry(registry, sdir)
            return {"outcome": "restored", "session_id": session_id, "run": run_dir.name}
    return {"outcome": "missing", "session_id": session_id}


def _empty_run(run_dir: Path, *, dry_run: bool) -> tuple[list[str], int]:
    """Forget one run: its files, its consent rows, its index entries.

    Returns the session ids it took and the bytes it freed. A file that refuses
    to unlink leaves the run folder standing; the ids are still reported, the
    way an emptying always reported them.
    """
    manifest = _manifest_of(run_dir)
    rows = (manifest or {}).get("entries")
    if not isinstance(rows, list):
        rows = [{"session_id": p.stem} for p in sorted(run_dir.glob("*.json"))]
    deleted: list[str] = []
    bytes_freed = 0
    emptied = True
    for path in sorted(run_dir.glob("*.json")):
        seen = _stat(path)
        if not dry_run:
            try:
                path.unlink()
            except OSError:
                emptied = False
                continue
        bytes_freed += seen[1] if seen else 0
    if not dry_run and emptied:
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest_path.unlink()
            except OSError:
                pass
        if not any(run_dir.iterdir()):
            try:
                run_dir.rmdir()
            except OSError:
                pass
    for row in rows:
        session_id = str(row.get("session_id") or "")
        if not session_id:
            continue
        deleted.append(session_id)
        if not dry_run:
            _forget_grants(session_id)
            _drop_from_index(session_id)
    return deleted, bytes_freed


def empty_trash(*, dry_run: bool = False) -> dict:
    """Delete finally. The one path that forgets a waiting session's consent."""
    deleted: list[str] = []
    runs: list[str] = []
    bytes_freed = 0
    for run_dir in _run_dirs():
        took, freed = _empty_run(run_dir, dry_run=dry_run)
        deleted.extend(took)
        bytes_freed += freed
        runs.append(run_dir.name)
    return {
        "deleted": deleted,
        "runs": runs,
        "bytes_freed": bytes_freed,
        "dry_run": dry_run,
    }


def retention_days() -> int:
    """The owner's window, clamped to the register's bounds; 0 keeps everything.

    A missing or unreadable entry answers with the register default, never with
    zero: a settings file that will not parse must not empty anyone's trash.
    """
    from core.settings_schema import SCHEMA, deep_number

    try:
        value = int(deep_number("ephemera.trash_retention_days"))
        bounds = SCHEMA["ephemera.trash_retention_days"]
    except (KeyError, TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
    return max(int(bounds["min"]), min(int(bounds["max"]), value))


def _age_seconds(run_dir: Path, moment: datetime) -> float | None:
    """How long a run has waited. The manifest stamp is the record; a run whose
    manifest never landed ages by its folder."""
    stamp = (_manifest_of(run_dir) or {}).get("trashed_at")
    if isinstance(stamp, str) and stamp:
        try:
            trashed_at = datetime.fromisoformat(stamp)
        except ValueError:
            trashed_at = None
        if trashed_at is not None:
            if trashed_at.tzinfo is None:
                trashed_at = trashed_at.replace(tzinfo=timezone.utc)
            return (moment - trashed_at).total_seconds()
    try:
        wrote = datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc)
    except OSError:
        return None
    return (moment - wrote).total_seconds()


def purge_expired(*, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Forget every run that waited past the window the owner set.

    `dry_run` counts what would go without going, the way the emptying route
    lets a surface show its number before the click.
    """
    run_dirs = _run_dirs()
    days = retention_days()
    if days <= 0:
        return {
            "deleted": [],
            "runs": [],
            "bytes_freed": 0,
            "kept": len(run_dirs),
            "retention_days": 0,
            "dry_run": dry_run,
        }
    moment = now or datetime.now(timezone.utc)
    deleted: list[str] = []
    runs: list[str] = []
    bytes_freed = 0
    kept = 0
    for run_dir in run_dirs:
        age = _age_seconds(run_dir, moment)
        if age is None or age < days * 86400:
            kept += 1
            continue
        took, freed = _empty_run(run_dir, dry_run=dry_run)
        deleted.extend(took)
        bytes_freed += freed
        runs.append(run_dir.name)
        logger.info(
            "session trash: %s passed its %d-day window — %d session(s), %d byte(s)%s",
            run_dir.name,
            days,
            len(took),
            freed,
            ", counted not deleted" if dry_run else "",
        )
    return {
        "deleted": deleted,
        "runs": runs,
        "bytes_freed": bytes_freed,
        "kept": kept,
        "retention_days": days,
        "dry_run": dry_run,
    }
