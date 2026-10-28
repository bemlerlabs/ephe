"""QD-013: keep the codebase index in step with what a write tool just wrote.

The store already skips a file whose mtime did not move, so a write that rewrote
identical bytes costs one stat. Lives in its own module because `file_ops.py` sits
at the file-length ceiling: the write tools call it, they do not own it.
"""
from __future__ import annotations

from pathlib import Path


def resolve_index_path(written: Path | str) -> tuple[Path, Path] | None:
    """The (workspace root, index database) pair, or None when nothing is indexed."""
    from core.engine_config import get_workspace_dir
    from core.semindex.store import index_database

    root = Path(get_workspace_dir()).resolve()
    database = index_database(root)
    return (root, database) if database.exists() else None


def refresh_index(written: Path | str) -> None:
    """Update the index for this one file; a failure never fails the write.

    The file is already on disk, and an index that lags is repaired by the next
    full run — the opposite order would lose a write to a bookkeeping error.
    """
    try:
        from core.semindex.store import SemanticStore, reindex_single_file

        pair = resolve_index_path(written)
        if pair is None:
            return
        root, database = pair
        store = SemanticStore(database)
        try:
            reindex_single_file(store, root, Path(written))
        finally:
            store.close()
    except Exception:
        return
