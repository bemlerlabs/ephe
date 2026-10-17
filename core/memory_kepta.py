"""
◑ Ephe – Kepta-core memory provider (ported, not patched)
core/memory_kepta.py

A SQLite brain instead of a vector service: FTS5 BM25, brute-force cosine and an
entity graph, fused with Reciprocal Rank Fusion, then weighted by recency,
confidence and oblivion retention. Ported from the Kepta-Core
`src/core/{store,engine}.ts` (MIT v2.6.11) — the constants and the ranking chain
were taken over unchanged so that Ephe's hits behave like those of a running Kepta.
The port sits spread over four modules — `memory_kepta_schema` (schema, decay
curve, encoders), `memory_kepta_ranking` (legs, RRF, boosts), `memory_kepta_read`
(listings, counters, search, access feedback, stats) and this one (the provider
class) — because the architecture limit pulls at 400 lines per module and these
responsibilities are different anyway.

Ephe extensions over Kepta (design + rationale: docs/MEMORY_KEPTA_DESIGN.md):
  * a `metadata` column (version 2) for Ephe's free dict (source/priority/hits),
    which has no home in Kepta's column model and drives eviction and injection.
  * scope is **enforced**: every read and write hangs on the workspace hash —
    Kepta does not enforce scope, in Ephe project A must never be readable in B (W16).
  * deletion is *soft* (`deleted_at`): the agent can later say what it has
    forgotten — the reason a new memory was needed in the first place.

No Node, no service, no new PyPI requirement: sqlite3 + FTS5 are standard library.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from core.memory_kepta_ranking import entry
from core.memory_kepta_read import KeptaReadMixin
from core.memory_kepta_schema import (
    DEDUPE_SIMILARITY,
    MAX_ENTITIES_PER_MEMORY,
    MIN_ENTITY_CHARS,
    VALID_TYPES,
    chunked,
    dot,
    from_blob,
    init_schema,
    title_of,
    to_blob,
    wiki_entities,
)

logger = logging.getLogger(__name__)


class KeptaProvider(KeptaReadMixin):
    """MemoryProvider based on SQLite. Every access is bound to `scope`."""

    def __init__(
        self,
        *,
        db_path: str,
        scope: str,
        embedder: Callable[[list[str]], list[list[float]]] | None = None,
        embed_model: str = "",
    ) -> None:
        if not scope:
            raise ValueError("KeptaProvider requires a scope")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._scope = scope
        self._embedder = embedder
        self._embed_model = embed_model or ("kepta-hash" if embedder else "")
        # One connection per thread. The server answers memory routes on the event
        # loop and writes post-turn facts on a worker thread, and sqlite3 refuses a
        # connection used off its creating thread. WAL makes the file readable from
        # all of them, so the thread that asks gets its own handle. Reachable before
        # only through Kepta releases; with one brain left it is the normal path.
        self._local = threading.local()
        self._fts_enabled = init_schema(self._db)

    # Helpers

    @property
    def _db(self) -> sqlite3.Connection:
        """The calling thread's connection, opened on first use."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA foreign_keys = ON")
            # WAL is a property of the file, not of the connection, and the first setter
            # can lose: better slow without WAL than with half transactions.
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                logger.debug("kepta: WAL unavailable for %s", self._db_path)
            self._local.conn = conn
        return conn

    @_db.setter
    def _db(self, conn: sqlite3.Connection) -> None:
        """Hands this thread a wrapped connection; the commit-gate test uses it."""
        self._local.conn = conn

    @property
    def name(self) -> str:
        return f"kepta_{self._scope}"

    @property
    def scope(self) -> str:
        return self._scope

    def close(self) -> None:
        """Closes this thread's connection; the file stays for the other threads."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        if self._embedder is None or not texts:
            return None
        try:
            return [list(t) for t in self._embedder(texts)]
        except Exception as exc:  # model missing/offline → legs 1+3 carry alone
            logger.warning("kepta: embedding unavailable (%s) — lexical fallback", exc)
            self._embedder = None
            return None

    def _active_rows(self) -> list[sqlite3.Row]:
        return list(
            self._db.execute(
                "SELECT * FROM memories WHERE scope = ? AND deleted_at IS NULL "
                "ORDER BY created_at DESC",
                (self._scope,),
            )
        )

    def _row_by_id(self, doc_id: str, *, include_deleted: bool = False) -> sqlite3.Row | None:
        sql = "SELECT * FROM memories WHERE scope = ? AND id = ?"
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        return self._db.execute(sql, (self._scope, doc_id)).fetchone()

    def _index_chunks(self, doc_id: str, text: str) -> None:
        chunk_texts = chunked(text)
        vectors = self._embed(chunk_texts)
        self._db.execute("DELETE FROM chunks WHERE memory_id = ?", (doc_id,))
        for seq, chunk in enumerate(chunk_texts):
            emb = vectors[seq] if vectors and seq < len(vectors) else None
            self._db.execute(
                "INSERT INTO chunks (memory_id, seq, text, embedding, embedding_model) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, seq, chunk, to_blob(emb) if emb is not None else None,
                 self._embed_model if emb is not None else ""),
            )

    def _link_entities(self, doc_id: str, names: list[str]) -> None:
        for name in names[:MAX_ENTITIES_PER_MEMORY]:
            clean = str(name).strip().lower()
            if len(clean) < MIN_ENTITY_CHARS:
                continue
            hit = self._db.execute("SELECT id FROM entities WHERE name = ?", (clean,)).fetchone()
            entity_id = int(hit["id"]) if hit else int(
                self._db.execute("INSERT INTO entities (name) VALUES (?)", (clean,)).lastrowid
            )
            self._db.execute(
                "INSERT OR IGNORE INTO memory_entities (memory_id, entity_id) VALUES (?, ?)",
                (doc_id, entity_id),
            )

    # Write

    def store(
        self, text: str, metadata: dict[str, Any] | None = None, *,
        memory_type: str | None = None, title: str | None = None,
        tags: list[str] | None = None, entities: list[str] | None = None,
        confidence: float | None = None, doc_id: str | None = None,
        commit: bool = True,
    ) -> str:
        """Creates a fact; '' when empty, near duplicates are merged.
        `doc_id` is set exclusively by the migration (source ids stay valid).
        `commit=False` leaves the write in the caller's open transaction, so
        `supersede` can land the insert and the mark under one commit."""
        text = (text or "").strip()
        if not text:
            return ""
        existing = self._find_near_duplicate(text)
        if existing:
            self._merge_into(existing, metadata, commit=commit)
            return str(existing["id"])

        now = time.time()
        incoming = dict(metadata or {})
        created = float(incoming.get("timestamp") or now)
        doc_id = doc_id or hashlib.sha256(f"{now}:{text}".encode()).hexdigest()[:16]
        kind = memory_type if memory_type in VALID_TYPES else "semantic"
        tag_list = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
        stored_meta = {k: v for k, v in incoming.items() if k not in ("timestamp", "hits")}
        confidence_val = (
            float(confidence) if confidence is not None
            else float(incoming.get("confidence", 1.0))
        )
        self._db.execute(
            "INSERT INTO memories (id, scope, type, title, content, tags, confidence, "
            "valid_from, created_at, last_access_at, access_count, utility, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                self._scope,
                kind,
                (title or title_of(text))[:200],
                text,
                json.dumps(tag_list, ensure_ascii=False),
                max(0.0, min(1.0, confidence_val)),
                created,
                created,
                created,
                int(incoming.get("hits") or 1),
                float(incoming.get("utility", 0.9 if incoming.get("priority") == "high" else 0.5)),
                json.dumps(stored_meta, ensure_ascii=False),
            ),
        )
        self._index_chunks(doc_id, text)
        names = wiki_entities(text) + list(entities or []) + tag_list
        if names:
            self._link_entities(doc_id, names)
        if commit:
            self._db.commit()
        return doc_id

    def _find_near_duplicate(self, text: str) -> sqlite3.Row | None:
        exact = self._db.execute(
            "SELECT * FROM memories WHERE scope = ? AND deleted_at IS NULL AND content = ?",
            (self._scope, text),
        ).fetchone()
        if exact:
            return exact
        vectors = self._embed([text])
        if not vectors:
            return None
        query = vectors[0]
        best: tuple[float, sqlite3.Row] | None = None
        for row in self._active_rows():
            for chunk in self._db.execute(
                "SELECT embedding FROM chunks WHERE memory_id = ? AND embedding_model = ?",
                (row["id"], self._embed_model),
            ):
                emb = chunk["embedding"]
                if not emb:
                    continue
                sim = dot(query, from_blob(bytes(emb)))
                if sim >= DEDUPE_SIMILARITY and (best is None or sim > best[0]):
                    best = (sim, row)
        return best[1] if best else None

    def _merge_into(self, row: sqlite3.Row, metadata: dict[str, Any] | None, *, commit: bool = True) -> None:
        """R30 dedupe, ported: hits++, last_seen, 'loudest priority wins'."""
        now = time.time()
        meta = entry(row)["metadata"]
        incoming = dict(metadata or {})
        meta["hits"] = int(row["access_count"] or 0) + 1
        meta["last_seen"] = now
        order = {"high": 2, None: 1, "low": 0}
        if order.get(incoming.get("priority"), 1) > order.get(meta.get("priority"), 1):
            meta["priority"] = incoming["priority"]
        meta.pop("hits", None)
        meta.pop("last_seen", None)
        self._db.execute(
            "UPDATE memories SET access_count = ?, last_access_at = ?, metadata = ? WHERE rid = ?",
            (
                int(row["access_count"] or 0) + 1,
                now,
                json.dumps(meta, ensure_ascii=False),
                row["rid"],
            ),
        )
        if commit:
            self._db.commit()

    def update(self, doc_id: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            raise ValueError("memory text must not be empty")
        row = self._row_by_id(doc_id)
        if row is None:
            raise KeyError(f"Memory entry '{doc_id}' not found.")
        self._db.execute(
            "UPDATE memories SET content = ?, title = ?, updated_at = ? WHERE rid = ?",
            (text, title_of(text), time.time(), row["rid"]),
        )
        self._index_chunks(doc_id, text)
        names = wiki_entities(text)
        if names:
            self._link_entities(doc_id, names)
        self._db.commit()

    def supersede(
        self, doc_id: str, new_text: str,
        metadata: dict[str, Any] | None = None, **write_options: Any,
    ) -> str:
        """Replaces a fact without deleting it: the old one keeps `superseded_by`
        and `valid_to`, the new one carries `supersedes` — descent in both
        directions, so the UI can say "that used to be the case". Duplicate dedupe
        runs first: identical text is no supersession of itself.

        The insert and the mark land under one commit: under a full disk the
        whole correction fails, never the new fact without the mark."""
        old = self._row_by_id(doc_id)
        if old is None:
            raise KeyError(f"Memory entry '{doc_id}' not found.")
        meta = {**(metadata or {}), "supersedes": doc_id}
        new_id = self.store(new_text, meta, commit=False, **write_options)
        if new_id == doc_id:
            self._db.commit()
            return new_id
        now = time.time()
        self._db.execute(
            "UPDATE memories SET superseded_by = ?, valid_to = ?, updated_at = ? WHERE rid = ?",
            (new_id, now, now, old["rid"]),
        )
        self._db.commit()
        return new_id

    def delete(self, doc_id: str) -> None:
        """Soft delete — invisible for retrieval, auditable in the file."""
        row = self._row_by_id(doc_id)
        if row is None:
            raise KeyError(f"Memory entry '{doc_id}' not found.")
        self._db.execute(
            "UPDATE memories SET deleted_at = ? WHERE rid = ?", (time.time(), row["rid"])
        )
        self._db.commit()

    def restore(self, doc_id: str) -> None:
        row = self._row_by_id(doc_id, include_deleted=True)
        if row is None or not row["deleted_at"]:
            raise KeyError(f"Deleted memory entry '{doc_id}' not found.")
        self._db.execute("UPDATE memories SET deleted_at = NULL WHERE rid = ?", (row["rid"],))
        self._db.commit()

    def clear(self) -> None:
        self._db.execute("DELETE FROM memories WHERE scope = ?", (self._scope,))
        self._db.commit()

