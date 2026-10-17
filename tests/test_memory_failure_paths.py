"""Quality gate: the memory subsystem's failure paths — store away, corrupt
storage, two writers at once.

Scope: ``core/auto_memory.py`` (maybe_store_turn), ``core/compaction_memory.py``
(preserve_compacted_pairs), ``core/corrections.py`` (CorrectionJournal) and the
journal's production write path (``POST /api/feedback/thumbs_down``).

A production user hits these paths whenever the brain is not answering (Kepta
instance down, bridge port closed, provider config broken), when a single
corrupted row or file is in the way, or when two writers touch the same file.

Every store is mocked — no network, no Chroma/Kepta, no real ``~/.ephe``.
Where a class docstring says "hole", the test failed before the small fix that
ships with it (the failure is the proof); the other tests pin behaviour that
was already correct so a regression is caught here instead of in production.

The refusal shape under test is the reason-code pattern of ``maybe_store_turn``:
``{"stored": False, "reason": <code>}`` with the deliberate codes
``disabled | too-short | artifact | low-value | duplicate`` and the
store-failure code ``error: <exc>``. An unreachable store is its own answer —
it must never be represented as "nothing to do" (the same rule as
``server/routes/memory.py::_unavailable``: 503 + ``upstream_error``).
"""
from __future__ import annotations

import asyncio
import json
import threading

import pytest

import core.auto_memory as am
import core.compaction_memory as cm
import core.multi_session as ms
from core.corrections import CorrectionJournal

GOOD_Q = "How should I build the FastAPI lifespan for the scheduler?"
GOOD_A = (
    "Start the scheduler directly on the event loop in the lifespan context, "
    "not in a worker thread — AsyncIOScheduler needs a running loop in the "
    "calling thread, otherwise the error is just swallowed."
)

STORE_DOWN = "kepta-bridge closed"


def _history(pairs: int = 20) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": "sys"}]
    for i in range(pairs):
        out.append({"role": "user", "content": f"Question {i} about the project"})
        out.append({"role": "assistant", "content": f"Answer {i} with details."})
    return out


class _FakeMemory:
    """Tiny store surface; ``raise_on`` simulates the store being unreachable."""

    def __init__(self, hits: list | None = None, raise_on: tuple[str, ...] = ()) -> None:
        self.hits = hits if hits is not None else []
        self.raise_on = set(raise_on)
        self.stored: list[dict] = []

    def search(self, text: str, top_k: int = 3):
        if "search" in self.raise_on:
            raise RuntimeError(STORE_DOWN)
        return self.hits

    def store(self, text: str, metadata: dict | None = None) -> None:
        if "store" in self.raise_on:
            raise RuntimeError(STORE_DOWN)
        self.stored.append({"text": text, "metadata": metadata or {}})

    def count(self) -> int:
        if "count" in self.raise_on:
            raise RuntimeError(STORE_DOWN)
        return len(self.stored)

    def list_all(self, limit: int = 100) -> list[dict]:
        return []

    def delete(self, doc_id: str) -> None:
        return None


@pytest.fixture()
def fake_memory(monkeypatch):
    mem = _FakeMemory()
    monkeypatch.setattr(am, "_memory_factory", lambda: mem)
    monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
    return mem


# core/auto_memory.py — maybe_store_turn


class TestAutoMemoryStoreUnavailable:
    """The store away: the turn's fact must not be lost to a crash, and the
    verdict must stay inside the reason-code pattern (no exception escapes)."""

    def test_a_store_that_cannot_be_opened_is_an_error_verdict(self, monkeypatch) -> None:
        """GIVEN a factory whose Memory() cannot be built (broken provider config)
        WHEN  a substantive turn is offered
        THEN  the verdict is stored=False with the error reason — never a raise."""
        def broken_factory():
            raise RuntimeError(STORE_DOWN)

        monkeypatch.setattr(am, "_memory_factory", broken_factory)
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is False
        assert res["reason"].startswith("error: ")
        assert STORE_DOWN in res["reason"]

    def test_a_search_outage_stores_without_dedupe(self, fake_memory) -> None:
        """GIVEN the search side of the store down but the write side answering
        WHEN  a turn is offered
        THEN  the fact is stored (dedupe degrades, the fact is not dropped)."""
        fake_memory.raise_on = {"search"}

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is True
        assert len(fake_memory.stored) == 1

    def test_a_store_outage_is_an_error_verdict(self, fake_memory) -> None:
        """GIVEN search answers empty and store raises
        WHEN  a turn is offered
        THEN  stored=False with the error reason; the caller keeps its flow."""
        fake_memory.raise_on = {"store"}

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is False
        assert res["reason"].startswith("error: ")

    def test_the_ceiling_step_is_best_effort(self, fake_memory) -> None:
        """GIVEN the store accepts the write but the ceiling count raises
        WHEN  a turn is offered
        THEN  the fact counts as stored, eviction is reported as 0 — a ceiling
              failure never un-stores a stored fact."""
        fake_memory.raise_on = {"count"}

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is True
        assert res.get("evicted", 0) == 0
        assert len(fake_memory.stored) == 1


