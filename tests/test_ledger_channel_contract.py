"""B2 contract: which field is the answer, and where the working-memory preamble lives.

Measured, not assumed:
- the ledger is built as one system message (core/conversation_compactor.py:117) and that is the only
  place it exists server-side — no SSE frame of /api/chat/stream and no body of /api/chat carries it;
- the answer is the `data` field of the `chunk` frame and the route forwards it unfiltered, so an
  engine that echoes its own context block would reach the transcript through the same field.

The audit bubble (docs/UX_PERSONA_AUDIT_2026-10-10.md, B2) was reproduced from the client's own
compaction: the placeholder it shows ("- Keine stabilen Fakten erkannt.") exists only in (language-gate: ignore — quoted client-side placeholder)
app/src/lib/compact.ts:228, while the Python producer writes the English form
(core/conversation_compactor.py:222). These tests therefore pin the server half of the contract and
state what the renderer may not assume.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

LEDGER_HEAD = "Working Memory Ledger for Ephe."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    from server.main import create_app

    return TestClient(create_app())


def _history(n: int = 30) -> list[dict]:
    """Longer than DEFAULT_MAX_MESSAGES (28), so the deterministic compactor fires."""
    msgs = [{"role": "user", "content": "task context: audit the report"}]
    for i in range(1, n):
        role = "assistant" if i % 2 else "user"
        msgs.append({"role": role, "content": f"turn {i}: runs pytest, writes downloads/report.pdf"})
    return msgs


def _sse(client: TestClient, body: dict) -> list[dict]:
    with patch(
        "server.routes.chat.reflect",
        new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok")),
    ):
        with client.stream(
            "POST", "/api/chat/stream", json={"model": "gemma4:12b", "history": [], **body}
        ) as response:
            assert response.status_code == 200
            text = "".join(response.iter_text())
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[5:].strip()))
            except json.JSONDecodeError:
                pass
    return events


class TestLedgerStaysOutOfTheAnswerChannel:
    def test_server_owned_compaction_hands_the_ledger_as_a_system_message(self, client):
        """G: a REST session long enough to compact, caller omits history
           W: POST /api/chat with the engine stubbed
           T: the context reaching the engine holds the ledger as role=system,
              and the ledger header appears nowhere in the HTTP body."""
        seen: dict = {}

        async def fake_react_loop(**kwargs):
            seen["context"] = list(kwargs.get("context") or [])
            return "The report has 12 rows."

        provider = MagicMock()
        provider.model = "gemma4:12b"
        with patch("server.routes.chat._load_rest_history", return_value=_history()), \
             patch("server.routes.chat.get_active_provider", return_value=provider), \
             patch("server.routes.chat._ensure_engine_ready"), \
             patch("server.routes.chat.react_loop", new=fake_react_loop):
            response = client.post(
                "/api/chat",
                json={"message": "summarise it", "model": "gemma4:12b", "history": [],
                      "session_id": "ledger-contract-rest"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["response"] == "The report has 12 rows."
        ledger = [m for m in seen["context"] if str(m.get("content", "")).startswith(LEDGER_HEAD)]
        assert ledger, f"no ledger message in the engine context: {[m.get('role') for m in seen['context']]}"
        assert {m["role"] for m in ledger} == {"system"}
        assert LEDGER_HEAD not in json.dumps(body)

    def test_stream_answer_is_the_chunk_data_field_and_carries_no_ledger(self, client):
        """T: answer text arrives only as chunk.data; no frame of the stream contains the ledger."""
        async def fake_chat_with_tools(**kwargs):
            for piece in ("The report ", "has 12 rows."):
                kwargs["on_chunk"](piece)
            return "The report has 12 rows."

        with patch("server.routes.chat._ensure_engine_ready"), \
             patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            events = _sse(client, {"message": "summarise it", "session_id": "ledger-contract-stream"})

        answer = "".join(str(e.get("data")) for e in events if e.get("type") == "chunk")
        assert answer == "The report has 12 rows."
        assert all(str(e.get("data", "")) for e in events if e.get("type") == "chunk")
        assert LEDGER_HEAD not in json.dumps(events, ensure_ascii=False)

    def test_an_echoed_preamble_reaches_the_transcript_unfiltered(self, client):
        """The channel is not screened: whatever the engine puts in the answer field is forwarded
           verbatim, so the renderer cannot assume chunk.data is always prose."""
        echo = f"{LEDGER_HEAD}\nConversation working memory for Ephe.\n## User preferences\n- x"

        async def fake_chat_with_tools(**kwargs):
            kwargs["on_chunk"](echo)
            return echo

        with patch("server.routes.chat._ensure_engine_ready"), \
             patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            events = _sse(client, {"message": "what did you remember", "session_id": "ledger-contract-echo"})

        answer = "".join(str(e.get("data")) for e in events if e.get("type") == "chunk")
        assert answer.startswith(LEDGER_HEAD)
