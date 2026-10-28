"""
◑ Ephe – I6-Fix P1-2 · TDD
tests/test_tool_stream_events.py

RULE: the tests were written BEFORE the implementation.

Covers the I6 findings P1-2 (+ route wiring pins for P1-4):
1. The server emits structured ``tool_start``/``tool_done`` events so the
   frontend can fill the persistent tool-stream rows (I1 ToolStreamRows).
   Before there were only ``activity`` chips → in the live chat tool calls were
   invisible after streaming (0 tool rows in the /ephe test).
2. The tool-iteration cap is public per call (max_tool_iterations);
   the /ephe path raises it to >= 8, and exhaustion ends with human-readable
   text instead of the raw "[⚠ Max tool iterations (5) reached]".
3. The chat route forwards the confirmation callback (on_tool_confirm)
   (P1-4 gate on the PWA path).
"""
from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient


# Helpers

def _make_ollama_response(content: str = "", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = msg
    return response


def _make_tool_call(name: str, arguments: dict):
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc = MagicMock()
    tc.function = func
    return tc


@pytest.fixture
def client(tmp_path):
    """TestClient with an isolated tmp_path for memory + profile + skills."""
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


def _stream(client, body: dict) -> str:
    """POST /api/chat/stream → the complete raw SSE text."""
    with patch(
        "server.routes.chat.reflect",
        new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok")),
    ):
        with client.stream(
            "POST", "/api/chat/stream",
            json={"model": "gemma4:12b", "history": [], **body},
        ) as response:
            assert response.status_code == 200
            return "".join(response.iter_text())


def _events(body_text: str) -> list[dict]:
    events = []
    for line in body_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[5:].strip()))
            except json.JSONDecodeError:
                pass
    return events


class TestToolStreamEvents:
    """SSE delivers tool_start/tool_done with the tool name (frontend rows)."""

    def test_stream_emits_tool_start_and_tool_done(self, client):
        """G: tool execution calls on_tool_start/on_tool_done
           W: POST /api/chat/stream
           T: tool_start event with tool+args, tool_done event with tool+result"""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"]("read_file", {"path": "a.txt"})
            kwargs["on_tool_done"]("read_file", "DER-INHALT")
            kwargs["on_chunk"]("Inhalt ist da.")
            return "Inhalt ist da."

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            body = _stream(client, {"message": "lies a.txt", "session_id": "tse-1"})

        evs = _events(body)
        starts = [e for e in evs if e.get("type") == "tool_start"]
        dones = [e for e in evs if e.get("type") == "tool_done"]
        assert starts, f"kein tool_start-Event in {[e.get('type') for e in evs]}"
        assert dones, f"kein tool_done-Event in {[e.get('type') for e in evs]}"
        assert starts[0]["tool"] == "read_file"
        assert starts[0]["args"]["path"] == "a.txt"
        assert dones[0]["tool"] == "read_file"
        assert "DER-INHALT" in dones[0]["result"]

    def test_tool_done_carries_the_digest_of_its_payload(self, client):
        """E1: the proof ledger's sha256 has to match the bytes the client holds."""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"]("read_file", {"path": "a.txt"})
            kwargs["on_tool_done"]("read_file", "DER-INHALT")
            kwargs["on_chunk"]("Inhalt ist da.")
            return "Inhalt ist da."

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            body = _stream(client, {"message": "lies a.txt", "session_id": "tse-digest"})

        done = [e for e in _events(body) if e.get("type") == "tool_done"][0]
        assert done["sha256"] == hashlib.sha256("DER-INHALT".encode()).hexdigest()

    def test_tool_done_digest_covers_the_capped_payload(self, client):
        """A capped frame is hashed after the cut, so the reader's own re-hash agrees."""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"]("read_file", {"path": "big.txt"})
            kwargs["on_tool_done"]("read_file", "X" * 50_000)
            kwargs["on_chunk"]("Fertig.")
            return "Fertig."

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            body = _stream(client, {"message": "lies big.txt", "session_id": "tse-digest-cap"})

        done = [e for e in _events(body) if e.get("type") == "tool_done"][0]
        assert done["sha256"] == hashlib.sha256(done["result"].encode()).hexdigest()

    def test_pdf_deliver_pages_marker_keeps_path_clean(self, client):
        """B3 deliver 'PDF_FILE:<path>\\nPDF_PAGES:<n>': the file_result event
        carries ONLY the path — no '\\nPDF_PAGES:…' suffix in the artifact path."""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"]("create_pdf", {"filename": "report.pdf"})
            kwargs["on_tool_done"]("create_pdf", "PDF_FILE:/tmp/Downloads/report.pdf\nPDF_PAGES:2")
            kwargs["on_chunk"]("PDF erstellt.")
            return "PDF erstellt."

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            body = _stream(client, {"message": "baue ein pdf", "session_id": "tse-pdf-pages"})

        files = [e for e in _events(body) if e.get("type") == "file_result" and e.get("file_type") == "pdf"]
        assert files, "kein file_result für create_pdf"
        assert files[0]["path"] == "/tmp/Downloads/report.pdf"
        assert "PDF_PAGES" not in files[0]["path"]

    def test_tool_done_result_is_size_capped(self, client):
        """Huge tool results must not inflate the stream (<= 4 KB)."""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"]("read_file", {"path": "big.txt"})
            kwargs["on_tool_done"]("read_file", "X" * 50_000)
            kwargs["on_chunk"]("Fertig.")
            return "Fertig."

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            body = _stream(client, {"message": "lies big.txt", "session_id": "tse-2"})

        dones = [e for e in _events(body) if e.get("type") == "tool_done"]
        assert dones
        assert len(dones[0]["result"]) <= 4_000

    def test_denied_tool_done_marks_result_as_denied(self, client):
        """[TOOL-DENIED] results stay recognisable as such (status text passed through)."""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"]("write_file", {"path": "x.txt"})
            kwargs["on_tool_done"]("write_file", "[TOOL-DENIED] write_file wurde nicht ausgeführt")
            kwargs["on_chunk"]("ok dann nicht")
            return "ok dann nicht"

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            body = _stream(client, {"message": "schreib x.txt", "session_id": "tse-3"})

        dones = [e for e in _events(body) if e.get("type") == "tool_done"]
        assert dones and "[TOOL-DENIED]" in dones[0]["result"]

    def test_route_forwards_tool_confirm_callback(self, client):
        """P1-4 pin: the /stream route passes on_tool_confirm through (not None)."""
        seen: dict = {}

        async def fake_chat_with_tools(**kwargs):
            seen.update(kwargs)
            kwargs["on_chunk"]("hi")
            return "hi"

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            _stream(client, {"message": "hallo", "session_id": "tse-4"})

        assert seen.get("on_tool_confirm") is not None


