"""Compact architecture summary from the index, for the system prompt.

The map answers four questions before the model reads a single file: which
languages the tree is written in, where it starts, which types carry it, and
which files hold the most symbols. It is generated from indexed rows only, so a
stale index produces a stale map — never an invented one.
"""
from __future__ import annotations

import os
from pathlib import Path

from core.semindex.store import SemanticStore

ENTRY_FILE_NAMES = frozenset({
    "main.py", "__main__.py", "app.py", "server.py", "cli.py", "manage.py",
    "main.rs", "lib.rs", "mod.rs", "build.rs",
    "index.ts", "index.tsx", "main.ts", "main.tsx", "app.tsx", "server.ts",
    "index.js", "main.js", "app.js",
})

TYPE_KINDS = ("class", "struct", "trait", "interface", "enum")


def _relative(file: str, root: Path) -> str:
    try:
        return Path(file).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return file


def _entrypoints(store: SemanticStore, root: Path, limit: int) -> list[str]:
    rows = store.conn.execute(
        "SELECT file, COUNT(*) FROM semindex_nodes WHERE kind = 'module' "
        "GROUP BY file"
    ).fetchall()
    found: list[str] = []
    for file, _ in rows:
        name = os.path.basename(file)
        if name in ENTRY_FILE_NAMES:
            found.append(_relative(file, root))
    return sorted(found)[:limit]


def _key_types(store: SemanticStore, root: Path, limit: int) -> list[str]:
    placeholders = ",".join("?" for _ in TYPE_KINDS)
    rows = store.conn.execute(
        "SELECT name, kind, file, start FROM semindex_nodes "
        f"WHERE kind IN ({placeholders}) ORDER BY file, start",
        TYPE_KINDS,
    ).fetchall()
    return [
        f"{name} ({kind}) — {_relative(file, root)}:{start}"
        for name, kind, file, start in rows[:limit]
    ]


def _busiest_files(store: SemanticStore, root: Path, limit: int) -> list[str]:
    rows = store.conn.execute(
        "SELECT file, COUNT(*) AS n FROM semindex_nodes "
        "WHERE kind != 'module' AND kind != 'import' "
        "GROUP BY file ORDER BY n DESC, file LIMIT ?", (limit,),
    ).fetchall()
    return [f"{_relative(file, root)} ({count} symbols)" for file, count in rows]


def build_project_map(store: SemanticStore, root: str | Path,
                      max_types: int = 24, max_files: int = 8) -> str:
    """The map as prompt text; empty sections are left out, not padded."""
    base = Path(root).resolve()
    languages = store.counts_by_language()
    files = store.file_count()
    symbols = store.symbol_count()
    if files == 0:
        return ""

    lines = ["## Project map (local index, generated from syntax trees)"]
    language_line = ", ".join(f"{name} {count}" for name, count in languages.items())
    lines.append(f"- Files: {files} indexed; symbols: {symbols}" + (
        f"; languages: {language_line}" if language_line else ""
    ))
    entrypoints = _entrypoints(store, base, 6)
    if entrypoints:
        lines.append(f"- Entrypoints: {', '.join(entrypoints)}")
    types = _key_types(store, base, max_types)
    if types:
        lines.append("- Key types:")
        lines.extend(f"  - {entry}" for entry in types)
    busiest = _busiest_files(store, base, max_files)
    if busiest:
        lines.append("- Densest files:")
        lines.extend(f"  - {entry}" for entry in busiest)
    lines.append(
        "- Ask query_codebase(query, kind) for a symbol, a file or a name "
        "before reading whole files."
    )
    return "\n".join(lines)


def project_map_for_workspace(root: str | Path,
                              db_path: str | Path | None = None) -> str:
    """Open the workspace index read-only in spirit and render its map."""
    from core.semindex.store import index_database

    database = Path(db_path) if db_path else index_database(root)
    if not database.exists():
        return ""
    store = SemanticStore(database)
    try:
        return build_project_map(store, root)
    finally:
        store.close()
