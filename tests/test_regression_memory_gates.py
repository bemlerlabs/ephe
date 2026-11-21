"""The auto-memory entry gates and the eviction ceiling, pinned.

The failure-path suite covers stores that are away or corrupt. What no test held
is the other half of the same promise: which turns never reach the store at all
(the kill switch, the micro answer, the artifact marker, a refusal answer) and
which entries the ceiling may take. The compactor's backups must survive every
trim, so a regression that evicts them would erase knowledge no copy keeps.
"""
from __future__ import annotations

import core.auto_memory as am

GOOD_Q = "How should I build the FastAPI lifespan for the scheduler?"
GOOD_A = (
    "Start the scheduler on the event loop inside the lifespan context, because "
    "AsyncIOScheduler needs the same thread that owns the loop to run at all."
)


class _Store:
    """Minimal store surface; entries is the whole corpus the ceiling sees."""

    def __init__(self, entries):
        self.entries = [dict(e) for e in entries]

    def search(self, text, top_k=3):
        return []

    def store(self, text, metadata=None):
        self.entries.append({"id": f"new-{len(self.entries)}", "metadata": metadata or {}})

    def count(self):
        return len(self.entries)

    def list_all(self, limit=100):
        return [dict(e) for e in self.entries[:limit]]

    def delete(self, doc_id):
        self.entries = [e for e in self.entries if e["id"] != doc_id]


def _use(monkeypatch, store):
    monkeypatch.setattr(am, "_memory_factory", lambda: store)
    monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
    return store


class TestTheKillSwitchStopsCapture:
    def test_the_environment_zero_wins(self, monkeypatch):
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "0")
        assert am.capture_enabled() is False

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)
        assert res == {"stored": False, "reason": "disabled"}


class TestTurnsThatNeverReachTheStore:
    def test_a_micro_answer_is_too_short_to_keep(self, monkeypatch):
        _use(monkeypatch, _Store([]))
        res = am.maybe_store_turn(GOOD_Q, "ok")
        assert res["stored"] is False
        assert res["reason"] == "too-short"

    def test_a_micro_question_is_too_short_to_keep(self, monkeypatch):
        _use(monkeypatch, _Store([]))
        res = am.maybe_store_turn("Hi", GOOD_A)
        assert res["stored"] is False
        assert res["reason"] == "too-short"

    def test_an_artifact_answer_is_kept_by_the_library(self, monkeypatch):
        _use(monkeypatch, _Store([]))
        answer = (
            "The deck is ready and was saved as _FILE:deck.pptx in the artifacts "
            "folder, so you can open the slides from there whenever you like."
        )
        res = am.maybe_store_turn(GOOD_Q, answer)
        assert res["stored"] is False
        assert res["reason"] == "artifact"

    def test_a_refusal_answer_never_enters_the_memory(self, monkeypatch):
        _use(monkeypatch, _Store([]))
        answer = (
            "I cannot help with that request right now, because the service it "
            "would need is not running in this session and answers would be partial."
        )
        res = am.maybe_store_turn(GOOD_Q, answer)
        assert res["stored"] is False
        assert res["reason"] == "low-value"

    def test_an_error_prefixed_answer_never_enters_the_memory(self, monkeypatch):
        _use(monkeypatch, _Store([]))
        answer = (
            "error: the provider closed the connection before an answer arrived, "
            "so nothing durable was produced for this turn at all."
        )
        res = am.maybe_store_turn(GOOD_Q, answer)
        assert res["stored"] is False
        assert res["reason"] == "low-value"

    def test_a_symbol_salad_question_never_enters_the_memory(self, monkeypatch):
        _use(monkeypatch, _Store([]))
        res = am.maybe_store_turn("!!!!!!!!!!!!!!!!", GOOD_A)
        assert res["stored"] is False
        assert res["reason"] == "low-value"


def _corpus():
    return [
        {"id": "c1", "metadata": {"source": "compaction", "priority": "low", "timestamp": 1}},
        {"id": "c2", "metadata": {"source": "compaction", "priority": "medium", "timestamp": 2}},
        {"id": "a-low", "metadata": {"source": "auto_memory", "priority": "low", "timestamp": 3}},
        {"id": "a-mid", "metadata": {"source": "auto_memory", "priority": "medium", "timestamp": 4}},
        {"id": "a-high", "metadata": {"source": "auto_memory", "priority": "high", "timestamp": 5}},
    ]


class TestTheCeilingNeverTakesACompactorBackup:
    def test_the_trim_takes_the_least_valuable_learned_entries_first(self, monkeypatch):
        store = _use(monkeypatch, _Store(_corpus()))
        monkeypatch.setattr(am, "_max_entries", lambda: 3)

        removed = am._enforce_ceiling(store)

        assert removed == 2
        ids = {e["id"] for e in store.entries}
        assert {"c1", "c2"} <= ids
        assert "a-high" in ids
        assert "a-low" not in ids and "a-mid" not in ids

    def test_a_stored_turn_trims_to_the_ceiling_without_losing_a_backup(self, monkeypatch):
        store = _use(monkeypatch, _Store(_corpus()))
        monkeypatch.setattr(am, "_max_entries", lambda: 3)

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is True
        assert res["evicted"] == 3
        ids = {e["id"] for e in store.entries}
        assert {"c1", "c2"} <= ids
        assert "a-high" in ids

    def test_below_the_ceiling_nothing_is_taken(self, monkeypatch):
        store = _use(monkeypatch, _Store(_corpus()))
        monkeypatch.setattr(am, "_max_entries", lambda: 99)

        assert am._enforce_ceiling(store) == 0
        assert len(store.entries) == 5


class TestTheCeilingControlIsRead:
    def test_the_environment_cap_is_read_when_no_explicit_control_is_set(self, monkeypatch):
        monkeypatch.setattr("core.engine_config.read_generation_explicit", lambda: {})
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "12")
        assert am._max_entries() == 12

    def test_a_junk_cap_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setattr("core.engine_config.read_generation_explicit", lambda: {})
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "not-a-number")
        assert am._max_entries() == 1000

    def test_a_non_positive_cap_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setattr("core.engine_config.read_generation_explicit", lambda: {})
        monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "0")
        assert am._max_entries() == 1000