class TestEpheToolIterationBudget:
    """/ephe raises the tool budget cap; exhaustion reads like prose."""

    def test_ephe_trigger_raises_iteration_budget(self, client):
        """G: message starts with /ephe (built-in skill)
           W: POST /api/chat/stream
           T: chat_with_tools receives max_tool_iterations >= 8"""
        seen: dict = {}

        async def fake_chat_with_tools(**kwargs):
            seen.update(kwargs)
            kwargs["on_chunk"]("Ephe arbeitet.")
            return "Ephe arbeitet."

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            _stream(client, {"message": "/ephe baue ein kleines python-projekt", "session_id": "tse-ephe"})

        assert seen.get("max_tool_iterations") is not None
        assert seen["max_tool_iterations"] >= 8

    def test_plain_chat_keeps_default_budget(self, client, empty_ephe_home):
        """Without a skill the standard cap stays in force (no budget hand-over > 5
           Required: max_tool_iterations either None or <= 8).

           I6-0: without an empty device folder this is not a test but a look into
           the developer's ~/.ephe — whoever set tool_budget there sees that value
           here instead of the empty register (read_generation_explicit
           reads presence-based)."""
        seen: dict = {}

        async def fake_chat_with_tools(**kwargs):
            seen.update(kwargs)
            kwargs["on_chunk"]("normale antwort")
            return "normale antwort"

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools):
            _stream(client, {"message": "normale frage", "session_id": "tse-plain"})

        assert seen.get("max_tool_iterations") is None or seen["max_tool_iterations"] <= 5

    @pytest.mark.asyncio
    async def test_default_cap_matches_max_tool_iterations_with_friendly_marker(self):
        """Core: cap = MAX_TOOL_ITERATIONS (R46: 25), no raw '⚠' marker,
        human-readable exhaustion text."""
        from core.chat import MAX_TOOL_ITERATIONS, chat_with_tools

        tool_response = _make_ollama_response(
            tool_calls=[_make_tool_call("read_file", {"path": "x.txt"})]
        )
        executor = AsyncMock(return_value="ok")
        chunks: list[str] = []

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            provider = AsyncMock()
            provider.chat = AsyncMock(side_effect=[tool_response] * 30)  # R46: cap 25 needs more mock answers
            MockClient.return_value = provider
            with patch.dict("core.tools.registry.TOOL_MAP", {"read_file": executor}, clear=False):
                answer = await chat_with_tools(
                    model="m",
                    history=[{"role": "user", "content": "Lies x.txt"}],
                    on_chunk=chunks.append,
                )

        assert executor.await_count == MAX_TOOL_ITERATIONS
        assert "⚠" not in answer
        assert "tool budget" in answer.lower() or "limit" in answer.lower()

    @pytest.mark.asyncio
    async def test_max_tool_iterations_parameter_raises_the_cap(self):
        """Core: max_tool_iterations=8 allows 8 tool rounds."""
        from core.chat import chat_with_tools

        tool_response = _make_ollama_response(
            tool_calls=[_make_tool_call("read_file", {"path": "x.txt"})]
        )
        executor = AsyncMock(return_value="ok")

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            provider = AsyncMock()
            provider.chat = AsyncMock(side_effect=[tool_response] * 30)  # R46: cap 25 needs more mock answers
            MockClient.return_value = provider
            with patch.dict("core.tools.registry.TOOL_MAP", {"read_file": executor}, clear=False):
                await chat_with_tools(
                    model="m",
                    history=[{"role": "user", "content": "Lies x.txt"}],
                    on_chunk=lambda c: None,
                    max_tool_iterations=8,
                )

        assert executor.await_count == 8
