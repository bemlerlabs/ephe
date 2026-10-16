"""Ephe – the CPython guest: where it lies and whether it is the pinned one (wave E1).

The one question this module asks: **is the interpreter we are about to start the
same one we built?** It knows the manifest
(``core/cpython_guest.manifest.json``), the installation paths under
``~/.ephe/cells/`` and the hashes — and nothing else. Execution, fuel caps and
report text are deliberately the other half of the seam and live in
``core.cpython_cell``.

Why the split: the integrity path is needed on EVERY load of a guest, the
execution path only when code arrives. A verified guest that cannot be started is
also a stateless diagnosis case — exactly what ``ephe doctor`` and the settings
card show.

Second, what the guest leaves on the disk belongs here: the writable folder of a
session and its total cap (``sweep_work_dir``). The engine caps per file, never
the sum — the sum is Ephe's promise, so Ephe's cleaning is its enforcement.

The ~29 MB interpreter and its stdlib tree never sit in Git; the manifest holds
the entry hash, the tree digest and the build recipe (source, toolchain, licence,
patch). A deviation is an error case with an actionable hint, not a silent
fallback (AGENTS.md: never a hidden fallback).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

from core.cell_output import STDERR_LOG_NAME, STDOUT_LOG_NAME, dir_bytes

MANIFEST_FILE = Path(__file__).with_name("cpython_guest.manifest.json")

#: Optional override for the writable /work root of a session, independent of the
#: configuration directory. The guest interpreter itself always stays where the
#: manifest points (the developer's real, verified install), but the ephemeral work
#: folders a run writes can be moved elsewhere — production leaves this unset, so
#: the default stays ``<config dir>/cells/work``; a test suite points it at a
#: per-run temporary folder so no test ever writes into ``~/.ephe`` (see
#: ``tests/test_home_isolation.py``).
ENV_WORK_ROOT = "EPHE_CELL_WORK_ROOT"

_SAFE_SESSION = re.compile(r"[^A-Za-z0-9_.-]")
_manifest_cache: dict[str, Any] | None = None
_tree_ok_cache: dict[str, bool] = {}
_lock = threading.Lock()


# Manifest and guest path

def manifest() -> dict[str, Any]:
    """The compiled-in guest manifest (an empty dict when it is missing or unwell)."""
    global _manifest_cache
    with _lock:
        if _manifest_cache is None:
            try:
                _manifest_cache = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — a broken manifest is a failure case, not a crash
                _manifest_cache = {}
        return _manifest_cache


def _config_dir() -> Path:
    from core import engine_config

    return Path(engine_config.CONFIG_DIR)


def guest_dir() -> Path | None:
    """Installation directory of the guest or None (never installed)."""
    guest = manifest().get("guest") or {}
    rel = str(guest.get("install_dir") or "")
    if not rel:
        return None
    return _config_dir() / rel


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(root: Path) -> str:
    """SHA-256 over (relative path, file hash) — deterministic, sorted."""
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            lines.append(f"{path.relative_to(root).as_posix()}\0{_sha256_file(path)}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _library_present() -> bool:
    """Is the sandbox runner (`ephemora_cell`) importable? (opt-in dependency)"""
    import importlib.util

    return importlib.util.find_spec("ephemora_cell") is not None


def guest_state(*, deep: bool = False) -> dict[str, Any]:
    """Is the guest present and is it the pinned one? (doctor and load path, fail-soft)"""
    man = manifest()
    guest = man.get("guest") or {}
    state: dict[str, Any] = {
        "manifest": bool(guest),
        "version": guest.get("version") or "",
        "installed": False,
        "library": _library_present(),
        "entry_ok": False,
        "tree_ok": False,
        "path": "",
        "reason": "",
    }
    if not guest:
        state["reason"] = f"Manifest missing or unreadable: {MANIFEST_FILE}"
        return state
    directory = guest_dir()
    if directory is None or not directory.is_dir():
        state["reason"] = (
            f"CPython guest not installed ({directory}); "
            "build it reproducibly with: python3 build_cpython_guest.py"
        )
        return state
    if not state["library"]:
        state["reason"] = (
            "The CPython guest is there, but the sandbox runtime is missing — "
            "pip install 'ephe[sandbox]' (ephemora-cell, pinned Apache-2.0)"
        )
        return state
    entry = directory / str(guest.get("entry") or "python.wasm")
    state["installed"] = True
    state["path"] = str(directory)
    if not entry.is_file():
        state["reason"] = (
            f"Guest interpreter missing: {entry} — the guest is half built. "
            "Build it reproducibly with: python3 build_cpython_guest.py"
        )
        return state
    if _sha256_file(entry) != guest.get("entry_sha256"):
        state["reason"] = (
            f"Entry hash differs from the manifest ({entry}) — delete and rebuild: "
            "python3 build_cpython_guest.py"
        )
        return state
    state["entry_ok"] = True
    tree = directory / str(guest.get("stdlib_dir") or "root")
    cache_key = f"{directory}"
    if not deep and _tree_ok_cache.get(cache_key):
        state["tree_ok"] = True
        return state
    if not tree.is_dir():
        state["reason"] = f"stdlib tree missing: {tree}"
        return state
    if _tree_digest(tree) != guest.get("root_tree_sha256"):
        state["reason"] = (
            f"stdlib tree differs from the manifest ({tree}) — delete and rebuild: "
            "python3 build_cpython_guest.py"
        )
        return state
    _tree_ok_cache[cache_key] = True
    state["tree_ok"] = True
    return state


def cell_ready() -> bool:
    state = guest_state()
    return bool(state["entry_ok"] and state["tree_ok"])


def guest_installed() -> bool:
    """Did this machine get a guest at all — regardless of whether it verifies?

    The two cases must not collapse into one (wave E1, finding from the live
    test): "never installed" is an honest kernel case, but "installed and
    unverifiable" is sabotage or a half build. Whoever drops the second into the
    kernel runs model code unsandboxed that the user explicitly believed was in a
    cell — with full host access. The "without approval" half of that sentence is
    closed (W3-15): while the cell does not carry the run, ``execute_code`` is
    MUTATING and the approval gate stands in front of it
    (``core.tools.approval._runs_uncontained``).
    """
    directory = guest_dir()
    return directory is not None and directory.is_dir()


# The writable folder of a session

def session_slug(session_id: str) -> str:
    """The safe, short key of a session (folder name as well as lock name)."""
    slug = _SAFE_SESSION.sub("_", session_id or "default")[:64]
    return "default" if slug in {"", ".", ".."} else slug


def work_root() -> Path:
    """The parent of every session's writable folder.

    The configuration directory holds the guest interpreter, so a test that wants
    to keep running code against the real guest still needs it there — but the
    ephemeral per-session work folders must not pollute the developer's home.
    ``EPHE_CELL_WORK_ROOT`` redirects exactly those, leaving ``guest_dir`` alone.
    """
    override = (os.environ.get(ENV_WORK_ROOT) or "").strip()
    path = Path(override) if override else _config_dir() / "cells" / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path


def work_dir(session_id: str) -> Path:
    """The only writable folder of a session (/work inside the guest)."""
    # The slug carries no separator; the real path plus the prefix check keeps the
    # folder under the work root even so (py/path-injection).
    root = os.path.realpath(work_root())
    target = os.path.realpath(os.path.join(root, session_slug(session_id)))
    if not target.startswith(root + os.sep):
        raise ValueError(f"session folder leaves the work root: {session_id!r}")
    path = Path(target)
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def reset_work_dir(session_id: str) -> None:
    path = work_dir(session_id)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


# The total cap of /work
#
# The engine caps per FILE (`disk_quota_bytes` -> RLIMIT_FSIZE, EFBIG), never the
# sum: eight files of 4 MiB each got through in the measurement, and their
# io_budget guard scans the sandbox's own folder, not Ephe's /work preopen. The
# total cap is therefore Ephe's promise — and it is set here, not just measured.

#: They carry promises: the fetchable remainder of the output (I1-5), the
#: persisted state and the running program. Paying the cap with them would mean
#: buying one promise with another.
WORK_PROTECTED = frozenset({
    STDOUT_LOG_NAME, STDERR_LOG_NAME, "result.json", "state.pkl", "cell_boot.py", "program.py",
})

#: Regenerable and therefore first in line: the bytecode buffer of the guest.
WORK_CACHE_DIR = "pyc"


def sweep_work_dir(work: Path, quota_bytes: int) -> dict[str, Any]:
    """Bring a session's workspace down to the total cap — oldest first.

    Returns what is left and what had to give way for it (`evicted`, relative
    path; `evicted_data` without the regenerable buffer — the distinction belongs
    here, it is the only one that knows what `WORK_CACHE_DIR` is). When the
    evictable remainder is not enough, the quota stays exceeded and `over_quota`
    says so: protected files are never deleted in silence.
    """
    total = dir_bytes(work)
    if total <= quota_bytes:
        return {"work_bytes": total, "evicted": [], "evicted_data": [],
                "freed_bytes": 0, "over_quota": False}

    candidates: list[tuple[int, float, Path, str]] = []
    for path in work.rglob("*"):
        try:
            if not path.is_file():
                continue
            rel = path.relative_to(work)
            if len(rel.parts) == 1 and rel.name in WORK_PROTECTED:
                continue
            candidates.append((0 if rel.parts[0] == WORK_CACHE_DIR else 1,
                               path.stat().st_mtime, path, rel.as_posix()))
        except OSError:
            continue

    evicted: list[str] = []
    evicted_data: list[str] = []
    freed = 0
    for kind, _, path, name in sorted(candidates):
        if total <= quota_bytes:
            break
        try:
            size = path.stat().st_size
            path.unlink(missing_ok=True)
        except OSError:
            continue
        evicted.append(name)
        if kind:
            evicted_data.append(name)
        freed += size
        total -= size

    return {"work_bytes": total, "evicted": evicted, "evicted_data": evicted_data,
            "freed_bytes": freed, "over_quota": total > quota_bytes}