class TestAutoMemoryCorruptEntries:
    """A single corrupt row in the search result — hole: it answered ``error:``
    for every later store, so one bad row silently blocked all writes."""

    @pytest.mark.parametrize(
        "hits",
        [
            [None],  # a non-dict row
            [{"score": None, "metadata": {"source": "auto_memory"}}],  # score null
            [{"score": "hoch", "metadata": {"source": "auto_memory"}}],  # score not a number
            [{"score": 0.95, "metadata": "garbage"}],  # metadata not a dict, score above threshold
        ],
        ids=["row-not-a-dict", "score-null", "score-not-numeric", "metadata-not-a-dict"],
    )
    def test_a_corrupt_hit_cannot_block_storing(self, fake_memory, hits) -> None:
        """GIVEN a corrupt row among the dedupe hits
        WHEN  a substantive turn is offered
        THEN  the corrupt row is skipped and the fact is stored (a bad row may
              cost one dedupe check, never the fact)."""
        fake_memory.hits = hits

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is True, res
        assert len(fake_memory.stored) == 1

    def test_a_search_returning_none_still_stores(self, fake_memory) -> None:
        """GIVEN a provider that answers None instead of a hit list
        WHEN  a turn is offered
        THEN  the fact is stored — "no answer" is not "do not store"."""
        fake_memory.search = lambda text, top_k=3: None

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res["stored"] is True, res

    def test_a_valid_duplicate_still_refuses(self, fake_memory) -> None:
        """GIVEN a well-formed above-threshold hit from a dedupe source
        WHEN  the same fact arrives
        THEN  reason duplicate — the corrupt-row guard must not disable dedupe."""
        fake_memory.hits = [{"score": 0.95, "metadata": {"source": "compaction"}}]

        res = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert res == {"stored": False, "reason": "duplicate"}
        assert fake_memory.stored == []


class TestAutoMemoryConcurrentWrites:
    def test_concurrent_identical_turns_may_duplicate_but_never_lose(self, fake_memory) -> None:
        """GIVEN two turns racing the check-then-act dedupe (both read an empty store)
        WHEN  both store
        THEN  both land — the store holds two copies (duplicate), none is lost;
              cross-call locking is out of scope for a best-effort capture."""
        first = am.maybe_store_turn(GOOD_Q, GOOD_A)
        second = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert first["stored"] is True and second["stored"] is True
        assert len(fake_memory.stored) == 2


# core/compaction_memory.py — preserve_compacted_pairs


