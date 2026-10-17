"""core/store_retention.py — how long the stores under the configuration dir live.

``core/session_lifecycle.py`` bounds the session store. Every other directory the
product creates under ``EPHE_CONFIG_DIR`` grew without a rule, and measured 2026-10-14
on the owner's machine ``~/.ephe`` was 2.8 GB: ``build/`` alone held 2.4 GB in two
CPython-for-WASI build trees (``cpython-wasi`` 1.5 GB, ``cpython-wasi-verify`` 870 MB,
both built 2026-10-02) while the 8634 session directories together were 47 MB.

The verdict each store gets, written down so the next reader does not re-derive it:

**Rebuildable cache — pruned to a count.**
    ``build/``  the build scratch of the sandbox cell's interpreter: the pinned
                tarballs, the Python checkout, the cross-build work and the ``stage/``
                tree the installer copies from. ``build_cpython_guest.py``
                rebuilds it and, while a tree is intact, ``--no-build`` re-stages
                without a recompile. The recipe's own folder (``build/cpython-wasi``) is
                reserved the way a prune reserves the active session; the count caps the
                ad-hoc trees beside it.

**State — never touched.**
    ``cells/cpython-wasi-<version>/``  the installed guest: read-only, digest pinned in
        ``core/cpython_guest.manifest.json``, probed by the doctor's CPython-Cell row
        through ``cell_ready()``. Removing it stops the sandbox cell until a full rebuild.
    ``cells/work/``  one writable folder per session. The output journal, ``state.pkl``
        and the program are session state, and ``core.cpython_guest`` already bounds the
        folder by quota with only ``pyc/`` regenerable, so retention stays out of it.
    ``memory/``  the Kepta entries decay on the 90-day scale with a floor weight of 0.2
        (``core/memory_kepta_schema.py``) and auto-memory evicts past 1000 entries; the
        chroma index is derived from the entries. Left to those two owners.
    ``sessions/``  ``core/session_lifecycle.py`` owns it, registry and active session
        included.
    the loose records — ``trajectory.json``, ``audit.log``, ``usage.jsonl``,
        ``ephemeris.jsonl``, ``search.db``, ``artifacts.db``, ``artifacts/``, ``bench/``,
        ``logs/`` and the single-file configuration — one file or one named set each,
        reachable from its own surface.

A machine without ``build/`` is reported as a store that is absent and pruned to
nothing. One guard survives that case: while no guest is installed at all, the scratch
tree is the only fast path back to one, so the prune declines instead of removing it.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, NamedTuple

from core.cell_output import dir_bytes

#: The two verdicts above. Every store carries exactly one of them.
STATE = "state"
CACHE = "cache"

BUILD = "build"

#: The recipe's own scratch folder (``build_cpython_guest.py --scratch`` default).
#: Reserved: an ad-hoc tree may never evict the folder a ``--no-build`` re-stage reads.
DEFAULT_SCRATCH = "cpython-wasi"

#: Retention by count. Measured 2026-10-14: two trees, 2.4 GB, one the reserved default
#: and one a verification build legitimately left. A third names an experiment, and the
#: older of those goes instead of the default costing a full recompile. A count cannot be
#: outrun by a burst the way an age can, and an age would delete the live default for no
#: gain at all.
DEFAULT_KEEP: dict[str, int] = {BUILD: 2}

REBUILD_RECIPE = "python3 build_cpython_guest.py"


class Store(NamedTuple):
    """One path the product creates under the configuration dir, with its verdict."""

    name: str
    relative: str
    kind: str
    owner: str
    rebuild: str | None


#: Every store, so one walk answers what is here, how big it is and who bounds it.
STORES: tuple[Store, ...] = (
    Store(BUILD, "build", CACHE, "this module", REBUILD_RECIPE),
    Store("cells", "cells", STATE, "core.cpython_guest", None),
    Store("sessions", "sessions", STATE, "core.session_lifecycle", None),
    Store("memory", "memory", STATE, "core.auto_memory, core.memory_kepta", None),
    Store("trajectory", "trajectory.json", STATE, "core.trajectory", None),
    Store("audit", "audit.log", STATE, "core.audit_log", None),
    Store("usage", "usage.jsonl", STATE, "core.usage", None),
    Store("ephemeris", "ephemeris.jsonl", STATE, "core.ephemeris", None),
    Store("search", "search.db", STATE, "core.session_search", None),
    Store("artifacts-db", "artifacts.db", STATE, "core.artifact_store", None),
    Store("artifacts", "artifacts", STATE, "core.artifact_store", None),
    Store("bench", "bench", STATE, "the bench harness", None),
    Store("logs", "logs", STATE, "the desktop backend", None),
)


def _config_dir() -> Path:
    """Resolved per call from the environment, so a test or a moved profile retargets
    every store (``engine_config.CONFIG_DIR`` is bound once at import)."""
    from core import engine_config

    return Path(engine_config.config_root())


def store_path(relative: str) -> Path:
    """Where a store lies, relative to the live configuration directory."""
    return _config_dir() / relative


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _entry_count(path: Path) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    try:
        return sum(1 for _ in path.iterdir())
    except OSError:
        return 0


def scratch_trees(root: Path | None = None) -> list[Path]:
    """The build-scratch directories, newest first. Empty when ``build/`` is not there.

    Only directories count: a tarball or a stray file dropped into ``build/`` is not a
    tree the recipe owns and is never a candidate.
    """
    root = root if root is not None else store_path(BUILD)
    if not root.is_dir():
        return []
    try:
        trees = [child for child in root.iterdir() if child.is_dir()]
    except OSError:
        return []
    return sorted(trees, key=_mtime, reverse=True)


def store_report() -> dict[str, Any]:
    """Per store: its path, verdict, bytes, entry count and the owner that bounds it."""
    rows: list[dict[str, Any]] = []
    for store in STORES:
        path = store_path(store.relative)
        present = path.exists()
        rows.append({
            "name": store.name,
            "path": str(path),
            "kind": store.kind,
            "owner": store.owner,
            "rebuild": store.rebuild,
            "exists": present,
            "bytes": dir_bytes(path) if present else 0,
            "entries": _entry_count(path) if present else 0,
        })
    return {
        "config_dir": str(_config_dir()),
        "stores": rows,
        "cache_bytes": sum(row["bytes"] for row in rows if row["kind"] == CACHE),
        "state_bytes": sum(row["bytes"] for row in rows if row["kind"] == STATE),
    }


def _guest_installed() -> bool:
    """Asked of the module that owns the question, so a test can answer it too."""
    from core.cpython_guest import guest_installed

    return bool(guest_installed())


def _kept_names(trees: list[Path], cap: int) -> set[str]:
    """What a count leaves: the reserved default plus the newest of the rest."""
    reserved = [tree for tree in trees if tree.name == DEFAULT_SCRATCH]
    room = max(0, cap - len(reserved))
    fills = [tree for tree in trees if tree.name != DEFAULT_SCRATCH][:room]
    return {tree.name for tree in (*reserved, *fills)}


def prune_stores(keep: dict | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Retention by count over the rebuildable caches: newest kept, the rest removed.

    ``dry_run`` reports the removal it would make and unlinks nothing. Pruning is a
    deliberate call from a user or an operator, never a side effect of a build; a silent
    delete is itself the defect (the session prune's rule, applied here).
    """
    caps = dict(DEFAULT_KEEP if keep is None else keep)
    trees = scratch_trees()
    declined = ""
    if trees and not _guest_installed():
        # Once no guest is installed the scratch is the only fast re-stage left, so a
        # count must not be the reason the cell costs a full cross-compile to come back.
        declined = "no installed guest: the build scratch is the way back, nothing removed"
    if declined:
        return {
            "deleted": [],
            "kept": len(trees),
            "bytes_freed": 0,
            "remaining": {BUILD: len(trees)},
            "declined": declined,
            "dry_run": dry_run,
        }

    cap = max(0, int(caps.get(BUILD, 0)))
    survivors = _kept_names(trees, cap)
    deleted: list[str] = []
    bytes_freed = 0
    for tree in trees:
        if tree.name in survivors:
            continue
        bytes_freed += dir_bytes(tree)
        deleted.append(tree.name)
        if not dry_run:
            shutil.rmtree(tree, ignore_errors=True)
    return {
        "deleted": sorted(deleted),
        "kept": len(survivors),
        "bytes_freed": bytes_freed,
        "remaining": {BUILD: len(trees) - len(deleted)},
        "declined": "",
        "dry_run": dry_run,
    }
