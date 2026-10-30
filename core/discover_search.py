"""Offline intent search over the discover shelf.

The shelf answers without a network: the entries are committed files, the
intent tags were computed when the catalog was generated, and the ranking runs
in a SQLite FTS5 table built once in memory (BM25 with the tag column weighted
heaviest). Ours comes first, then the curated picks, then the recent rest.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import discover_intent, mcp_catalog

#: Higher tiers win: our own catalog, then a named pick, then recently seen. The bonus
#: is large enough to survive a BM25 spread over the publisher descriptions.
_TIER_BONUS = {0: 8.0, 1: 2.0, 2: 0.0}
_TOKEN = re.compile(r"[0-9a-z]{2,}")
#: Words that carry no task in either language. Left in, a three-letter filler would
#: match half the shelf and bury the entry the intent tag just found.
_FILLER = frozenset(
    "als auch auf aus bei das dem den der des die ein eine einen einer eines fuer".split()  # language-gate: ignore
    + "ich im in ist kann man mit nach oder soll ueber um und von vor zu zum zur".split()  # language-gate: ignore
    + """about all and any are as at be by can could for from has have how in into is it
    me my of on or our that the their there these this to use using was were what
    when which who will with you your""".split()
)
_INTENTS_PATH = Path(__file__).resolve().parent.parent / "marketplace" / "search-intents.json"
_lock = threading.Lock()
_ready: _Index | None = None


class _Index:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.execute(
            "CREATE VIRTUAL TABLE entries USING fts5("
            "id UNINDEXED, tier UNINDEXED, title, body, tags, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        for row in _rows():
            self.connection.execute(
                "INSERT INTO entries (id, tier, title, body, tags) VALUES (?, ?, ?, ?, ?)",
                row,
            )

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        folded = discover_intent.fold(query)
        tokens = [
            token
            for token in _TOKEN.findall(folded)
            if len(token) >= 3 and token not in _FILLER
        ]
        keys = discover_intent.intents_in(query)
        if not tokens and not keys:
            return []
        text_rank = self._text_ranks(tokens) if tokens else {}
        seen: set[str] = set()
        ordered: list[dict[str, Any]] = []
        for entry_id, tier in self._intent_hits(keys):
            seen.add(entry_id)
            ordered.append({"id": entry_id, "tier": tier, "score": text_rank.get(entry_id, 0.0)})
        ordered.sort(key=lambda one: (one["tier"], one["score"], one["id"]))
        for item in ordered:
            item.pop("tier", None)
        for entry_id, score in sorted(text_rank.items(), key=lambda one: (one[1], one[0])):
            if entry_id in seen:
                continue
            ordered.append({"id": entry_id, "score": score})
        return ordered[:limit]

    def _intent_hits(self, keys: list[str]) -> list[tuple[str, int]]:
        """Rows whose tag says they do the task, ours first, then by tier."""
        if not keys:
            return []
        expression = " OR ".join(f"tags:{key}" for key in keys)
        try:
            rows = self.connection.execute(
                "SELECT id, tier FROM entries WHERE entries MATCH ? ORDER BY tier, id",
                (expression,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(str(entry_id), int(tier)) for entry_id, tier in rows]

    def _text_ranks(self, tokens: list[str]) -> dict[str, float]:
        """What the typed words alone find, as a BM25 rank per entry."""
        if not tokens:
            return {}
        expression = " OR ".join(f"{token}*" for token in dict.fromkeys(tokens))
        try:
            rows = self.connection.execute(
                "SELECT id, bm25(entries, 0.0, 0.0, 4.0, 1.0, 0.0) AS rank "
                "FROM entries WHERE entries MATCH ? ORDER BY rank",
                (expression,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {str(entry_id): float(rank) for entry_id, rank in rows}


def _precomputed_tags() -> dict[str, list[str]]:
    try:
        payload = json.loads(_INTENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {
        str(key): [str(tag) for tag in value]
        for key, value in entries.items()
        if isinstance(value, list)
    }


def _rows() -> list[tuple[str, int, str, str, str]]:
    rows: list[tuple[str, int, str, str, str]] = []
    precomputed = _precomputed_tags()
    for tier, entries in (
        (0, mcp_catalog.catalog_entries()),
        (1, mcp_catalog.curated_entries()),
    ):
        for entry in entries:
            entry_id = str(entry.get("id") or entry.get("name") or "")
            if not entry_id:
                continue
            title = str(entry.get("name") or entry.get("title") or entry_id)
            description = entry.get("description")
            if isinstance(description, dict):
                description = description.get("en") or description.get("de") or ""
            body = f"{description or ''} {entry.get('install_hint') or ''} {entry.get('category') or ''}"
            tags = precomputed.get(entry_id)
            if tags is None:
                tags = discover_intent.tags_for(
                    title, str(description or ""), str(entry.get("category") or "")
                )
            rows.append((entry_id, tier, title, body[:600], " ".join(tags)))
    return rows


def search(query: str, limit: int = 24) -> list[dict[str, Any]]:
    """Ranked entry ids for a typed phrase; empty when nothing matches."""
    text = str(query or "").strip()
    if len(text) < 2:
        return []
    global _ready
    if _ready is None:
        with _lock:
            if _ready is None:
                try:
                    _ready = _Index()
                except sqlite3.OperationalError:
                    return []
    return _ready.search(text, max(1, min(int(limit), 100)))
