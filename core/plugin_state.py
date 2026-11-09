"""A bundle's own state folder: where it is, what it holds, and the ceiling it holds it under.

Task #24 asked for state persistence inside validated roots with a cap. The roots landed in
`af06fefc` — read grants, honoured by both rails from one resolution function. This module is
the other half: the one place that says how many bytes a bundle keeps, what it may keep, and
what happens when the two meet.

The state folder is the directory the confined worker is handed as `state_dir`
(`core.mcp_sandbox.home_for("plugin_<id>")`). It is the only place a plugin writes, the OS
boundary enforces that, so the measurement here is not a guess about where a bundle puts
things: it walks the same tree the profile opened for the child.

Why a ceiling measured after the run rather than enforced during it. No portable per-directory
quota exists between the two rails this product runs on, and a child that discovered it could
not write would report that as a tool failure of its own. So the ceiling bites at the gate
before the next call, and the row after each run carries the numbers: a bundle that crossed is
seen on the trail, then refused on its next call with the bytes and the move named. A refusal
that arrives before the disk fills is the honest shape of a quota, and it is stated as one.

Nothing here quotes a host path into a message. Sizes are facts; directories are where a
machine layout leaks.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

#: The owner's decision, 2026-11-06: 512 MiB of kept state per bundle, unless the bundle's own
#: manifest says otherwise. A default is a policy, so it is named where a reader can find it.
DEFAULT_STATE_CAP_MB = 512

#: The ceiling a manifest may raise itself to. It exists because a declaration is read by a
#: security surface, and "any integer" is not a bound an installer can review.
MAX_STATE_CAP_MB = 16_384

MB = 1024 * 1024


def usage(state_dir: Path | str) -> tuple[int, int]:
    """Bytes and files under one directory, measured by walking it.

    A subtree the walk cannot enter is skipped rather than raised: a state folder is the
    child's own, and a file it left behind that this process may not stat is still not a
    reason to answer the reader with a traceback.
    """
    total = 0
    files = 0
    for base, _dirs, names in os.walk(str(state_dir), onerror=lambda error: None):
        for name in names:
            try:
                total += (Path(base) / name).stat().st_size
            except OSError:
                continue
            files += 1
    return total, files


def declared_cap_mb(plugin_id: str) -> int | None:
    """The ceiling one installed bundle declares, or None when it declares nothing.

    The manifest is the authority, and `core.plugin_manifest` has already refused a value that
    is not a positive integer within `MAX_STATE_CAP_MB`, so a bundle that loads has a number a
    reviewer could read on the Extensions page.
    """
    from core import plugin_manifest

    for entry in plugin_manifest.scan_plugins():
        manifest = entry["manifest"]
        if entry["error"] or not manifest or str(manifest.get("name")) != str(plugin_id):
            continue
        permissions = manifest.get("permissions")
        if not isinstance(permissions, dict):
            return None
        declared = permissions.get("state_cap_mb")
        return declared if isinstance(declared, int) and not isinstance(declared, bool) else None
    return None


def cap_bytes(plugin_id: str) -> int:
    """The ceiling one bundle's state folder lives under, in bytes.

    A declaration of nothing means the default, which is the point of a default: every bundle
    is bounded whether or not its author thought of the line.
    """
    declared = declared_cap_mb(plugin_id)
    return (declared if declared else DEFAULT_STATE_CAP_MB) * MB


def over(cap: int, used: int) -> bool:
    """Whether a bundle has spent its ceiling. Equal counts as spent: a cap that lets the byte
    past its own number is a cap that reports a different size than it enforces."""
    return used >= cap


#: How many stored files the Extensions row lists. The largest come first, so the move
#: the refusal names is one the reader can see. The count itself stays the full walk.
LISTED_FILES = 200

_PLUGIN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def state_home(plugin_id: str) -> Path:
    """The folder a confined worker is handed, resolved without creating it."""
    from core.mcp_sandbox import home_path

    return home_path(f"plugin_{plugin_id}")


def cap_bytes_from_manifest(manifest: dict | None) -> int:
    """The ceiling one manifest declares, or the default when the line is absent."""
    declared = None
    if isinstance(manifest, dict):
        permissions = manifest.get("permissions")
        if isinstance(permissions, dict):
            value = permissions.get("state_cap_mb")
            if isinstance(value, int) and not isinstance(value, bool):
                declared = value
    return (declared if declared else DEFAULT_STATE_CAP_MB) * MB


def summary_for(plugin_id: str, manifest: dict | None = None) -> dict:
    """Megabytes kept, megabytes allowed, and how many files. No path, no names."""
    home = state_home(plugin_id)
    used, files = usage(home) if home.is_dir() else (0, 0)
    cap = cap_bytes_from_manifest(manifest)
    return {
        "used_mb": round(used / MB),
        "cap_mb": cap // MB,
        "file_count": files,
    }


def is_addressable(plugin_id: str) -> bool:
    """Whether this id is a bundle the Extensions row can name.

    A slug that is neither installed nor in the catalog is not a reason to look
    at a home directory.
    """
    if not isinstance(plugin_id, str) or not _PLUGIN_ID.fullmatch(plugin_id):
        return False
    from core import plugin_manifest, plugin_store

    for entry in plugin_manifest.scan_plugins():
        manifest = entry.get("manifest") or {}
        if str(manifest.get("name") or "") == plugin_id:
            return True
    try:
        catalog = plugin_store.load_catalog()
    except Exception:
        return False
    for segment in ("public", "personal"):
        for entry in catalog.get(segment, []):
            if str(entry.get("name") or "") == plugin_id:
                return True
    return False


def _relative_name(name: object) -> str:
    """A stored-file name that stays inside the state folder, or ValueError."""
    if not isinstance(name, str) or not name or len(name) > 240:
        raise ValueError("name")
    if "\\" in name or "\x00" in name or name.startswith("/"):
        raise ValueError("name")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("name")
    return path.as_posix()


def _stored_entries(home: Path) -> list[dict]:
    """File names relative to the state folder, largest first. A link that leaves
    the folder is omitted. The absolute path stays out of the record."""
    if not home.is_dir():
        return []
    root = home.resolve()
    found: list[dict] = []
    for base, dirs, names in os.walk(home, onerror=lambda error: None):
        dirs[:] = [item for item in dirs if not (Path(base) / item).is_symlink()]
        for item in names:
            path = Path(base) / item
            try:
                rel = path.relative_to(home).as_posix()
            except ValueError:
                continue
            if any(part in {"", ".", ".."} for part in PurePosixPath(rel).parts):
                continue
            if path.is_symlink():
                try:
                    size = path.lstat().st_size
                except OSError:
                    continue
            else:
                try:
                    resolved = path.resolve()
                    size = path.stat().st_size
                except OSError:
                    continue
                if resolved != root and root not in resolved.parents:
                    continue
            found.append({"name": rel, "bytes": size})
    found.sort(key=lambda record: (-int(record["bytes"]), str(record["name"])))
    return found


def report(plugin_id: str) -> dict:
    """Usage plus the stored-file list the Extensions row shows.

    The list stops at `LISTED_FILES`. `truncated` says the walk found more.
    Nothing in the dict is a host path.
    """
    home = state_home(plugin_id)
    used, files = usage(home) if home.is_dir() else (0, 0)
    cap = cap_bytes(plugin_id)
    entries = _stored_entries(home)
    return {
        "used_bytes": used,
        "file_count": files,
        "cap_bytes": cap,
        "used_mb": round(used / MB),
        "cap_mb": cap // MB,
        "entries": entries[:LISTED_FILES],
        "truncated": len(entries) > LISTED_FILES,
    }


def remove_stored_file(plugin_id: str, name: object) -> dict:
    """Delete one stored file and return the report that follows.

    A directory stays. A name that leaves the state folder stays. A symlink is
    unlinked as a symlink, so the thing it points at is left where it is.
    """
    rel = _relative_name(name)
    home = state_home(plugin_id)
    target = home.joinpath(*PurePosixPath(rel).parts)
    try:
        target.relative_to(home)
    except ValueError as exc:
        raise ValueError("name") from exc
    if target.is_symlink():
        target.unlink()
        return report(plugin_id)
    if not target.is_file():
        raise ValueError("missing")
    resolved = target.resolve()
    root = home.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("name")
    target.unlink()
    return report(plugin_id)


#: One key in the page store. A slash, a dot-segment and an empty name are refused.
_CLIENT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CLIENT_STORE_NAME = "client-store.json"
CLIENT_VALUE_MAX = 8192
CLIENT_STORE_MAX = 65536


def _client_key(key: object) -> str:
    if not isinstance(key, str) or _CLIENT_KEY.fullmatch(key) is None:
        raise ValueError("key")
    return key


def _read_client_store(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        name: value
        for name, value in loaded.items()
        if isinstance(name, str) and _CLIENT_KEY.fullmatch(name) is not None
    }


def client_get(plugin_id: str, key: object) -> tuple[object, bool]:
    """The stored value and whether the key is present. The folder stays uncreated."""
    name = _client_key(key)
    path = state_home(plugin_id) / CLIENT_STORE_NAME
    store = _read_client_store(path)
    if name not in store:
        return None, False
    return store[name], True


def client_set(plugin_id: str, key: object, value: object) -> bool:
    """Store one JSON value, or drop the key when the value is null.

    Returns whether the key is present afterwards. A value past the byte
    ceiling, a store past its own ceiling, or a write that would cross the
    bundle ceiling raises ValueError. The folder is created only for a write.
    """
    name = _client_key(key)
    home = state_home(plugin_id)
    path = home / CLIENT_STORE_NAME
    if path.is_symlink():
        raise ValueError("store")
    store = _read_client_store(path)
    if value is None:
        store.pop(name, None)
        body = b""
    else:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > CLIENT_VALUE_MAX:
            raise ValueError("value")
        store[name] = value
        body = json.dumps(store, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > CLIENT_STORE_MAX:
            raise ValueError("store")
    old = path.stat().st_size if path.is_file() else 0
    used, _files = usage(home) if home.is_dir() else (0, 0)
    if body and over(cap_bytes(plugin_id), used - old + len(body)):
        raise ValueError("cap")
    if not body:
        if path.is_file():
            path.unlink()
        return name in store
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(CLIENT_STORE_NAME + ".tmp")
    temporary.write_bytes(body)
    temporary.replace(path)
    return True
