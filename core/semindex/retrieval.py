"""Lossless Semantic Tree — retrieval (T4).

Query → token → symbol match in the tree → nearest_def node → source span.
Deterministic, no vector embeddings, no LLM in the index.
"""
from __future__ import annotations

from pathlib import Path

from core.semindex.store import SemanticStore


def _read_span(file: str, start: int, end: int, cap: int = 4000) -> str:
    """Exact line-span excerpt from the source file (capped)."""
    try:
        lines = Path(file).read_text(encoding="utf-8").split("\n")
    except OSError:
        return ""
    seg = lines[max(0, start - 1):end]
    text = "\n".join(seg)
    if len(text) > cap:
        text = text[:cap] + "\n… [gekuerzt]"
    return text


def semantic_tree_search(store: SemanticStore, query: str,
                          limit: int = 8) -> list[dict]:
    """Query the tree. Returns hits with the source span.

    Match order: exact qualname → exact name → token partial match.
    """
    q = query.strip()
    if not q:
        return []
    hits: list[dict] = []
    seen: set[str] = set()

    def _push(row: dict | None) -> None:
        if row is None or row["id"] in seen:
            return
        seen.add(row["id"])
        row = dict(row)
        row["source"] = _read_span(row["file"], row["start"], row["end"])
        hits.append(row)

    # 1) exact qualname
    _push(store.get_node(q))
    # 2) exact name
    rows = store.conn.execute(
        "SELECT id,kind,name,qualname,file,start,end,parent_id "
        "FROM semindex_nodes WHERE name = ? LIMIT ?", (q, limit)
    ).fetchall()
    keys = ("id", "kind", "name", "qualname", "file", "start", "end", "parent_id")
    for r in rows:
        _push(dict(zip(keys, r)))
    # 3) token partial match (qualname LIKE)
    if len(hits) < limit:
        tokens = [t for t in q.replace(".", " ").split() if len(t) >= 3]
        for tok in tokens:
            rows = store.conn.execute(
                "SELECT id,kind,name,qualname,file,start,end,parent_id "
                "FROM semindex_nodes WHERE qualname LIKE ? LIMIT ?",
                (f"%{tok}%", limit),
            ).fetchall()
            for r in rows:
                _push(dict(zip(keys, r)))
            if len(hits) >= limit:
                break
    return hits[:limit]
