"""
◑ Ephe – Kepta port: retrieval ranking
core/memory_kepta_ranking.py

The three legs (BM25 over FTS5, brute-force cosine over the chunk BLOBs,
entity graph) and their fusion with Reciprocal Rank Fusion, then the
boost chain: recency × confidence × oblivion retention, with damping for
expired and superseded facts. Port from kepta/src/core/engine.ts — the
constants are unchanged so that Ephe's hits behave like those of a running
Kepta.

Two things here are contract, not style:
  * Normalization. Raw RRF values sit at ~1/(k+1) ≈ 0.016 per leg, and
    `get_context_injection()` filters at score < 0.3 — without normalization
    the whole memory would silently fall out of every prompt.
  * Order before the cut. Sorting runs on the unclipped score,
    `min(1.0, …)` happens only at output; otherwise two good
    hits would lose what distinguishes them.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from typing import Any, Callable

from core.memory_kepta_schema import (
    MIN_MENTION_CHARS,
    from_blob,
    dot,
    normalize,
    retention_factor,
)

logger = logging.getLogger(__name__)

# Ranking constants, verbatim from kepta/src/core/engine.ts
RRF_K = 60
EXPIRED_FACTOR = 0.5
SUPERSEDED_FACTOR = 0.4
RECENCY_MAX_BONUS = 0.15
RECENCY_WINDOW = 365 * 86400.0

#: Cap per leg: RRF ranks positions, not quantities — 50 candidates
# are enough to cover the top-k safely after the boost chain.
LEG_LIMIT = 50

_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "und", "oder", "aber", "ist", "sind", "war", "waren", "hat", "haben",
    "mit", "von", "für", "auf", "aus", "bei", "im", "ins", "zum", "zur",
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "has", "have",
    "with", "for", "on", "of", "in", "to", "that", "this", "it", "as", "be",
}


def managed_metadata(row: sqlite3.Row) -> dict[str, Any]:
    """Shapes the columns back into the free dict that Ephe's consumers
    expect — `metadata` carries the userInput, the rest is derived."""
    meta: dict[str, Any] = {}
    try:
        loaded = json.loads(row["metadata"] or "{}")
        if isinstance(loaded, dict):
            meta.update(loaded)
    except (TypeError, ValueError):
        pass
    tags = json.loads(row["tags"] or "[]")
    meta["timestamp"] = row["created_at"]
    meta["hits"] = row["access_count"]
    meta["type"] = row["type"]
    if tags:
        meta["tags"] = tags
    if row["updated_at"]:
        meta["updated_at"] = row["updated_at"]
    if row["last_access_at"]:
        meta["last_seen"] = row["last_access_at"]
    if row["superseded_by"]:
        meta["superseded_by"] = row["superseded_by"]
    if row["valid_to"]:
        meta["valid_to"] = row["valid_to"]
    if row["deleted_at"]:
        meta["deleted_at"] = row["deleted_at"]
    return meta


def entry(row: sqlite3.Row, score: float | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row["id"],
        "text": row["content"],
        "metadata": managed_metadata(row),
    }
    if score is not None:
        out["score"] = score
    return out


def fts_terms(query: str) -> list[str]:
    return [
        t for t in re.split(r"[^\w]+", query.lower(), flags=re.UNICODE)
        if len(t) >= 2 and t not in _STOPWORDS
    ]


def leg_fts(
    db: sqlite3.Connection, scope: str, query: str,
    active: dict[str, sqlite3.Row], *, fts_enabled: bool,
) -> list[str]:
    if not fts_enabled:
        return []
    terms = fts_terms(query)
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    try:
        rows = db.execute(
            "SELECT m.id AS id, bm25(memories_fts) AS s FROM memories_fts "
            "JOIN memories m ON m.rid = memories_fts.rowid "
            "WHERE memories_fts MATCH ? AND m.scope = ? AND m.deleted_at IS NULL "
            f"ORDER BY s ASC LIMIT {LEG_LIMIT}",
            (match, scope),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("kepta: FTS query failed (%s)", exc)
        return []
    return [str(r["id"]) for r in rows if str(r["id"]) in active]


def leg_vector(
    db: sqlite3.Connection, scope: str, query: str,
    active: dict[str, sqlite3.Row], *, embed_model: str,
    embed: Callable[[list[str]], list[list[float]] | None],
) -> list[str]:
    vectors = embed([query])
    if not vectors:
        return []
    qvec = normalize(list(vectors[0]))
    best: dict[str, float] = {}
    for chunk in db.execute(
        "SELECT c.memory_id AS mid, c.embedding AS emb FROM chunks c "
        "JOIN memories m ON m.id = c.memory_id "
        "WHERE m.scope = ? AND m.deleted_at IS NULL AND c.embedding_model = ?",
        (scope, embed_model),
    ):
        if chunk["mid"] not in active or not chunk["emb"]:
            continue
        sim = dot(qvec, normalize(from_blob(bytes(chunk["emb"]))))
        if sim <= 0.0:
            continue
        if sim > best.get(chunk["mid"], -1.0):
            best[chunk["mid"]] = sim
    return sorted(best, key=lambda k: best[k], reverse=True)[:LEG_LIMIT]


def leg_entities(
    db: sqlite3.Connection, scope: str, query: str, active: dict[str, sqlite3.Row]
) -> list[str]:
    q = query.lower()
    names = [
        str(r["name"])
        for r in db.execute("SELECT id, name FROM entities LIMIT 500")
        if len(str(r["name"])) >= MIN_MENTION_CHARS and str(r["name"]) in q
    ]
    if not names:
        return []
    placeholders = ",".join("?" * len(names))
    rows = db.execute(
        f"SELECT DISTINCT me.memory_id AS id FROM memory_entities me "
        f"JOIN entities e ON e.id = me.entity_id "
        f"JOIN memories m ON m.id = me.memory_id "
        f"WHERE e.name IN ({placeholders}) AND m.scope = ? AND m.deleted_at IS NULL",
        (*names, scope),
    ).fetchall()
    return [str(r["id"]) for r in rows if str(r["id"]) in active]


def boost(row: sqlite3.Row, raw: float, *, leg_count: int, now: float) -> float:
    """Normalization (a contract, see the module docstring) and then the boost
    chain. Multiplication, not addition: a stale entry should fall back
    relatively, no matter how good its rank was."""
    score = raw / (leg_count / (RRF_K + 1))
    age = max(0.0, now - float(row["created_at"] or now))
    if age < RECENCY_WINDOW:
        score *= 1.0 + RECENCY_MAX_BONUS * (1.0 - age / RECENCY_WINDOW)
    score *= 0.5 + 0.5 * float(row["confidence"] or 1.0)
    days_since = (now - float(row["last_access_at"] or row["created_at"] or now)) / 86400.0
    score *= retention_factor(
        float(row["utility"] or 0.5), int(row["access_count"] or 0), days_since
    )
    if row["valid_to"] and float(row["valid_to"]) < now:
        score *= EXPIRED_FACTOR
    if row["superseded_by"]:
        score *= SUPERSEDED_FACTOR
    return score


def ranked_search(
    db: sqlite3.Connection,
    *,
    scope: str,
    query: str,
    rows: list[sqlite3.Row],
    embed: Callable[[list[str]], list[list[float]] | None],
    embed_model: str,
    fts_enabled: bool,
    top_k: int = 15,
) -> list[dict[str, Any]]:
    if not (query or "").strip() or not rows:
        return []
    active = {str(r["id"]): r for r in rows}
    now = time.time()

    legs = [leg_fts(db, scope, query, active, fts_enabled=fts_enabled),
            leg_entities(db, scope, query, active)]
    leg_count = 2
    vector_leg = leg_vector(db, scope, query, active, embed_model=embed_model, embed=embed)
    if vector_leg:
        legs.append(vector_leg)
        leg_count = 3

    fused: dict[str, float] = {}
    for leg in legs:
        for rank, doc_id in enumerate(leg):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    if not fused:
        return []

    scored = [(boost(active[d], raw, leg_count=leg_count, now=now), d) for d, raw in fused.items()]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    limit = max(1, min(int(top_k), len(scored)))
    return [
        entry(active[doc_id], score=round(min(1.0, max(score, 0.0)), 4))
        for score, doc_id in scored[:limit]
    ]
