"""G7: memory provenance — a run records the facts it was built from.

The gap this closes: injection used to be an anonymous tail block. The system
prompt carried the facts, but nothing recorded *which* entries a given turn had
used, so a user could correct a memory yet never see why the agent had believed
anything. Here the injection is a query with a result set, and the run's record
(the trajectory turn) keeps it.

Pins:
1. ``Memory.get_injection`` returns the block AND the rows it was built from, in
   the same order; the string door is the block alone (no drift between them).
2. The similarity floor is a wall in both directions: an entry under it is in
   neither the block nor the provenance — never a fact the model never saw.
3. ``trajectory.record_memories`` writes on the live turn, is deduped and capped,
   survives ``end_turn`` into the history, round-trips through the snapshot, and
   is a no-op where there is no live turn.
4. Integration: assembling a prompt with a session records exactly the entries
   ``get_injection`` lifted.
5. Surface: ``GET /api/trajectory?session=`` carries the facts.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import trajectory  # noqa: E402
from core.memory import InjectionResult, Memory  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "ephe-home"))
    trajectory.reset_for_test()
    yield
    trajectory.reset_for_test()


def _mem(tmp_path, name="prov") -> Memory:
    return Memory(persist_dir=str(tmp_path / "chroma"), collection_name=name)


# 1. the result set

def test_injection_is_a_query_with_a_result_set(tmp_path):
    """The block and the rows describe the same facts, in the same order."""
    mem = _mem(tmp_path)
    mem.store("The user works on an AI assistant named Ephe.", {"source": "auto_memory"})

    inj = mem.get_injection("Ephe AI assistant")
    assert isinstance(inj, InjectionResult)
    assert inj.entries, "a hit above the floor has to appear in the result set"

    entry = inj.entries[0]
    assert set(entry) == {"id", "text", "score", "source"}
    assert entry["id"], "without an id nobody can correct the entry later"
    assert entry["text"] in inj.block, "the line was written from exactly this entry"
    assert entry["source"] == "auto_memory"
    assert isinstance(entry["score"], float)

    # block lines == entries + the two frame lines: nothing hidden, nothing extra
    bullets = [ln for ln in inj.block.splitlines() if ln.startswith("• ")]
    assert len(bullets) == len(inj.entries)
    for e in inj.entries:
        assert f"• {e['text']}" in bullets


def test_string_door_is_the_same_block(tmp_path):
    """`get_context_injection` is the block alone — the two doors cannot drift."""
    mem = _mem(tmp_path)
    mem.store("The user's favourite colour is blue.", {"source": "test"})

    inj = mem.get_injection("colour")
    assert inj.block == mem.get_context_injection("colour")
    assert inj.block  # non-empty here, so the equality is not two empties


# 2. the floor is a wall in both directions

def test_the_floor_also_gates_the_result_set(tmp_path, monkeypatch):
    mem = _mem(tmp_path)
    mem.store("The user works on an AI assistant named Ephe.", {"source": "test"})

    monkeypatch.setattr("core.memory.inject_min_score", lambda: 1.1)
    under = mem.get_injection("Ephe")
    assert under.block == ""
    assert under.entries == [], "an entry under the floor never reached the model"

    monkeypatch.setattr("core.memory.inject_min_score", lambda: 0.0)
    over = mem.get_injection("Ephe")
    assert over.block and over.entries


def test_an_empty_store_invents_no_provenance(tmp_path):
    mem = _mem(tmp_path, name="empty")
    inj = mem.get_injection("anything")
    assert inj.block == "" and inj.entries == []


# 3. the run's record

def test_record_memories_writes_on_the_running_turn(tmp_path):
    trajectory.begin_turn("s1", model="m", turn_id="t1")
    trajectory.record("s1", {"type": "user", "text": "What is my name?"})

    trajectory.record_memories("s1", [{"id": "a", "text": "Name: Test User", "score": 0.9, "source": "agent"}])

    live = trajectory.get_turns("s1")
    assert live[0]["memories"] == [
        {"id": "a", "text": "Name: Test User", "score": 0.9, "source": "agent"}
    ]

    trajectory.end_turn("s1")
    hist = trajectory.get_turns("s1")
    assert hist[0]["memories"][0]["id"] == "a", "the provenance outlives the end of the turn"
    assert hist[0]["turn_id"] == "t1"


def test_record_memories_dedupes_and_caps(tmp_path):
    trajectory.begin_turn("s2", model="m")
    trajectory.record("s2", {"type": "user", "text": "x"})

    first = [{"id": "a", "text": "A", "score": 0.5, "source": "s"}]
    trajectory.record_memories("s2", first)
    trajectory.record_memories("s2", first)  # a second assembly of the same prompt
    assert len(trajectory.get_turns("s2")[0]["memories"]) == 1, "the same id twice is a bug"

    many = [{"id": f"m{i}", "text": f"T{i}", "score": 0.5, "source": "s"}
            for i in range(trajectory.MAX_MEMORIES_PER_TURN + 10)]
    trajectory.record_memories("s2", many)
    assert len(trajectory.get_turns("s2")[0]["memories"]) == trajectory.MAX_MEMORIES_PER_TURN


def test_record_memories_without_a_live_turn_is_a_noop(tmp_path):
    trajectory.begin_turn("s3", model="m")
    trajectory.end_turn("s3")
    # the turn is closed; a late assembly must not resurrect it or raise
    trajectory.record_memories("s3", [{"id": "a", "text": "A", "score": 0.5, "source": "s"}])
    assert trajectory.get_turns("s3")[0]["memories"] == []
    trajectory.record_memories("unknown", [{"id": "a", "text": "A", "score": 0.5, "source": "s"}])
    assert trajectory.get_turns("unknown") == []


def test_record_memories_drops_entries_without_an_id(tmp_path):
    """A row nobody can correct is not provenance — it is dropped, not stored."""
    trajectory.begin_turn("s4", model="m")
    trajectory.record("s4", {"type": "user", "text": "x"})
    trajectory.record_memories(
        "s4",
        [
            {"id": "", "text": "no handle", "score": 0.9, "source": "s"},
            {"text": "not a dict", "score": 0.9},
            {"id": "keep", "text": "with a handle", "score": 0.9, "source": "s"},
        ],
    )
    memories = trajectory.get_turns("s4")[0]["memories"]
    assert [m["id"] for m in memories] == ["keep"]


def test_snapshot_roundtrip_keeps_the_provenance(tmp_path, monkeypatch):
    trajectory.begin_turn("s5", model="m", turn_id="t5")
    trajectory.record("s5", {"type": "user", "text": "x"})
    trajectory.record_memories("s5", [{"id": "z", "text": "Fact Z", "score": 0.7, "source": "k"}])
    trajectory.end_turn("s5")

    trajectory.reset_for_test()
    turns = trajectory.get_turns("s5")
    assert turns[0]["memories"] == [
        {"id": "z", "text": "Fact Z", "score": 0.7, "source": "k"}
    ], "a restart must not delete the reason an answer read the way it did"


# 4. integration: the prompt assembly records what it lifted

class _FakeMemory:
    @classmethod
    def has_persisted_memory(cls) -> bool:
        return True

    def get_injection(self, query: str, max_entries: int | None = None) -> InjectionResult:
        return InjectionResult(
            block="\n--- Relevant context from your memory ---\n• Name: Test User\n--- End of memory context ---\n",
            entries=[{"id": "a", "text": "Name: Test User", "score": 0.91, "source": "agent"}],
        )


def test_prompt_assembly_writes_the_provenance_on_the_turn(tmp_path, monkeypatch):
    from core import chat_prompt

    monkeypatch.setattr(chat_prompt, "Memory", _FakeMemory)
    trajectory.begin_turn("s6", model="m", turn_id="t6")
    trajectory.record("s6", {"type": "user", "text": "What is my name?"})
    messages = [{"role": "user", "content": "What is my name?"}]

    chat_prompt._assemble_system_prompt_into(
        messages, "m", None, None, session_id="s6", turn_id="t6"
    )

    assert messages[0]["role"] == "system"
    assert "Name: Test User" in messages[0]["content"], "the block is in the prompt"
    assert trajectory.get_turns("s6")[0]["memories"] == [
        {"id": "a", "text": "Name: Test User", "score": 0.91, "source": "agent"}
    ], "and exactly these facts stand on the turn"


def test_prompt_assembly_without_a_session_invents_no_provenance(tmp_path, monkeypatch):
    from core import chat_prompt

    monkeypatch.setattr(chat_prompt, "Memory", _FakeMemory)
    messages = [{"role": "user", "content": "What is my name?"}]

    chat_prompt._assemble_system_prompt_into(messages, "m", None, None)

    assert "Name: Test User" in messages[0]["content"], "the block is still injected"
    assert trajectory.get_turns("") == [], "without a session there is no turn to label"


def test_react_loop_forwards_the_session(monkeypatch):
    """REST runs go through react_loop: it has to hand the session on, or the
    turn it opens records nothing about what was injected."""
    import core.react as react

    seen: dict = {}

    async def fake_chat_with_tools(**kwargs):
        seen.update(kwargs)
        return "ok"

    async def fake_reflect(**kwargs):
        return react.ReflexionResult(needs_revision=False)

    monkeypatch.setattr(react, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(react, "reflect", fake_reflect)

    asyncio.run(react.react_loop(question="hi", model="m", session_id="sess", turn_id="t"))

    assert seen.get("session_id") == "sess"
    assert seen.get("turn_id") == "t"


# 5. the surface

def test_trajectory_route_carries_the_facts(tmp_path):
    from server.routes.trajectory import get_trajectory

    trajectory.begin_turn("api", model="m", turn_id="t-api")
    trajectory.record("api", {"type": "user", "text": "x"})
    trajectory.record_memories("api", [{"id": "a", "text": "Fact A", "score": 0.8, "source": "s"}])
    trajectory.end_turn("api")

    payload = asyncio.run(get_trajectory(session="api"))
    turn = payload["turns"][0]
    assert turn["turn_id"] == "t-api"
    assert turn["memories"] == [{"id": "a", "text": "Fact A", "score": 0.8, "source": "s"}]