class TestCompactionPreservationFailurePaths:
    """Checkpointed preservation while the store is away. Hole: a store that
    did not answer was counted as "preserved", the checkpoint advanced past it,
    and the pairs were lost for good."""

    def test_a_store_outage_does_not_advance_the_checkpoint(self, tmp_path, monkeypatch) -> None:
        """GIVEN the store answers {"stored": False, "reason": "error: ..."} (down)
        WHEN  the discarded pairs are offered
        THEN  nothing counts as preserved and no checkpoint is written;
              once the store answers again every pair is preserved (retry)."""
        calls: list[str] = []

        def down_sink(user, assistant, source="auto_memory"):
            calls.append(user)
            return {"stored": False, "reason": f"error: {STORE_DOWN}"}

        def up_sink(user, assistant, source="auto_memory"):
            calls.append(user)
            return {"stored": True, "evicted": 0}

        cp = tmp_path / "checkpoints.json"
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
        monkeypatch.setattr(am, "maybe_store_turn", down_sink)

        first = cm.preserve_compacted_pairs("s-down", messages=_history(), path=cp)

        assert first == 0, "a store that did not answer must not count as preserved"
        assert not cp.exists(), "no pair was preserved — no checkpoint to write"

        monkeypatch.setattr(am, "maybe_store_turn", up_sink)
        second = cm.preserve_compacted_pairs("s-down", messages=_history(), path=cp)

        assert second == 15, "after recovery every pair is preserved"
        assert json.loads(cp.read_text(encoding="utf-8"))["s-down"] == 15

    @pytest.mark.parametrize(
        "reason", ["disabled", "too-short", "artifact", "low-value", "duplicate"]
    )
    def test_deliberate_refusals_advance_the_frontier(self, tmp_path, reason) -> None:
        """GIVEN the sink deliberately refuses with a stable reason code
              (not an error)
        WHEN  the pairs are offered twice
        THEN  the refusal counts as handled (no retry storm) — only the
              "did not answer" family holds the frontier."""
        calls: list[str] = []

        def refusing(user, assistant):
            calls.append(user)
            return {"stored": False, "reason": reason}

        cp = tmp_path / "checkpoints.json"
        first = cm.preserve_compacted_pairs("s-refused", messages=_history(), sink=refusing, path=cp)
        second = cm.preserve_compacted_pairs("s-refused", messages=_history(), sink=refusing, path=cp)

        assert first == 15
        assert second == 0, "deliberate refusals are decisions, not outages"
        assert len(calls) == 15

    def test_a_raising_sink_holds_the_frontier_at_the_last_good_pair(self, tmp_path) -> None:
        """GIVEN a sink that raises on the fourth discarded pair
        WHEN  preservation runs (twice, the second time healthy)
        THEN  the checkpoint stops before the failing pair and the resumed run
              starts exactly there — the first three pairs are not re-offered."""
        stored: list[str] = []

        def sink(user, assistant):
            if user.startswith("Question 3"):
                raise RuntimeError(STORE_DOWN)
            stored.append(user)

        cp = tmp_path / "checkpoints.json"
        first = cm.preserve_compacted_pairs("s-sink-raise", messages=_history(), sink=sink, path=cp)

        assert first == 3
        assert json.loads(cp.read_text(encoding="utf-8"))["s-sink-raise"] == 3

        resumed: list[str] = []
        second = cm.preserve_compacted_pairs(
            "s-sink-raise", messages=_history(), sink=lambda u, a: resumed.append(u), path=cp
        )

        assert second == 12
        assert resumed[0].startswith("Question 3")

    def test_a_corrupt_checkpoint_file_reads_as_empty_and_represerves(self, tmp_path) -> None:
        """GIVEN a checkpoint file that is not JSON
        WHEN  preservation runs
        THEN  it reads as empty, everything is re-offered (the store-side dedupe
              catches real duplicates) and a valid checkpoint is written."""
        cp = tmp_path / "checkpoints.json"
        cp.write_text("{ not json", encoding="utf-8")
        stored: list[str] = []

        n = cm.preserve_compacted_pairs(
            "s-corrupt-json", messages=_history(), sink=lambda u, a: stored.append(u), path=cp
        )

        assert n == 15
        assert json.loads(cp.read_text(encoding="utf-8"))["s-corrupt-json"] == 15

    @pytest.mark.parametrize("value", ["corrupt", None, {"x": 1}, [1, 2]],
                             ids=["string", "null", "object", "list"])
    def test_a_corrupt_per_session_counter_is_repaired_not_fatal(self, tmp_path, value) -> None:
        """GIVEN one corrupt per-session counter (hand edit, foreign writer)
        WHEN  preservation runs
        THEN  the counter reads as 0 (re-derived from the store, dedupe catches
              the duplicates) instead of raising — a raise here is swallowed by
              the fire-and-forget caller and kills preservation for the session."""
        cp = tmp_path / "checkpoints.json"
        cp.write_text(json.dumps({"s-corrupt-counter": value}), encoding="utf-8")
        stored: list[str] = []

        n = cm.preserve_compacted_pairs(
            "s-corrupt-counter", messages=_history(), sink=lambda u, a: stored.append(u), path=cp
        )

        assert n == 15
        assert json.loads(cp.read_text(encoding="utf-8"))["s-corrupt-counter"] == 15

    def test_an_unreachable_session_store_is_zero_pairs(self, tmp_path, monkeypatch) -> None:
        """GIVEN the session store raises while loading the history
        WHEN  preservation runs without explicit messages
        THEN  the verdict is 0 and nothing is written — never a raise."""

        def down(sid):
            raise OSError("session store down")

        monkeypatch.setattr(ms, "load_messages", down)
        cp = tmp_path / "checkpoints.json"

        assert cm.preserve_compacted_pairs("s-session-down", path=cp) == 0
        assert not cp.exists()

    def test_a_checkpoint_that_cannot_be_written_is_reported_after_the_sink_ran(
        self, tmp_path
    ) -> None:
        """GIVEN a checkpoint path whose parent cannot be created (a file stands there)
        WHEN  preservation runs
        THEN  the sink side-effect already happened; the write failure surfaces
              as an OSError for the caller (which treats preservation as
              best-effort) — no data loss, only the checkpoint lags."""
        blocker = tmp_path / "blocked"
        blocker.write_text("a file, not a directory", encoding="utf-8")
        stored: list[str] = []

        with pytest.raises(OSError):
            cm.preserve_compacted_pairs(
                "s-unwritable", messages=_history(), sink=lambda u, a: stored.append(u),
                path=blocker / "checkpoints.json",
            )

        assert len(stored) == 15, "the sink ran; only the checkpoint write failed"

    def test_concurrent_checkpoint_writers_cost_rework_never_a_pair(self, tmp_path) -> None:
        """GIVEN two sessions whose checkpoint saves interleave (last write wins,
              computed from a base read before the other save)
        WHEN  the overwritten session runs again
        THEN  every pair is re-offered and refused as duplicate by the store-side
              dedupe — rework, but no pair is lost and the checkpoint self-repairs."""
        cp = tmp_path / "checkpoints.json"
        seen: set[str] = set()
        calls = 0

        def dedupe_sink(user, assistant):
            nonlocal calls
            calls += 1
            if user in seen:
                return {"stored": False, "reason": "duplicate"}
            seen.add(user)
            return {"stored": True, "evicted": 0}

        first = cm.preserve_compacted_pairs("A", messages=_history(), sink=dedupe_sink, path=cp)
        assert first == 15

        # The concurrent writer for session B saves from a base read before A's save.
        cp.write_text(json.dumps({"B": 15}), encoding="utf-8")

        second = cm.preserve_compacted_pairs("A", messages=_history(), sink=dedupe_sink, path=cp)

        assert second == 15, "all pairs re-offered"
        assert calls == 30, "the store saw them twice; the dedupe refused the copies"
        bookkeeping = json.loads(cp.read_text(encoding="utf-8"))
        assert bookkeeping["A"] == 15, "A's checkpoint repaired"
        assert bookkeeping["B"] == 15, "B's checkpoint kept"


