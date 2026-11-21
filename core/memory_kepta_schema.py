"""
◑ Ephe — the Kepta port: schema & encodings
core/memory_kepta_schema.py

The data-holding part of the memory: constants, the decay curve, the
text/vector encoders and the complete DDL (tables, indexes, the FTS5 index with
its three triggers). Deliberately free of provider logic — a test can verify the
curve and the sentence encoders without opening a database.

Split up because the architecture rule knows 400 lines/module (scripts/
architecture_check.mjs); the ranking lives in core/memory_kepta_ranking.py,
the provider class in core/memory_kepta.py.
"""
from __future__ import annotations

import logging
import math
import re
import sqlite3
from array import array

logger = logging.getLogger(__name__)

#: Version of the port schema. Patches only as idempotent
# "ALTER TABLE … ADD COLUMN" (Kepta rule: no re-create in the field).
SCHEMA_VERSION = 2

VALID_TYPES = ("semantic", "episodic", "procedural")

#: Cosine similarity above which two writes count as the same fact
# (Chroma side: _DEDUPE_DISTANCE = 0.08 distance ≈ 0.92 similarity).
DEDUPE_SIMILARITY = 0.92

# Oblivion constants, verbatim from kepta/src/core/engine.ts
RETENTION_T_DAYS = 90.0
RETENTION_FLOOR = 0.2

MAX_ENTITIES_PER_MEMORY = 40
MIN_ENTITY_CHARS = 2
MIN_MENTION_CHARS = 3

_WIKI_LINK = re.compile(r"\[\[([^\]|]{2,80})\]\]")

MEMORY_DDL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
  rid INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'semantic'
    CHECK (type IN ('semantic','episodic','procedural')),
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 1.0,
  valid_from REAL,
  valid_to REAL,
  superseded_by TEXT,
  created_at REAL NOT NULL,
  updated_at REAL,
  deleted_at REAL,
  last_access_at REAL,
  access_count INTEGER NOT NULL DEFAULT 0,
  utility REAL NOT NULL DEFAULT 0.5,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(scope, deleted_at);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_superseded ON memories(superseded_by);
CREATE TABLE IF NOT EXISTS chunks (
  memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  text TEXT NOT NULL,
  embedding BLOB,
  embedding_model TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (memory_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_chunks_model ON chunks(embedding_model);
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS memory_entities (
  memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  PRIMARY KEY (memory_id, entity_id)
);
CREATE TABLE IF NOT EXISTS relations (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  target_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'related',
  valid_from REAL,
  valid_to REAL,
  memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_memory ON relations(memory_id);
"""

#: External-content FTS: the index holds no copies of the texts, `memories`
# stays the single source of truth (trigger sync instead of double storage).
FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  title, content, tags,
  content='memories', content_rowid='rid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, title, content, tags)
    VALUES (new.rid, new.title, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
    VALUES ('delete', old.rid, old.title, old.content, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
    VALUES ('delete', old.rid, old.title, old.content, old.tags);
  INSERT INTO memories_fts(rowid, title, content, tags)
    VALUES (new.rid, new.title, new.content, new.tags);
END;
"""


def retention_factor(utility: float, access_count: int, days_since_access: float) -> float:
    """Oblivion curve: how strongly an entry is damped once it rested.

    n=0, utility=0.5, days=0 → 1.0. n=0, utility=0.5, days=100 → 0.265.
    n=0, utility=0.5, days→∞ → 0.20.
    Frequently used and highly rated facts decay more slowly; the
    floor ensures that forgetting never means eliminating.
    """
    t_eff = (utility + min(access_count, 10) + 0.1) * RETENTION_T_DAYS
    if t_eff <= 0:
        return RETENTION_FLOOR
    return RETENTION_FLOOR + (1.0 - RETENTION_FLOOR) * math.exp(
        -max(days_since_access, 0.0) / t_eff
    )


def wiki_entities(text: str) -> list[str]:
    return [m.strip() for m in _WIKI_LINK.findall(text) if m.strip()]


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n <= 0:
        return vec
    return [x / n for x in vec]


def to_blob(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def from_blob(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


def title_of(text: str) -> str:
    head = re.split(r"(?<=[.!?\n])\s", text.strip(), maxsplit=1)[0]
    return head[:80].strip() or text[:40]


def chunked(text: str, size: int = 500) -> list[str]:
    parts: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not sentence:
            continue
        while len(sentence) > size:
            parts.append(sentence[:size])
            sentence = sentence[size:]
        parts.append(sentence)
    return parts or [text[:size]]


def fts_supported(db: sqlite3.Connection) -> bool:
    """FTS5 is standard library, but not guaranteed (self-built
    Python builds can leave it out). One probe table in temp costs nothing
    and decides whether leg 1 exists at all."""
    try:
        db.execute("CREATE VIRTUAL TABLE temp._kepta_probe USING fts5(a)")
        db.execute("DROP TABLE temp._kepta_probe")
        return True
    except sqlite3.OperationalError:
        return False


def init_schema(db: sqlite3.Connection) -> bool:
    """Creates the port schema and returns whether FTS5 is available.
    The FTS status goes into `meta`, so a later read access does not need to
    probe again (and `stats()` can report it)."""
    db.executescript(MEMORY_DDL)
    fts_available = fts_supported(db)
    if fts_available:
        db.executescript(FTS_DDL)
    else:
        logger.warning("kepta: FTS5 unavailable — retrieval runs on vector+entity legs only")
    row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        db.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('fts5', ?)",
        ("1" if fts_available else "0"),
    )
    db.commit()
    return fts_available
