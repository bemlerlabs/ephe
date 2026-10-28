"""Lossless Semantic Tree — persistence (T3) + incremental reindex (T5).

SQLite: semindex_nodes + semindex_edges. Reindex is mtime-based (re-parse only
changed files). Deterministic: identical source → identical rows.
"""
from __future__ import annotations

import fnmatch
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from core import sqlite_util
from core.semindex.tree import (
    LANGUAGE_BY_SUFFIX,
    SUPPORTED_SUFFIXES,
    SemanticTree,
    build_tree_from_language,
)

#: Directories no index pass enters; the generated trees of a build, not its source.
SKIP_DIRECTORIES = frozenset({
    "node_modules", "target", ".git", "dist", ".venv", "__pycache__", "build",
    ".next", ".turbo", ".mypy_cache", ".pytest_cache", ".ruff_cache", "venv",
})

IGNORE_FILES = (".gitignore", ".epheignore")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS semindex_nodes (
    id TEXT PRIMARY KEY, kind TEXT, name TEXT, qualname TEXT,
    file TEXT, start INTEGER, end INTEGER, parent_id TEXT
);
CREATE TABLE IF NOT EXISTS semindex_edges (
    src TEXT, dst TEXT, kind TEXT
);
CREATE TABLE IF NOT EXISTS semindex_files (
    file TEXT PRIMARY KEY, mtime REAL
);
"""

_NODE_COLUMNS = "id,kind,name,qualname,file,start,end,parent_id"


@dataclass(frozen=True)
class IndexResult:
    root: str
    files: int
    symbols: int
    removed: int
    duration_ms: int

    def as_dict(self) -> dict:
        return asdict(self)


def index_database(root: str | Path) -> Path:
    """Where a workspace's index lives: `<root>/.ephe/index.db`."""
    return Path(root).resolve() / ".ephe" / "index.db"


def read_ignore_patterns(root: str | Path) -> list[str]:
    """Patterns from `.gitignore`/`.epheignore`; negations are ignored (subtractive
    rules would need a full git matcher and buy nothing for an index)."""
    patterns: list[str] = []
    base = Path(root)
    for name in IGNORE_FILES:
        path = base / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if line and not line.startswith(("#", "!")):
                patterns.append(line.rstrip("/"))
    return patterns


def ignored_relative_path(relative: str, patterns: list[str]) -> bool:
    parts = relative.split("/")
    for pattern in patterns:
        if "/" not in pattern:
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        elif fnmatch.fnmatch(relative, pattern):
            return True
    return False


def iter_source_files(root: str | Path, patterns: list[str] | None = None) -> list[Path]:
    """Every indexable file below `root`, in a stable order, minus skipped paths."""
    base = Path(root).resolve()
    patterns = patterns if patterns is not None else read_ignore_patterns(base)
    found: list[Path] = []
    for current, directories, names in os.walk(base):
        directories[:] = sorted(
            d for d in directories
            if d not in SKIP_DIRECTORIES and not d.startswith(".")
        )
        relative_dir = Path(current).relative_to(base).as_posix()
        if relative_dir != "." and ignored_relative_path(relative_dir, patterns):
            directories[:] = []
            continue
        for name in sorted(names):
            if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            relative = name if relative_dir == "." else f"{relative_dir}/{name}"
            if ignored_relative_path(relative, patterns):
                continue
            found.append(Path(current) / name)
    return found