# core/corrections.py — CorrectionJournal


class TestCorrectionsJournalFailurePaths:
    """The journal file: corrupt blocks, undecodable bytes, an unwritable store
    and two writers. Hole: an undecodable file made every read and write raise —
    the TUI caller does not catch, so corrections vanished (server) or crashed
    the turn (TUI), and a new correction was lost on top."""

    def test_malformed_blocks_are_skipped_valid_blocks_survive(self, tmp_path) -> None:
        """GIVEN a journal with one valid, one malformed and one half-block
        WHEN  it is read
        THEN  only the complete blocks parse — a corrupt entry costs itself."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        journal.path.write_text(
            "## 2026-01-01 00:00:00\n**Falsch behauptet:** a\n**Korrekt:** b\n---\n"
            "## broken\n- no fields\n---\n"
            "## 2026-01-02 00:00:00\n**Falsch behauptet:** c\n---\n"
            "## 2026-01-03 00:00:00\n**Falsch behauptet:** d\n**Korrekt:** e\n---\n",
            encoding="utf-8",
        )

        parsed = journal.get_recent(10)

        assert [(c.wrong, c.correct) for c in parsed] == [("a", "b"), ("d", "e")]

    def test_an_undecodable_journal_reads_as_empty(self, tmp_path) -> None:
        """GIVEN a journal file with invalid UTF-8 bytes (editor saved it wrong)
        WHEN  it is read
        THEN  the read degrades to empty (the corrupt-file class: empty, never
              a crash — same rule as the checkpoint and session stores)."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        journal.path.write_bytes(b"## 2026-01-01 00:00:00\n**Korrekt:** b\n---\n\xff\xfe")

        assert journal.get_recent(5) == []

    def test_a_new_correction_lands_when_the_old_file_is_undecodable(self, tmp_path) -> None:
        """GIVEN an undecodable journal and a user correction
        WHEN  add() runs
        THEN  the new correction is written (readable by get_recent) — the
              unreadable remainder must not swallow new entries."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        journal.path.write_bytes(b"\xff\xfe corrupt")

        journal.add(wrong="A=B", correct="A is not B")

        recent = journal.get_recent(1)
        assert recent and recent[0].correct == "A is not B"

    def test_an_unwritable_store_is_a_refusal_the_caller_can_see(self, tmp_path) -> None:
        """GIVEN a journal path that cannot be created (a file, not a directory)
        WHEN  add() runs
        THEN  the write raises — the feedback route relies on this raise to
              answer journal=False (an unreachable store is not an empty one)."""
        blocker = tmp_path / "blocked"
        blocker.write_text("a file, not a directory", encoding="utf-8")
        journal = CorrectionJournal(path=blocker / "corrections.md")

        with pytest.raises(OSError):
            journal.add(wrong="a", correct="b")

    def test_add_waits_while_another_writer_holds_the_journal_lock(self, tmp_path) -> None:
        """GIVEN another process holds the exclusive journal lock
        WHEN  add() runs
        THEN  it waits for the lock before its read-modify-write — the lock is
              what keeps two writers (server + TUI) from losing an entry."""
        fcntl = pytest.importorskip("fcntl")
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        lock_path = journal.path.with_suffix(journal.path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with open(lock_path, "a+", encoding="utf-8") as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
            done = threading.Event()
            worker = threading.Thread(target=lambda: (journal.add("X", "Y"), done.set()))
            worker.start()
            try:
                assert not done.wait(0.4), "add() must wait for the foreign writer's lock"
            finally:
                fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        worker.join(10)

        assert done.is_set()
        assert journal.get_recent(1)[0].correct == "Y"

    def test_parallel_adds_lose_no_entry(self, tmp_path) -> None:
        """GIVEN two writers appending at the same time (both rewrite the whole
              file newest-first)
        WHEN  they finish
        THEN  every entry is on disk — without the lock the later writer's
              read-modify-write silently drops the other one's entry."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        n = 40

        def writer(tag: str) -> None:
            for i in range(n):
                journal.add(wrong=f"{tag}-{i}", correct=f"{tag}-{i}")

        threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)

        assert len(journal.get_recent(10_000)) == 2 * n


