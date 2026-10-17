"""
◑ Ephe – Kepta port: read and access surface
core/memory_kepta_read.py

The query side of the provider: the paged listings (`list_all`, `list_deleted`),
the counters (`count`, `deleted_count`, `count_access`), `search` over the
ranking, the access-feedback loop `search` drives (`record_access`) and `stats`.
Split out because the architecture rule knows 400 lines/module
(scripts/architecture_check.mjs); the provider class stays in
core/memory_kepta.py, so `from core.memory_kepta import KeptaProvider` names the
same class and every method here is a method on it.

The mixin holds no state: it uses the attributes and helpers the provider sets
up — `_db`, `_scope`, `_embedder`, `_embed_model`, `_fts_enabled`, `_db_path`,
plus `_row_by_id`, `_active_rows` and `_embed`.
"""
from __future__ import annotations

import json
import time
from typing import Any

from core.memory_kepta_ranking import entry, ranked_search
from core.memory_kepta_schema import dot, from_blob, normalize


class KeptaReadMixin:
    """Read and query methods composed into `KeptaProvider`."""

    def count(self) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE scope = ? AND deleted_at IS NULL",
            (self._scope,),
        ).fetchone()
        return int(row["c"])

    def deleted_count(self) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE scope = ? AND deleted_at IS NOT NULL",
            (self._scope,),
        ).fetchone()
        return int(row["c"])

    def count_access(self, doc_id: str) -> int:
        row = self._row_by_id(doc_id, include_deleted=True)
        if row is None:
            raise KeyError(f"Memory entry '{doc_id}' not found.")
        return int(row["access_count"] or 0)

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._paged(False, limit)

    def list_deleted(self, limit: int = 100) -> list[dict[str, Any]]:
        """The trash bin, newest removal first — the entry carries `deleted_at` in
        its metadata, so the UI can say when it is missing."""
        return self._paged(True, limit)

    def _paged(self, include_deleted: bool, limit: int) -> list[dict[str, Any]]:
        op = "IS NOT NULL" if include_deleted else "IS NULL"
        order = "deleted_at" if include_deleted else "created_at"
        rows = self._db.execute(
            f"SELECT * FROM memories WHERE scope = ? AND deleted_at {op} "
            f"ORDER BY {order} DESC LIMIT ?",
            (self._scope, max(1, int(limit))),
        ).fetchall()
        return [entry(r) for r in rows]

    def search(self, query: str, top_k: int = 15) -> list[dict[str, Any]]:
        hits = ranked_search(
            self._db,
            scope=self._scope,
            query=query,
            rows=self._active_rows(),
            embed=self._embed,
            embed_model=self._embed_model,
            fts_enabled=self._fts_enabled,
            top_k=top_k,
        )
        self.record_access([h["id"] for h in hits])
        return hits

    def record_access(self, doc_ids: list[str]) -> None:
        """Kepta's feedback loop: a hit makes the next one cheaper.
        Exactly the signal that the state_tools cap and auto-memory eviction have
        to guess at today."""
        if not doc_ids:
            return
        now = time.time()
        for doc_id in doc_ids:
            self._db.execute(
                "UPDATE memories SET access_count = access_count + 1, last_access_at = ? "
                "WHERE scope = ? AND id = ? AND deleted_at IS NULL",
                (now, self._scope, doc_id),
            )
        self._db.commit()

    def stats(self) -> dict[str, Any]:
        embedded = self._db.execute(
            "SELECT COUNT(*) AS c FROM chunks c JOIN memories m ON m.id = c.memory_id "
            "WHERE m.scope = ? AND c.embedding IS NOT NULL",
            (self._scope,),
        ).fetchone()
        return {
            "total": self.count(),
            "deleted": self.deleted_count(),
            "chunks_embedded": int(embedded["c"]),
            "vector_leg": self._embedder is not None,
            "lexical_leg": self._fts_enabled,
            "embedding_model": self._embed_model if self._embedder is not None else "",
            "scope": self._scope,
            "provider": "kepta",
            "db_path": self._db_path,
        }

    def meta_value(self, key: str) -> Any:
        """One `meta` row, decoded, or None. The migration leaves the boundary it
        converted here, so a reader finds it next to the data it applies to."""
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return row["value"]

    def cosine_matches(self, query: str, *, limit: int = 1) -> list[tuple[dict[str, Any], float]]:
        """(entry, cosine) for the closest active rows, best first.

        `search` fuses three legs into a rank score and the angle is gone by then.
        A caller that carries a distance boundary of its own — the vision store
        keeps the L2 radius its retired client queried with — needs the number.
        """
        vectors = self._embed([query])
        if not vectors:
            return []
        qvec = normalize(list(vectors[0]))
        best: dict[str, float] = {}
        for chunk in self._db.execute(
            "SELECT c.memory_id AS mid, c.embedding AS emb FROM chunks c "
            "JOIN memories m ON m.id = c.memory_id "
            "WHERE m.scope = ? AND m.deleted_at IS NULL AND c.embedding_model = ?",
            (self._scope, self._embed_model),
        ):
            emb = chunk["emb"]
            if not emb:
                continue
            sim = dot(qvec, normalize(from_blob(bytes(emb))))
            if sim > best.get(str(chunk["mid"]), -2.0):
                best[str(chunk["mid"])] = sim
        rows = {str(r["id"]): r for r in self._active_rows()}
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]
        return [(entry(rows[mid]), sim) for mid, sim in ranked if mid in rows]
