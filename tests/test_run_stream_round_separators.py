"""A finished run keeps its sentence groups apart across tool rounds.

The run text the user reads is assembled in ``_make_stream_callbacks``: every
streamed piece of every round lands in ``first_chunks`` and the three consumers
(live assistant frame, stored session message, memory note) each join that one
list with the empty string. Within one round the pieces are tokenizer deltas
that already carry their own spacing, so a direct join is right. The only place
a separator is owed is the boundary between rounds, where one sentence ends on a
period and the next begins on a capital letter. These tests drive the assembler,
then read what a real route turn persists and what the memory writer stores.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.routes.chat import _make_stream_callbacks

ROUND_ONE = ("I'll", " look", " for", " your", " numbers", " before", " I", " build", " anything.")
ROUND_TWO = ("Workspace", " listing", " is", " in.")
ROUND_THREE = ("No", " numbers", " found.", " I", " stopped", " here.")
EXPECTED_RUN = (
    "I'll look for your numbers before I build anything.\n\n"
    "Workspace listing is in.\n\n"
    "No numbers found. I stopped here."
)


def _drive_two_tool_rounds():
    events: list[dict] = []
    first_chunks: list[str] = []
    on_chunk, _on_thinking, on_start, on_done, _on_phase = _make_stream_callbacks(
        events.append, first_chunks, [], "sep-session", "sep-turn"
    )
    for piece in ROUND_ONE:
        on_chunk(piece)
    on_start("list_files", {"path": "."}, "call-1")
    on_done("list_files", "the listing arrived", "call-1")
    for piece in ROUND_TWO:
        on_chunk(piece)
    on_start("read_file", {"path": "notes.txt"}, "call-2")
    on_done("read_file", "no figures inside", "call-2")
    for piece in ROUND_THREE:
        on_chunk(piece)
    return events, "".join(first_chunks)


def test_round_boundaries_keep_a_paragraph_break():
    _events, answer = _drive_two_tool_rounds()
    assert answer == EXPECTED_RUN


def test_no_separator_is_invented_inside_a_round():
    _events, answer = _drive_two_tool_rounds()
    assert answer.count("\n\n") == 2
    assert "build anything.\nWorkspace" not in answer
    assert "listing is.\nNo numbers" not in answer


def test_live_chunk_frames_match_the_assembled_text():
    events, answer = _drive_two_tool_rounds()
    streamed = "".join(e["data"] for e in events if e["type"] == "chunk")
    assert streamed == answer


@pytest.fixture
def sessions_root(tmp_path, monkeypatch):
    from core import multi_session as ms

    root = tmp_path / "sessions"
    monkeypatch.setattr(ms, "SESSIONS_DIR", root)
    monkeypatch.setattr(ms, "REGISTRY_FILE", root / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", root / "default.json")
    return root


@pytest.fixture
def route_client(tmp_path):
    os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    from server.main import create_app

    return TestClient(create_app())


def test_a_route_run_stores_the_round_break_in_the_session_message(route_client, sessions_root):
    """The stored message is read back from the session file on disk."""
    from core.react import ReflexionResult

    async def fake_chat_with_tools(*, on_chunk, on_tool_start, **_kwargs):
        for piece in ROUND_ONE:
            on_chunk(piece)
        on_tool_start("list_files", {"path": "."}, "c1")
        for piece in ROUND_TWO:
            on_chunk(piece)
        on_tool_start("read_file", {"path": "x"}, "c2")
        for piece in ROUND_THREE:
            on_chunk(piece)

    with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), patch(
        "server.routes.chat.reflect",
        new=AsyncMock(return_value=ReflexionResult(needs_revision=False, reason="ok")),
    ):
        with route_client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "Find my numbers", "model": "gemma4:e4b", "session_id": "sep-run"},
        ) as response:
            "".join(response.iter_text())

    assert response.status_code == 200
    data = json.loads((sessions_root / "rest-sep-run.json").read_text(encoding="utf-8"))
    assistant = [m for m in data if m["role"] == "assistant"][-1]
    assert assistant["content"] == EXPECTED_RUN


def test_the_memory_note_stores_the_round_break(monkeypatch):
    """The second consumer, the auto-memory Q/A note, keeps the interior break."""
    from core import auto_memory

    captured: list[str] = []

    class FakeMem:
        def search(self, _query, top_k=8):
            return []

        def store(self, text, metadata=None):
            captured.append(text)

        def count(self):
            return len(captured)

    monkeypatch.setattr(auto_memory, "_memory_factory", lambda: FakeMem())
    monkeypatch.setattr(auto_memory, "capture_enabled", lambda: True)
    monkeypatch.setattr(auto_memory, "min_answer_chars", lambda: 0)
    monkeypatch.setattr(auto_memory, "_is_low_value", lambda _q, _a: False)
    monkeypatch.setattr(auto_memory, "_enforce_ceiling", lambda _mem: 0)

    result = auto_memory.maybe_store_turn("Did you find my numbers anywhere?", EXPECTED_RUN)

    assert result["stored"] is True
    note = captured[0]
    assert note.startswith("Q: Did you find my numbers anywhere?\nA: ")
    assert "anything.\n\nWorkspace" in note
    assert "is in.\n\nNo numbers" in note