# The journal's production write path — POST /api/feedback/thumbs_down


class TestFeedbackRouteJournalPath:
    """Hole: the route called ``add(context=..., correction=...)`` while the
    journal signature is ``add(wrong, correct)`` — every thumbs-down with a
    reason raised TypeError, was swallowed, answered ``journal: False`` (which
    no surface reads), and the correction never landed."""

    def test_a_thumbs_down_reason_reaches_the_journal(self, tmp_path, monkeypatch) -> None:
        """GIVEN the route with a real store and a real journal on disk
        WHEN  a thumbs-down with a reason arrives
        THEN  journal is True and the correction is readable from the journal."""
        import server.routes.feedback as fb
        from core.feedback import FeedbackStore

        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        monkeypatch.setattr(fb, "_get_journal", lambda: journal)
        monkeypatch.setattr(
            fb, "_get_store", lambda: FeedbackStore(base_dir=tmp_path / "feedback")
        )

        response = asyncio.run(
            fb.thumbs_down(
                fb.FeedbackRequest(
                    prompt="Was ist die Hauptstadt von Australien?",
                    response="Sydney.",
                    reason="Canberra ist die Hauptstadt",
                )
            )
        )

        assert response.saved is True
        assert response.journal is True
        recent = journal.get_recent(1)
        assert recent, "the correction must be on disk"
        assert recent[0].wrong == "Was ist die Hauptstadt von Australien?"
        assert recent[0].correct == "Avoid this in similar requests: Canberra ist die Hauptstadt"