class SemanticStore:
    """SQLite-backed index with incremental reindex."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self.conn = sqlite_util.connect(self.db_path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _file_mtime(self, path: str) -> float:
        try:
            return Path(path).stat().st_mtime
        except OSError:
            return 0.0

    def _needs_reindex(self, path: str) -> bool:
        row = self.conn.execute(
            "SELECT mtime FROM semindex_files WHERE file = ?", (path,)
        ).fetchone()
        if row is None:
            return True
        return abs(row[0] - self._file_mtime(path)) > 1e-9

    def index_file(self, path: str | Path, module: str | None = None) -> int:
        """Write one file into the index. Returns the node count (0 when the
        suffix has no extractor)."""
        p = str(path)
        suffix = Path(p).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return 0
        if not self._needs_reindex(p):
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM semindex_nodes WHERE file = ?", (p,)
            ).fetchone()
            return int(cur[0]) if cur else 0
        try:
            source = Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return 0
        mod = module or Path(p).stem
        tree = build_tree_from_language(
            source, p, mod, LANGUAGE_BY_SUFFIX.get(suffix)
        )
        self._write_tree(p, tree)
        return len(tree.nodes)

    def _write_tree(self, path: str, tree: SemanticTree) -> None:
        c = self.conn
        c.execute("DELETE FROM semindex_nodes WHERE file = ?", (path,))
        c.execute(
            "DELETE FROM semindex_edges WHERE src IN "
            "(SELECT id FROM semindex_nodes WHERE file = ?)", (path,),
        )
        for n in tree.nodes.values():
            c.execute(
                "INSERT OR REPLACE INTO semindex_nodes "
                "(id,kind,name,qualname,file,start,end,parent_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (n.id, n.kind, n.name, n.qualname, n.file, n.start, n.end, n.parent),
            )
            for ch in n.children:
                c.execute(
                    "INSERT INTO semindex_edges (src,dst,kind) VALUES (?,?,?)",
                    (n.id, ch, "contains"),
                )
        c.execute(
            "INSERT OR REPLACE INTO semindex_files (file,mtime) VALUES (?,?)",
            (path, self._file_mtime(path)),
        )
        c.commit()

    def prune_missing(self, root: str | Path, known: set[str]) -> int:
        """Drop rows for files under `root` that no longer exist on disk."""
        prefix = str(Path(root).resolve()) + os.sep
        stale = [
            row[0] for row in self.conn.execute(
                "SELECT file FROM semindex_files"
            ).fetchall()
            if row[0].startswith(prefix) and row[0] not in known
        ]
        for path in stale:
            self.conn.execute("DELETE FROM semindex_nodes WHERE file = ?", (path,))
            self.conn.execute(
                "DELETE FROM semindex_edges WHERE src NOT IN "
                "(SELECT id FROM semindex_nodes)"
            )
            self.conn.execute("DELETE FROM semindex_files WHERE file = ?", (path,))
        if stale:
            self.conn.commit()
        return len(stale)

    # Lookup-API (T3)
    def get_node(self, qualname: str) -> dict | None:
        row = self.conn.execute(
            f"SELECT {_NODE_COLUMNS} FROM semindex_nodes WHERE qualname = ?",
            (qualname,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(_NODE_COLUMNS.split(","), row))

    def children_of(self, node_id: str) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT n.{_NODE_COLUMNS.replace(',', ',n.')} "
            "FROM semindex_edges e JOIN semindex_nodes n ON n.id = e.dst "
            "WHERE e.src = ? AND e.kind = 'contains'", (node_id,)
        ).fetchall()
        return [dict(zip(_NODE_COLUMNS.split(","), r)) for r in rows]

    def symbols_in(self, file: str) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {_NODE_COLUMNS} FROM semindex_nodes WHERE file = ?", (file,)
        ).fetchall()
        return [dict(zip(_NODE_COLUMNS.split(","), r)) for r in rows]

    def nearest_def(self, file: str, line: int) -> dict | None:
        rows = self.conn.execute(
            f"SELECT {_NODE_COLUMNS} FROM semindex_nodes WHERE file = ? "
            "AND kind != 'module' AND start <= ? AND end >= ? "
            "ORDER BY (end-start) ASC LIMIT 1",
            (file, line, line),
        ).fetchone()
        if rows is None:
            return None
        return dict(zip(_NODE_COLUMNS.split(","), rows))

    def search(self, query: str, kind: str | None = None, limit: int = 10) -> list[dict]:
        """Name/qualname/file match, exact names first; `kind` narrows the rows."""
        q = query.strip()
        if not q:
            return []
        kind_clause = " AND kind = ?" if kind else ""
        kind_args: tuple[str, ...] = (kind,) if kind else ()
        seen: set[str] = set()
        hits: list[dict] = []

        def _collect(rows: list[tuple]) -> None:
            for row in rows:
                entry = dict(zip(_NODE_COLUMNS.split(","), row))
                if entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                hits.append(entry)

        _collect(self.conn.execute(
            f"SELECT {_NODE_COLUMNS} FROM semindex_nodes WHERE name = ?{kind_clause} "
            "ORDER BY file, start LIMIT ?", (q, *kind_args, limit),
        ).fetchall())
        if len(hits) < limit:
            pattern = f"%{q}%"
            _collect(self.conn.execute(
                f"SELECT {_NODE_COLUMNS} FROM semindex_nodes "
                f"WHERE qualname LIKE ?{kind_clause} ORDER BY file, start LIMIT ?",
                (pattern, *kind_args, limit),
            ).fetchall())
        if len(hits) < limit:
            pattern = f"%{q}%"
            _collect(self.conn.execute(
                f"SELECT {_NODE_COLUMNS} FROM semindex_nodes "
                f"WHERE file LIKE ?{kind_clause} ORDER BY file, start LIMIT ?",
                (pattern, *kind_args, limit),
            ).fetchall())
        return hits[:limit]

    def file_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM semindex_files").fetchone()
        return int(row[0]) if row else 0

    def symbol_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM semindex_nodes").fetchone()
        return int(row[0]) if row else 0

    def counts_by_kind(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT kind, COUNT(*) FROM semindex_nodes GROUP BY kind ORDER BY kind"
        ).fetchall()
        return {kind: int(count) for kind, count in rows}

    def counts_by_language(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT file FROM semindex_files").fetchall()
        counts: dict[str, int] = {}
        for (file,) in rows:
            language = LANGUAGE_BY_SUFFIX.get(Path(file).suffix.lower())
            if language:
                counts[language] = counts.get(language, 0) + 1
        return dict(sorted(counts.items()))

    def index_workspace(self, root: str | Path, progress=None) -> IndexResult:
        """Index every source file below `root`; unchanged files stay untouched."""
        import time

        started = time.monotonic()
        base = Path(root).resolve()
        patterns = read_ignore_patterns(base)
        files = iter_source_files(base, patterns)
        symbols = 0
        for position, file in enumerate(files, 1):
            module = file.relative_to(base).with_suffix("").as_posix().replace("/", ".")
            symbols += self.index_file(file, module=module)
            if progress is not None:
                progress(position, len(files))
        removed = self.prune_missing(base, {str(file) for file in files})
        return IndexResult(
            root=str(base),
            files=len(files),
            symbols=self.symbol_count(),
            removed=removed,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def reindex_single_file(
    store: SemanticStore, workspace: Path | str, file_path: Path | str
) -> int:
    """QD-013: after one write, bring that one file up to date.

    The store already skips a file whose mtime did not move, so a write that
    rewrote identical bytes costs one stat. A path outside the workspace is not
    indexed at all — the tool that wrote it was already refused there, and the
    index must not become the way around that fence.
    """
    root = Path(workspace).resolve()
    target = Path(file_path)
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if target != root and root not in target.parents:
        return 0
    nodes = store.index_file(target)
    store.conn.commit()
    return nodes


def index_workspace(root: str | Path, db_path: str | Path | None = None,
                    progress=None) -> IndexResult:
    """Open (or create) the workspace index and bring it up to date."""
    base = Path(root).resolve()
    database = Path(db_path) if db_path else index_database(base)
    database.parent.mkdir(parents=True, exist_ok=True)
    store = SemanticStore(database)
    try:
        return store.index_workspace(base, progress=progress)
    finally:
        store.close()
