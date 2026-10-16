"""
Ephe — R33 / stress triage P1-1: server-side history for REST callers.

The 1000-message campaign found that POST /api/chat kept NO server-side
history: every REST caller had to replay its own `history` array, and the
server-side compaction path was therefore unreachable for them. These tests
pin the fix: with a session_id the route persists each completed turn into
the session store (namespace `rest-<id>`) and, when the caller omits
`history`, the server feeds the persisted turns back as context.

RULE: tests written BEFORE the implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def sessions_root(tmp_path, monkeypatch):
    """Redirect the whole multi-session store into a private tmp dir."""
    from core import multi_session as ms

    root = tmp_path / "sessions"
    monkeypatch.setattr(ms, "SESSIONS_DIR", root)
    monkeypatch.setattr(ms, "REGISTRY_FILE", root / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", root / "default.json")
    return root


@pytest.fixture
def client(tmp_path):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    from server.main import create_app

    return TestClient(create_app())


def _read_store_file(root, sid):
    f = root / f"{sid}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


class TestRestTurnPersistence:
    def test_chat_with_session_id_persists_turn(self, client, sessions_root):
        """
        GIVEN  a fresh session store
        WHEN   POST /api/chat with {"message", "session_id": "s1"} (engine mocked)
        THEN   rest-s1.json exists in the sessions dir
        AND    it contains the user message and the assistant reply in order
        """
        with patch(
            "server.routes.chat.react_loop",
            new=AsyncMock(return_value="Hallo zurueck!"),
        ):
            r = client.post(
                "/api/chat",
                json={"message": "Hallo", "model": "gemma4:12b", "session_id": "s1"},
            )
        assert r.status_code == 200
        data = _read_store_file(sessions_root, "rest-s1")
        assert data is not None
        assert [m["role"] for m in data] == ["user", "assistant"]
        assert data[0]["content"] == "Hallo"
        assert data[1]["content"] == "Hallo zurueck!"

    def test_chat_without_session_id_stores_nothing(self, client, sessions_root):
        """
        GIVEN  a fresh session store
        WHEN   POST /api/chat WITHOUT a session_id
        THEN   no rest-*.json file is created (documented stateless mode)
        """
        with patch(
            "server.routes.chat.react_loop",
            new=AsyncMock(return_value="Antwort"),
        ):
            r = client.post("/api/chat", json={"message": "Hi", "model": "gemma4:12b"})
        assert r.status_code == 200
        assert list(sessions_root.glob("rest-*.json")) == []

    def test_second_turn_appends(self, client, sessions_root):
        """
        GIVEN  one persisted turn in rest-s2
        WHEN   a second POST /api/chat with the same session_id
        THEN   the store holds user/assistant/user/assistant in call order
        """
        with patch(
            "server.routes.chat.react_loop",
            new=AsyncMock(return_value="Erste Antwort"),
        ):
            client.post(
                "/api/chat",
                json={"message": "Frage 1", "model": "gemma4:12b", "session_id": "s2"},
            )
        with patch(
            "server.routes.chat.react_loop",
            new=AsyncMock(return_value="Zweite Antwort"),
        ):
            client.post(
                "/api/chat",
                json={"message": "Frage 2", "model": "gemma4:12b", "session_id": "s2"},
            )
        data = _read_store_file(sessions_root, "rest-s2")
        assert [m["role"] for m in data] == ["user", "assistant", "user", "assistant"]
        assert data[2]["content"] == "Frage 2"

    def test_invalid_session_id_is_rejected_from_store_not_request(self, client, sessions_root):
        """
        GIVEN  a path-traversal style session_id
        WHEN   POST /api/chat
        THEN   the request still succeeds (engine mocked)
        AND    nothing is written under the sessions dir for that id
        """
        with patch(
            "server.routes.chat.react_loop",
            new=AsyncMock(return_value="OK"),
        ):
            r = client.post(
                "/api/chat",
                json={
                    "message": "hi",
                    "model": "gemma4:12b",
                    "session_id": "../../etc/passwd",
                },
            )
        assert r.status_code == 200
        assert list(sessions_root.glob("*")) == []


class TestServerContextFallback:
    def test_empty_history_loads_persisted_turns(self, client, sessions_root):
        """
        GIVEN  rest-s3 already holds one user/assistant pair
        WHEN   POST /api/chat with the same session_id and NO history field
        THEN   react_loop receives the persisted pair as `context`
        """
        sessions_root.mkdir(parents=True, exist_ok=True)
        (sessions_root / "rest-s3.json").write_text(
            json.dumps(
                [
                    {"role": "user", "content": "Vorherige Frage"},
                    {"role": "assistant", "content": "Vorherige Antwort"},
                ]
            ),
            encoding="utf-8",
        )
        fake = AsyncMock(return_value="Neu")
        with patch("server.routes.chat.react_loop", new=fake):
            r = client.post(
                "/api/chat",
                json={"message": "Weiter", "model": "gemma4:12b", "session_id": "s3"},
            )
        assert r.status_code == 200
        context = fake.await_args.kwargs["context"]
        assert [m["content"] for m in context] == ["Vorherige Frage", "Vorherige Antwort"]

    def test_long_server_history_arrives_compacted(self, client, sessions_root):
        """
        GIVEN  rest-s6 holds 40 turns worth of messages (well over the 28 cap)
        WHEN   POST /api/chat with the session id and NO history
        THEN   react_loop receives a compacted context: fewer messages than 40
        AND    exactly one leading system summary message
        AND    the most recent turn survives verbatim
        """
        sessions_root.mkdir(parents=True, exist_ok=True)
        turns = []
        for i in range(20):
            turns.append({"role": "user", "content": f"Frage {i}"})
            turns.append({"role": "assistant", "content": f"Antwort {i}"})
        (sessions_root / "rest-s6.json").write_text(
            json.dumps(turns), encoding="utf-8"
        )
        fake = AsyncMock(return_value="ok")
        with patch("server.routes.chat.react_loop", new=fake):
            client.post(
                "/api/chat",
                json={"message": "Weiter", "model": "gemma4:e4b", "session_id": "s6"},
            )
        context = fake.await_args.kwargs["context"]
        assert len(context) < 40
        # W18: first-message guard (index 0 = the protected first 'user'), ledger at index 1
        assert context[0]["role"] == "user"
        assert context[1]["role"] == "system"
        assert [m for m in context if m["role"] != "system"][-1]["content"] == "Antwort 19"

    def test_explicit_history_wins_over_store(self, client, sessions_root):
        """
        GIVEN  rest-s4 holds a persisted pair AND the request carries its own history
        WHEN   POST /api/chat
        THEN   react_loop gets the caller-provided history unchanged
        """
        sessions_root.mkdir(parents=True, exist_ok=True)
        (sessions_root / "rest-s4.json").write_text(
            json.dumps([{"role": "user", "content": "Server-Kontext"}]),
            encoding="utf-8",
        )
        fake = AsyncMock(return_value="Neu")
        with patch("server.routes.chat.react_loop", new=fake):
            client.post(
                "/api/chat",
                json={
                    "message": "Weiter",
                    "model": "gemma4:12b",
                    "session_id": "s4",
                    "history": [{"role": "user", "content": "Client-Kontext"}],
                },
            )
        context = fake.await_args.kwargs["context"]
        assert context == [{"role": "user", "content": "Client-Kontext"}]


class TestStreamPersistence:
    def test_stream_turn_is_mirrored(self, client, sessions_root):
        """
        GIVEN  a fresh store
        WHEN   POST /api/chat/stream with a session_id (chat_with_tools mocked
               to emit one chunk via its on_chunk callback)
        THEN   the stream completes with `done`
        AND    rest-s5.json holds the user message + the streamed answer
        """
        from core.react import ReflexionResult

        async def fake_chat_with_tools(*, on_chunk, **_kwargs):
            on_chunk("Hallo ")
            on_chunk("Welt")

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), \
             patch("server.routes.chat.reflect",
                   new=AsyncMock(return_value=ReflexionResult(needs_revision=False, reason="ok"))):
            with client.stream(
                "POST",
                "/api/chat/stream",
                json={"message": "Hallo Welt", "model": "gemma4:e4b", "session_id": "s5"},
            ) as response:
                body = "".join(response.iter_text())
        assert response.status_code == 200
        assert "done" in body
        data = _read_store_file(sessions_root, "rest-s5")
        assert data is not None
        assert [m["role"] for m in data] == ["user", "assistant"]
        assert data[1]["content"] == "Hallo Welt"


class TestStoreCaps:
    def test_store_is_capped_and_trims_oldest(self, client, sessions_root):
        """
        GIVEN  rest-cap already holds 2000 messages (the cap)
        WHEN   a new turn is persisted
        THEN   the store still holds exactly 2000 messages
        AND    the oldest message was trimmed, the newest is present
        """
        sessions_root.mkdir(parents=True, exist_ok=True)
        bulk = [{"role": "user", "content": f"alt-{i}"} for i in range(2000)]
        (sessions_root / "rest-cap.json").write_text(
            json.dumps(bulk), encoding="utf-8"
        )
        with patch(
            "server.routes.chat.react_loop",
            new=AsyncMock(return_value="Frisch"),
        ):
            client.post(
                "/api/chat",
                json={"message": "Neu", "model": "gemma4:12b", "session_id": "cap"},
            )
        data = _read_store_file(sessions_root, "rest-cap")
        assert len(data) == 2000
        assert data[-1]["content"] == "Frisch"
        assert data[-2]["content"] == "Neu"
        assert data[0]["content"] != "alt-0"
