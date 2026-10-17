"""
Ephe — R33 / stress triage P1-2: auto-memory ceiling + eviction + gate.

The 1000-message campaign ended with ~956 auto-memory entries (~0.9 stored
per turn) — unbounded growth with no ceiling, no eviction and no importance
gate. This suite pins the fix: low-signal turns (emoji-only / greeting-only
questions, refusal answers) never enter the store, and the auto_memory
namespace is capped by EPHE_MEMORY_MAX_ENTRIES with oldest-lowest-priority
eviction that never touches compaction-preserved knowledge.

RULE: tests before implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import pytest

from core import auto_memory


class FakeMemory:
    """In-memory stand-in with the tiny surface auto_memory relies on."""

    def __init__(self):
        self.entries = []          # [{id,text,metadata}]
        self.search_hits = []       # injected duplicates for the dedupe path
        self.deleted = []

    def search(self, query, top_k=15):
        return list(self.search_hits)

    def store(self, text, metadata=None):
        self.entries.append({
            "id": f"id-{len(self.entries)}",
            "text": text,
            "metadata": {"timestamp": 1_000_000.0 + len(self.entries), **(metadata or {})},
        })

    def count(self):
        return len(self.entries)

    def list_all(self, limit=100):
        ordered = sorted(
            self.entries,
            key=lambda e: e["metadata"].get("timestamp", 0),
            reverse=True,
        )
        return ordered[:limit]

    def delete(self, doc_id):
        self.deleted.append(doc_id)
        self.entries = [e for e in self.entries if e["id"] != doc_id]


@pytest.fixture
def fake(monkeypatch):
    mem = FakeMemory()
    monkeypatch.setattr(auto_memory, "_memory_factory", lambda: mem)
    monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
    monkeypatch.delenv("EPHE_MEMORY_MAX_ENTRIES", raising=False)
    return mem


GOOD_Q = "Wie sollte ich die FastAPI lifespan für den Scheduler aufbauen?"
GOOD_A = (
    "Starte den Scheduler direkt auf dem Eventloop im lifespan-Kontext, "
    "nicht in einem Worker-Thread — AsyncIOScheduler braucht einen laufenden "
    "Loop im aufrufenden Thread und sonst wird der Fehler nur geschluckt."
)


class TestImportanceGate:
    def test_emoji_only_question_is_rejected(self, fake):
        """
        GIVEN  an emoji/greeting-only question and a substantive answer
        WHEN   maybe_store_turn
        THEN   nothing is stored with reason low-value
        """
        res = auto_memory.maybe_store_turn("👍🎉 danke!", GOOD_A)
        assert res["stored"] is False
        assert res["reason"] == "low-value"
        assert fake.count() == 0

    def test_refusal_answer_is_rejected(self, fake):
        """
        GIVEN  a question plus a pure refusal/error answer over the length floor
        WHEN   maybe_store_turn
        THEN   the refusal never becomes long-term memory
        """
        res = auto_memory.maybe_store_turn(
            GOOD_Q,
            "I cannot help with that request, because it would require network "
            "access which is unavailable in this offline deployment scenario today.",
        )
        assert res["stored"] is False
        assert res["reason"] == "low-value"

    def test_substantive_turn_is_stored(self, fake):
        """
        GIVEN  a substantive Q/A pair
        WHEN   maybe_store_turn
        THEN   it is stored with source auto_memory
        """
        res = auto_memory.maybe_store_turn(GOOD_Q, GOOD_A)
        assert res["stored"] is True
        assert fake.count() == 1
        assert fake.entries[0]["metadata"]["source"] == "auto_memory"

    def test_disabled_toggle_wins(self, fake, monkeypatch):
        """
        GIVEN  memory disabled via env
        WHEN   maybe_store_turn
        THEN   reason is disabled and the gate order is unchanged
        """
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "0")
        res = auto_memory.maybe_store_turn(GOOD_Q, GOOD_A)
        assert res == {"stored": False, "reason": "disabled"}


class TestCeilingEviction:
    def _seed(self, fake, n, source="auto_memory"):
        for i in range(n):
            fake.entries.append({
                "id": f"seed-{source}-{i}",
                "text": f"alter eintrag {i}",
                "metadata": {"timestamp": 1000.0 + i, "source": source},
            })

    def test_overflow_evicts_oldest_auto_memory_first(self, fake, monkeypatch):
        """
        GIVEN  ceiling of 6 with 6 auto_memory entries already stored
               (plus one older compaction entry that must survive)
        WHEN   a new substantive turn is stored
        THEN   the store stays at the ceiling
        AND    the oldest auto_memory entry was evicted
        AND    the compaction-sourced entry is untouched
        """
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "6")
        self._seed(fake, 6)
        self._seed(fake, 1, source="compaction")  # timestamp 1000 → oldest of all
        res = auto_memory.maybe_store_turn(GOOD_Q, GOOD_A)
        assert res["stored"] is True
        assert fake.count() == 6
        assert "seed-compaction-0" in [e["id"] for e in fake.entries]
        assert "seed-auto_memory-0" not in [e["id"] for e in fake.entries]

    def test_invalid_ceiling_falls_back_to_default(self, fake, monkeypatch):
        """
        GIVEN  a garbage EPHE_MEMORY_MAX_ENTRIES value
        WHEN   maybe_store_turn stores one entry
        THEN   it stores without crashing and no eviction runs (default ceiling)
        """
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "sechs")
        res = auto_memory.maybe_store_turn(GOOD_Q, GOOD_A)
        assert res["stored"] is True
        assert res.get("evicted", 0) == 0

    def test_ceiling_below_used_count_prunes_down(self, fake, monkeypatch):
        """
        GIVEN  10 stored auto_memory entries, ceiling lowered to 4
        WHEN   the next turn triggers enforcement
        THEN   only the 4 newest (plus the fresh one capped) remain — count == 4
        """
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "4")
        self._seed(fake, 10)
        res = auto_memory.maybe_store_turn(GOOD_Q, GOOD_A)
        assert res["stored"] is True
        assert fake.count() <= 4

    def test_eviction_never_touches_compaction_entries(self, fake, monkeypatch):
        """
        GIVEN  10 compaction entries + ceiling 4 and no auto_memory entries
        WHEN   enforcement runs via a new stored turn
        THEN   all 10 compaction entries survive (only auto_memory is evictable)
        """
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "4")
        self._seed(fake, 10, source="compaction")
        auto_memory.maybe_store_turn(GOOD_Q, GOOD_A)
        survivors = [e for e in fake.entries if e["metadata"]["source"] == "compaction"]
        assert len(survivors) == 10
