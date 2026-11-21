"""Memory failure paths, second expansion: writers that race and writes that
tear.

Scope: the file-backed writers of the memory subsystem that the first
failure-path suite (`tests/test_memory_failure_paths.py`) does not cover — the
correction journal (`core/corrections.py`), the feedback example store
(`core/feedback.py`), the compaction checkpoint (`core/compaction_memory.py`)
and the process singleton in `core/memory.py`.

Two classes of crash are named here. A *torn write* is one whose bytes reach
the disk but never complete (a kill, a full disk): what a reader must find
afterwards decides whether a whole file is lost. A *racing writer* is a second
thread entering the same read-modify-write or the same lazy construction while
the first is still inside it. Every store is local — no network, no Chroma, no
Kepta, no real ``~/.ephe``.

Where a class docstring says "hole", the test failed before the small fix that
ships with it (the failure is the proof); the other tests pin behaviour that was
already correct, so a regression is caught here instead of in production.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

import core.compaction_memory as cm
import core.corrections as corrections
import core.engine_config as engine_config
import core.feedback as feedback
import core.memory as memory
import core.memory_provider as memory_provider
from core.corrections import CorrectionJournal
from core.feedback import FeedbackStore


def _history(pairs: int = 20) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": "sys"}]
    for i in range(pairs):
        out.append({"role": "user", "content": f"Question {i} about the project"})
        out.append({"role": "assistant", "content": f"Answer {i} with details."})
    return out


def _crash_on_write(monkeypatch, predicate, partial: str) -> None:
    """Make ``Path.write_text`` land a truncated payload then die, for every
    path ``predicate`` accepts. The partial bytes stay on disk, which is what a
    kill between two writes of the same file leaves behind."""
    real = Path.write_text

    def fake(self, data, encoding=None, errors=None, newline=None):
        if predicate(self):
            real(self, partial, encoding="utf-8")
            raise OSError("simulated crash mid-write")
        return real(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", fake)


class _FakeProvider:
    """The smallest provider surface ``Memory.__init__`` touches."""

    def __init__(self) -> None:
        self.closed = False

    def count(self) -> int:
        return 0

    def close(self) -> None:
        self.closed = True


# core/corrections.py — the journal file under a torn write and forged text


class TestJournalPartialWrite:
    """Holes: ``add`` rewrote the journal in place, so a crash mid-write
    truncated every entry it held; and a correction whose text carried a line
    break wrote a second entry, dropping the real one on the next read."""

    def test_a_torn_write_keeps_the_existing_entries(self, tmp_path, monkeypatch) -> None:
        """GIVEN a journal with one entry on disk
        WHEN  the next add() tears while writing the file
        THEN  the entry already there is still readable afterwards — the file
              is swapped in, never truncated in place."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        journal.add("old wrong", "old correct")

        _crash_on_write(
            monkeypatch,
            lambda p: p.name == "corrections.md",
            "## 2026-01-01 00:00:00\n**Falsch beh",
        )
        try:
            journal.add("new wrong", "new correct")
        except OSError:
            pass  # a build that wrote in place would raise; the check below is the point

        assert ("old wrong", "old correct") in [
            (c.wrong, c.correct) for c in journal.get_recent(10)
        ]

    def test_a_value_with_a_line_break_cannot_forge_an_entry(self, tmp_path) -> None:
        """GIVEN a correction whose text embeds a separator and the field markers
        WHEN  it is stored and read back
        THEN  no fabricated entry appears and the real correction survives as a
              single entry."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        journal.add("real wrong", "real correct")
        journal.add(
            "bad claim\n---\n## 2026-01-01 00:00:00\n"
            "**Falsch behauptet:** injected\n**Korrekt:** injected",
            "the fix",
        )

        parsed = [(c.wrong, c.correct) for c in journal.get_recent(10)]

        assert ("injected", "injected") not in parsed
        assert ("real wrong", "real correct") in parsed
        assert any(w.startswith("bad claim") and c == "the fix" for w, c in parsed)

    def test_a_value_cannot_pre_empt_the_correct_field(self, tmp_path) -> None:
        """GIVEN a correction whose text carries the correct-field marker
        WHEN  it is stored and read back
        THEN  the ``correct`` field holds the real fix, not the embedded marker."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")

        journal.add("claim\n**Korrekt:** HIJACK", "the real fix")

        assert journal.get_recent(1)[0].correct == "the real fix"

    def test_a_torn_trailing_block_keeps_the_complete_entries(self, tmp_path) -> None:
        """GIVEN a journal whose last block was cut off by a crash
        WHEN  it is read
        THEN  the complete entries still parse — the torn tail costs itself."""
        journal = CorrectionJournal(path=tmp_path / "corrections.md")
        journal.path.write_text(
            "## 2026-01-01 00:00:00\n**Falsch behauptet:** a\n**Korrekt:** b\n---\n"
            "## 2026-01-02 00:00:00\n**Falsch beh",
            encoding="utf-8",
        )

        assert [(c.wrong, c.correct) for c in journal.get_recent(10)] == [("a", "b")]


