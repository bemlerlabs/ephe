"""core/session_lifecycle.py — how long a session file lives, and what prunes it.

The store is a flat directory of JSON files in three namespaces: a registered
session (``0123abcd.json``, listed in ``registry.json``), the PWA mirror
(``pwa-<id>.json``, the durable copy behind ``GET /api/sessions/restore``) and
the REST mirror (``rest-<id>.json``, the server-side turn history of one REST
caller). Measured 2026-10-13 on this machine: the directory held 8061 JSON
files at 44 MB allocated while the registry listed 1749 and the restore path
reached 50. Nothing removed the rest — ``create_session`` writes a file per
call and the REST mirror writes a file per caller session id.

The policy is a retention count per namespace, newest first by mtime. A count
bounds the directory whatever writes it: a bench that adds hundreds of files in
a minute cannot outrun a count the way it outruns an age. Pruning is a
deliberate call from a user or an operator, never a side effect of a write; a
silent delete is itself the defect.

What the policy does not do, on purpose: it never removes ``registry.json``,
never removes the active session, never leaves the session directory (artifacts
live in ``artifact_store``'s own database and are untouched), and never touches
the browser's own copy of a mirrored session. A pruned mirror file is gone; the
PWA re-syncs what it still holds.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: The two namespaces a run can create without a human in the loop.
MIRROR_NAMESPACES: tuple[str, ...] = ("rest-", "pwa-")

#: Retention per namespace for an operator bound that names no numbers. The REST
#: mirror carries one file per caller session id, so it takes the larger cap;
#: restore serves at most 50 pwa files, so 200 already outlives the reader.
DEFAULT_KEEP: dict[str, int] = {"rest-": 500, "pwa-": 200}

REGISTRY_NAME = "registry.json"
LEGACY_NAME = "default.json"
#: A session id is a file stem: letters, digits, dash and underscore, no dot and
#: no separator, so a caller cannot name a path outside the store.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: Stems that name a store-level file rather than a session.
_RESERVED = frozenset({REGISTRY_NAME[:-5], LEGACY_NAME[:-5]})


def _sessions_dir() -> Path:
    """The live store path. Resolved per call, so a test or a moved profile retargets it."""
    import core.multi_session as ms

    return Path(ms.SESSIONS_DIR)


def namespace_of(session_id: str) -> str:
    """``rest-``, ``pwa-`` or ``""`` for a registered session."""
    for prefix in MIRROR_NAMESPACES:
        if session_id.startswith(prefix):
            return prefix
    return ""


def known_id(session_id: str) -> bool:
    """Whether the id may name a file in the store."""
    return bool(session_id) and session_id not in _RESERVED and bool(_ID_RE.match(session_id))


def session_files(sdir: Path | None = None) -> list[Path]:
    """Every session file, with the registry and the legacy file left out."""
    sdir = sdir or _sessions_dir()
    try:
        return [p for p in sdir.glob("*.json") if p.name not in (REGISTRY_NAME, LEGACY_NAME)]
    except OSError:
        return []


def read_registry(sdir: Path | None = None) -> dict:
    """The registry as a dict, an empty one when it is absent or unreadable."""
    sdir = sdir or _sessions_dir()
    try:
        data = json.loads((sdir / REGISTRY_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": []}
    if not isinstance(data, dict):
        return {"sessions": []}
    if not isinstance(data.get("sessions"), list):
        data["sessions"] = []
    return data


def save_registry(reg: dict, sdir: Path | None = None) -> None:
    """Write the registry through a temp file, the way the store's own writer does."""
    sdir = sdir or _sessions_dir()
    path = sdir / REGISTRY_NAME
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _stat(path: Path) -> tuple[float, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime, st.st_size)


def _by_mtime_desc(paths: list[Path]) -> list[Path]:
    def key(path: Path):
        seen = _stat(path)
        return seen[0] if seen else 0.0

    return sorted(paths, key=key, reverse=True)


def _stamp(paths: list[Path], *, oldest: bool) -> dict | None:
    ranked = _by_mtime_desc(paths)
    if not ranked:
        return None
    pick = ranked[-1] if oldest else ranked[0]
    seen = _stat(pick)
    if seen is None:
        return None
    return {
        "id": pick.stem,
        "namespace": namespace_of(pick.stem),
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(seen[0])),
    }


def store_stats() -> dict:
    """The holdings, counted honestly: per namespace, in bytes, and what a list reaches."""
    sdir = _sessions_dir()
    files = session_files(sdir)
    registry = read_registry(sdir)
    registered_ids = {str(e.get("id")) for e in registry.get("sessions", []) if e.get("id")}
    by_namespace = {ns: {"files": 0, "bytes": 0} for ns in (*MIRROR_NAMESPACES, "")}
    total_bytes = 0
    listed = 0
    for path in files:
        seen = _stat(path)
        if seen is None:
            continue
        namespace = namespace_of(path.stem)
        by_namespace[namespace]["files"] += 1
        by_namespace[namespace]["bytes"] += seen[1]
        total_bytes += seen[1]
        if path.stem in registered_ids:
            listed += 1
    return {
        "session_dir": str(sdir),
        "total": len(files),
        "bytes": total_bytes,
        "by_namespace": by_namespace,
        "registered_sessions": len(registered_ids),
        "listed_files": listed,
        "unreachable_by_list": len(files) - listed,
        "reachable_by_restore": min(by_namespace["pwa-"]["files"], 50),
        "oldest": _stamp(files, oldest=True),
        "newest": _stamp(files, oldest=False),
    }


