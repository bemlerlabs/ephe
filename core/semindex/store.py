"""Lossless Semantic Tree — persistence (T3) + incremental reindex (T5).

SQLite: semindex_nodes + semindex_edges. Reindex is mtime-based (re-parse only
changed files). Deterministic: identical source → identical rows.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from core.semindex.tree import SemanticTree, build_tree_from_source

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


class SemanticStore:
    """SQLite-backed index with incremental reindex."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
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
        """Write one file into the index. Returns the node count."""
        p = str(path)
        if not self._needs_reindex(p):
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM semindex_nodes WHERE file = ?", (p,)
            ).fetchone()
            return int(cur[0]) if cur else 0
        source = Path(p).read_text(encoding="utf-8")
        mod = module or Path(p).stem
        tree = build_tree_from_source(source, p, mod)
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

    # Lookup-API (T3)
    def get_node(self, qualname: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id,kind,name,qualname,file,start,end,parent_id "
            "FROM semindex_nodes WHERE qualname = ?", (qualname,)
        ).fetchone()
        if row is None:
            return None
        keys = ("id", "kind", "name", "qualname", "file", "start", "end", "parent_id")
        return dict(zip(keys, row))

    def children_of(self, node_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT n.id,n.kind,n.name,n.qualname,n.file,n.start,n.end,n.parent_id "
            "FROM semindex_edges e JOIN semindex_nodes n ON n.id = e.dst "
            "WHERE e.src = ? AND e.kind = 'contains'", (node_id,)
        ).fetchall()
        keys = ("id", "kind", "name", "qualname", "file", "start", "end", "parent_id")
        return [dict(zip(keys, r)) for r in rows]

    def symbols_in(self, file: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id,kind,name,qualname,file,start,end,parent_id "
            "FROM semindex_nodes WHERE file = ?", (file,)
        ).fetchall()
        keys = ("id", "kind", "name", "qualname", "file", "start", "end", "parent_id")
        return [dict(zip(keys, r)) for r in rows]

    def nearest_def(self, file: str, line: int) -> dict | None:
        rows = self.conn.execute(
            "SELECT id,kind,name,qualname,file,start,end,parent_id "
            "FROM semindex_nodes WHERE file = ? AND kind != 'module' "
            "AND start <= ? AND end >= ? ORDER BY (end-start) ASC LIMIT 1",
            (file, line, line),
        ).fetchone()
        if rows is None:
            return None
        keys = ("id", "kind", "name", "qualname", "file", "start", "end", "parent_id")
        return dict(zip(keys, rows))