# core/feedback.py — the example store under a torn write and two writers


class TestFeedbackExampleWrites:
    """Hole: ``_save`` wrote each example straight into its ``*.json`` name, so
    a torn write left a file that ``_load_from`` skips while ``_count`` still
    counts it — a phantom example the surface reports and never returns."""

    def test_a_torn_write_leaves_no_counted_but_unreadable_example(
        self, tmp_path, monkeypatch
    ) -> None:
        """GIVEN a feedback store and an example write that tears
        WHEN  the write is attempted
        THEN  nothing is counted that cannot also be read back (``count_good``
              equals the number of readable examples) and no partial file is
              left behind."""
        base = tmp_path / "feedback"
        store = FeedbackStore(base_dir=base)
        good_dir = base / "good_examples"

        _crash_on_write(
            monkeypatch,
            lambda p: p.name.endswith(".json") and p.parent == good_dir,
            '{"prompt": "x", "resp',
        )
        store.thumbs_up("a prompt", "an answer")

        assert store.count_good() == len(store.get_good_examples(max_items=1000))
        leftovers = list(good_dir.glob("*.tmp")) if good_dir.exists() else []
        assert leftovers == []

    def test_a_successful_write_leaves_one_file_and_no_temp(self, tmp_path) -> None:
        """GIVEN a feedback store
        WHEN  an example is stored
        THEN  exactly one readable ``*.json`` exists and the temp file is gone."""
        base = tmp_path / "feedback"
        store = FeedbackStore(base_dir=base)

        assert store.thumbs_up("a prompt", "an answer") is True

        good_dir = base / "good_examples"
        assert len(list(good_dir.glob("*.json"))) == 1
        assert list(good_dir.glob("*.tmp")) == []
        assert store.get_good_examples(max_items=1)[0].prompt == "a prompt"

    def test_two_writers_lose_no_example(self, tmp_path) -> None:
        """GIVEN two threads storing distinct examples at the same time
        WHEN  both finish
        THEN  every example is on disk and every one of them is readable."""
        store = FeedbackStore(base_dir=tmp_path / "feedback")
        per_writer = 25

        def writer(tag: str) -> None:
            for i in range(per_writer):
                store.thumbs_up(f"prompt {tag}-{i}", f"answer {tag}-{i}")

        threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)

        assert store.count_good() == 2 * per_writer
        assert len(store.get_good_examples(max_items=10_000)) == 2 * per_writer


# core/memory.py — the process singleton built by two threads at once