def _freed_and_stem(path: Path) -> tuple[int, str]:
    seen = _stat(path)
    return (seen[1] if seen else 0, path.stem)


def _drop_from_index(session_id: str) -> None:
    """Best effort: the FTS index is a search cache, not the source of truth."""
    try:
        from core.session_search import drop_session

        drop_session(session_id)
    except Exception:
        logger.debug("session index drop skipped", exc_info=True)


def _count_by_namespace(sdir: Path) -> dict:
    counts = {ns: 0 for ns in (*MIRROR_NAMESPACES, "")}
    for path in session_files(sdir):
        counts[namespace_of(path.stem)] += 1
    return counts


def prune_store(keep: dict | None = None, *, namespaces=None, dry_run: bool = False) -> dict:
    """Retention by count: keep the newest ``keep[namespace]`` files, remove the rest.

    ``namespaces`` names the buckets to consider and defaults to every key of
    ``keep``, so pruning one namespace is one argument. The active session is
    reserved before the cap is filled: an operator bound may never delete the
    session the user is sitting in.
    """
    sdir = _sessions_dir()
    caps = dict(DEFAULT_KEEP if keep is None else keep)
    targets = list(caps) if namespaces is None else list(namespaces)
    active = str(read_registry(sdir).get("active_id") or "")
    buckets: dict[str, list[Path]] = {}
    for path in session_files(sdir):
        buckets.setdefault(namespace_of(path.stem), []).append(path)

    deleted: list[str] = []
    bytes_freed = 0
    kept = 0
    for namespace in targets:
        cap = max(0, int(caps.get(namespace, 0)))
        ordered = _by_mtime_desc(buckets.get(namespace, []))
        reserved = [p for p in ordered if p.stem == active]
        fills = [p for p in ordered if p.stem != active][: max(0, cap - len(reserved))]
        survivors = {p.name for p in (*reserved, *fills)}
        kept += len(survivors)
        for path in ordered:
            if path.name in survivors:
                continue
            freed, stem = _freed_and_stem(path)
            deleted.append(stem)
            bytes_freed += freed
            if dry_run:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            _drop_from_index(stem)

    if not dry_run and deleted:
        _forget_registry_rows(sdir, deleted)
    remaining = _count_by_namespace(sdir)
    if dry_run:
        # Nothing was unlinked, so report the state the run would leave behind.
        for stem in deleted:
            remaining[namespace_of(stem)] = max(0, remaining[namespace_of(stem)] - 1)
    return {
        "deleted": sorted(deleted),
        "kept": kept,
        "bytes_freed": bytes_freed,
        "remaining": remaining,
        "namespaces": targets,
        "dry_run": dry_run,
    }


def _forget_registry_rows(sdir: Path, deleted: list[str]) -> None:
    """A removed session leaves the registry with it, so list and disk agree."""
    names = set(deleted)
    registry = read_registry(sdir)
    entries = registry.get("sessions", [])
    remaining = [e for e in entries if str(e.get("id")) not in names]
    if len(remaining) != len(entries):
        registry["sessions"] = remaining
        save_registry(registry, sdir)


def remove_sessions(ids) -> dict:
    """Remove named sessions from the store: file, index row and registry entry.

    Ids that name no file, or a path that would leave the store, are reported in
    ``missing`` instead of raising, so a bulk caller sees the whole outcome.
    """
    sdir = _sessions_dir()
    deleted: list[str] = []
    missing: list[str] = []
    registry = None
    registry_changed = False
    for raw in ids:
        session_id = str(raw)
        if not known_id(session_id):
            missing.append(session_id)
            continue
        # known_id() already bars a separator; the real path plus the prefix check makes
        # the containment a property of the path itself (py/path-injection).
        root = os.path.realpath(sdir)
        target = os.path.realpath(os.path.join(root, f"{session_id}.json"))
        if not target.startswith(root + os.sep):
            missing.append(session_id)
            continue
        path = Path(target)
        if not path.exists():
            missing.append(session_id)
            continue
        try:
            path.unlink()
        except OSError:
            missing.append(session_id)
            continue
        deleted.append(session_id)
        _drop_from_index(session_id)
        if registry is None:
            registry = read_registry(sdir)
        entries = registry.get("sessions", [])
        remaining = [e for e in entries if str(e.get("id")) != session_id]
        if len(remaining) != len(entries):
            registry["sessions"] = remaining
            registry_changed = True
    if registry is not None and registry_changed:
        save_registry(registry, sdir)
    return {"deleted": deleted, "missing": missing}