class TestMemorySingletonConstruction:
    """Hole: ``Memory.__new__`` publishes the scoped instance into ``_SCOPED``
    before ``__init__`` runs, so two threads calling ``Memory()`` together both
    reached the provider build; the second overwrote ``self._provider`` and
    leaked the first (a Chroma client or an open Kepta file)."""

    @pytest.fixture()
    def fake_provider(self, monkeypatch):
        built: list[int] = []
        entered = threading.Event()

        def fake_open(*args, **kwargs):
            built.append(1)
            entered.set()
            time.sleep(0.4)  # the expensive client build the singleton exists to avoid
            return _FakeProvider()

        monkeypatch.setattr(memory_provider, "resolve_provider", lambda **k: ("chroma", "test"))
        monkeypatch.setattr(memory_provider, "open_provider", fake_open)
        monkeypatch.setattr(engine_config, "workspace_hash", lambda: "extra2-scope")
        memory.Memory.reset_scoped_instances()
        try:
            yield built, entered
        finally:
            memory.Memory.reset_scoped_instances()

    def test_concurrent_construction_builds_the_provider_once(self, fake_provider) -> None:
        """GIVEN two threads that call Memory() together for one workspace
        WHEN  both calls return
        THEN  they hold the same object and the provider was built exactly once."""
        built, entered = fake_provider
        results: list = []

        first = threading.Thread(target=lambda: results.append(memory.Memory()))
        first.start()
        assert entered.wait(5), "the first build must start"
        second = threading.Thread(target=lambda: results.append(memory.Memory()))
        second.start()
        first.join(10)
        second.join(10)

        assert len(results) == 2
        assert results[0] is results[1]
        assert len(built) == 1, "a racing caller must not build a second provider"

    def test_an_explicit_memory_bypasses_the_singleton(self, monkeypatch, tmp_path) -> None:
        """GIVEN the scoped singleton already cached
        WHEN  Memory() is called with an explicit argument
        THEN  it returns a different object (the cache is keyed on the no-arg
              call only)."""
        monkeypatch.setattr(memory_provider, "resolve_provider", lambda **k: ("chroma", "test"))
        monkeypatch.setattr(memory_provider, "open_provider", lambda *a, **k: _FakeProvider())
        memory.Memory.reset_scoped_instances()
        try:
            scoped = memory.Memory()
            explicit = memory.Memory(persist_dir=str(tmp_path / "db"))
            assert scoped is not explicit
        finally:
            memory.Memory.reset_scoped_instances()


# core/compaction_memory.py — the checkpoint temp file


class TestCheckpointTempFile:
    """The checkpoint writer already swaps a temp file in; these pin the
    invariants a torn write relies on."""

    def test_a_stale_temp_file_does_not_change_the_checkpoint(self, tmp_path) -> None:
        """GIVEN a partial ``.tmp`` left by an earlier crash
        WHEN  preservation runs and writes the checkpoint
        THEN  the checkpoint is correct and the stale temp file is gone."""
        checkpoint = tmp_path / cm.CHECKPOINT_FILENAME
        stale = tmp_path / (cm.CHECKPOINT_FILENAME + ".tmp")
        stale.write_text('{"sess": 1, "part', encoding="utf-8")

        stored = cm.preserve_compacted_pairs(
            "sess",
            messages=_history(20),
            sink=lambda user, answer: {"stored": True},
            path=checkpoint,
            keep_recent=2,
        )

        assert stored > 0
        assert json.loads(checkpoint.read_text(encoding="utf-8"))["sess"] == stored
        assert list(tmp_path.glob("*.tmp")) == []


def test_the_journal_uses_a_swap_not_an_in_place_write(tmp_path, monkeypatch) -> None:
    """Pin: ``add`` must not touch the final path directly, so a reader never
    opens a half-written journal."""
    journal = CorrectionJournal(path=tmp_path / "corrections.md")
    journal.add("old wrong", "old correct")

    touched: list[str] = []
    real = Path.write_text

    def record(self, data, encoding=None, errors=None, newline=None):
        if self.name == "corrections.md":
            touched.append(self.name)
        return real(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", record)
    journal.add("new wrong", "new correct")

    assert touched == [], "the final journal path is only reached through os.replace"


def test_corrections_one_line_collapses_breaks() -> None:
    """Pin: the entry format is one field per line, so a value is flattened."""
    assert corrections._one_line("a\r\nb\n\nc") == "a b c"
    assert corrections._one_line("  spaced  ") == "spaced"
