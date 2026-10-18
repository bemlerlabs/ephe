"""
◑ Ephe – W15 · stability & parity hardening · TDD
tests/test_w15_audit_hardening.py

RULE: tests BEFORE implementation. RED first, then GREEN.

Pins the six W15 points:
1. P0: the approval-registry entry is cleaned up even on CancelledError
   (no lease left in the app-wide `_active_sandbox_events`), `pending_sandbox` alias gone.
2. P0: `_fit_messages_to_window` runs per tool round before the follow-up call —
   the prompt length never exceeds the resolved window.
3. P0: tool timing keyed by call id ((name, str(idx))) + real SAFE-batch runtime.
4. P0: `SUMMARY_FILE_MARKERS` as a module-global SSOT constant (10 entries).
6. P1: `done` frame + `: post` comment before the sentinel; post-turn jobs after.
"""
from __future__ import annotations

import asyncio
import json
import types

import pytest
from unittest.mock import AsyncMock

from core.usage import estimate_tokens, serialize_prompt


# Helpers

def _tool_call(name: str, arguments: dict) -> dict:
    """The dict form is supported by the parser in core.chat (isinstance branch)."""
    return {"function": {"name": name, "arguments": arguments}}


def _ns_response(content: str = "", tool_calls: list | None = None):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(content=content, tool_calls=tool_calls or [])
    )


async def _collect_stream(req, mock_chat) -> list[dict]:
    """Drives server.routes.chat.chat_stream with a mocked chat_with_tools."""
    from server.routes import chat as chat_route
    from server.routes.chat import chat_stream

    resp = await chat_stream(req)
    gen = resp.body_iterator
    frames: list[dict] = []
    async for _ in range(50):
        line = await gen.__anext__()
        frames.append(line)
        if '"type": "done"' in line or line.startswith(":"):
            # done or the last frame (comment before the sentinel) — read the buffer
            pass
    return frames


def _events(raw_lines: list[str]) -> list[dict]:
    out = []
    for line in raw_lines:
        for part in line.split("\n\n"):
            if part.startswith("data: "):
                out.append(json.loads(part[len("data: "):]))
    return out


# T1 · P0: approval-registry cleanup on abort

class TestApprovalRegistryCleanup:

    @pytest.mark.asyncio
    async def test_given_cancelled_stream_when_approval_pending_then_registry_empty(self, monkeypatch):
        """G: approval pending (token registered, event.wait() blocks)
        W: consumer abort (stop button → CancelledError)
        T: the token is gone from _active_sandbox_events without residue"""
        from server.routes import chat as chat_route

        async def fake_ct(**kwargs):
            cb = kwargs.get("on_tool_confirm")
            if cb is not None:
                await cb("write_file", {"path": "a"})
            return "ok"

        monkeypatch.setattr(chat_route, "chat_with_tools", fake_ct)
        chat_route._active_sandbox_events.clear()

        req = chat_route.StreamRequest(message="test", session_id="s1")
        resp = await chat_route.chat_stream(req)
        gen = resp.body_iterator

        # consume frames up to sandbox_confirm (the token is registered by then)
        token_seen: str | None = None
        for _ in range(10):
            line = await gen.__anext__()
            for part in line.split("\n\n"):
                if part.startswith("data: "):
                    ev = json.loads(part[len("data: "):])
                    if ev.get("type") == "sandbox_confirm":
                        token_seen = ev["token"]
            if token_seen is not None:
                break

        assert token_seen is not None, "sandbox_confirm-Event mit token erwartet"
        assert token_seen in chat_route._active_sandbox_events

        # The run ledger queues one run_phase frame behind the consent frame; read
        # it so the next read is the idle wait (a timeout here would cancel the
        # generator, which is the stop this test simulates below).
        phase_line = await asyncio.wait_for(gen.__anext__(), 0.2)
        assert "run_phase" in phase_line, phase_line[:120]

        # Stop simulation: anext task with a short timeout → CancelledError in the
        # generator frame → task.cancel() inside the generator → _sandbox_cb finally.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gen.__anext__(), 0.02)
        await asyncio.sleep(0.05)  # drain the loop: run the task's finally blocks through

        assert token_seen not in chat_route._active_sandbox_events, (
            "Token nach Abbruch nicht aufgeraeumt (Registry-Leak)"
        )

    def test_pending_sandbox_alias_removed(self):
        """T-02: the deprecated legacy alias `pending_sandbox` is removed."""
        from server.routes import chat as chat_route

        assert not hasattr(chat_route, "pending_sandbox")

    def test_normal_path_pops_token(self):
        """Normal case (the approval arrives): pop as before, registry empty."""
        from server.routes import chat as chat_route

        chat_route._active_sandbox_events.clear()
        token = "t-1"
        chat_route._active_sandbox_events[token] = {
            "event": asyncio.Event(), "approved": True,
        }
        res = chat_route._active_sandbox_events.pop(token, {"approved": False})
        assert res["approved"] is True
        assert token not in chat_route._active_sandbox_events


# T2 · P0: re-overflow guard in the tool loop

class TestToolLoopWindowFit:

    @pytest.mark.asyncio
    async def test_given_ten_tool_rounds_when_followup_then_prompt_fits_window(self, monkeypatch, tmp_path):
        """G: 10 tool rounds with ~5k-character results each, window 8192
        W: chat_with_tools runs (Ollama path, non-streaming detection)
        T: the last follow-up payload is <= the window (fit per round, not just once)"""
        import core.chat as cc

        monkeypatch.setenv("EPHE_CONTEXT_WINDOW", "8192")
        big = "x" * 5000
        f = tmp_path / "big.txt"
        f.write_text(big, encoding="utf-8")

        tc = [_tool_call("read_file", {"path": str(f)})]
        responses = [
            _ns_response(tool_calls=tc) for _ in range(10)
        ] + [_ns_response(content="fertig")]

        async def _next_response(responses):
            return responses.pop(0)

        mock_client = AsyncMock()
        mock_client.chat.side_effect = lambda **kw: _next_response(responses)
        monkeypatch.setattr(cc, "build_provider_client", lambda provider: mock_client)
        monkeypatch.setattr(cc, "get_active_provider", lambda: cc.ModelProviderConfig(
            provider="local_ollama", model="gemma4:12b",
            base_url="http://127.0.0.1:11434", label="Local Ollama",
            offline_capable=True, requires_internet=False,
        ))

        history = [{"role": "user", "content": " Lies die Datei."}]
        await cc.chat_with_tools(
            model="gemma4:12b",
            history=history,
            on_chunk=lambda c: None,
        )

        # The last chat call carries the final follow-up payload.
        last_kwargs = mock_client.chat.call_args_list[-1]
        sent = last_kwargs[1] if len(last_kwargs) > 1 else last_kwargs[0]
        messages = sent.get("messages") if isinstance(sent, dict) else None
        if messages is None:
            # keyword-named calls: the last kwargs entry
            messages = sent.get("messages")

        window = 8192
        est = estimate_tokens(serialize_prompt(messages))
        assert est <= window, (
            f"Follow-up-Payload {est} Tokens ueberschreitet Fenster {window} — "
            "fit laeuft nicht je Runde"
        )


# T3 · P0: tool timing with call id + real SAFE-batch runtime

class TestToolTimingKeys:

    @pytest.mark.asyncio
    async def test_given_two_same_name_calls_when_stream_then_call_id_present(self, monkeypatch):
        """G: 1 round, 2 tools of the same name (read_file twice), cap 1
        W: real chat_with_tools + route frames
        T: tool_start carries call_id '0'/'1'; both starts before the first done;
           tool_done with the matching call_id + duration_ms > 0"""
        import core.chat as cc
        from server.routes import chat as chat_route

        # Small 1-round suite: cap=1 (no 2nd follow-up needed), so that the
        # frames stay manageable.
        monkeypatch.setattr(cc, "MAX_TOOL_ITERATIONS", 1)

        f_1, f_2 = "/tmp/a", "/tmp/b"  # args-only comparison, IO via patch

        async def fake_exec(name, args, policy=None):
            await asyncio.sleep(0.02)
            return "ergebnis"

        monkeypatch.setattr(cc, "execute_tool", fake_exec)

        responses = [
            _ns_response(tool_calls=[
                _tool_call("read_file", {"path": f_1}),
                _tool_call("read_file", {"path": f_2}),
            ]),
            _ns_response(content="fertig"),
        ]

        async def _next_response(**kw):
            return responses.pop(0)

        mock_client = AsyncMock()
        mock_client.chat.side_effect = _next_response
        monkeypatch.setattr(cc, "build_provider_client", lambda provider: mock_client)
        monkeypatch.setattr(cc, "get_active_provider", lambda: cc.ModelProviderConfig(
            provider="local_ollama", model="gemma4:12b",
            base_url="http://127.0.0.1:11434", label="Local Ollama",
            offline_capable=True, requires_internet=False,
        ))

        req = chat_route.StreamRequest(message="test", session_id="s1")
        resp = await chat_route.chat_stream(req)
        gen = resp.body_iterator
        raw_all = ""
        for _ in range(60):
            try:
                raw_all += await asyncio.wait_for(gen.__anext__(), 2.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
            if '"type": "done"' in raw_all:
                break

        events = _events(raw_all.split("\n\n"))
        starts = [e for e in events if e.get("type") == "tool_start"]
        dones = [e for e in events if e.get("type") == "tool_done"]

        assert len(starts) >= 2
        assert len(dones) >= 2
        # 1) the call_id field exists and is index-stable — the A3 groundwork carries
        #    the turn identity inside it: twenty turns share a bare "0", and a
        #    workbench card pointing at "0" says nothing about where its result came from.
        first, second = starts[0]["call_id"], starts[1]["call_id"]
        assert first.endswith("-0") and second.endswith("-1"), (first, second)
        assert first != second
        assert dones[0].get("call_id") == first
        assert dones[1].get("call_id") == second
        # 2) both starts before the first done (parse phase before execute+append)
        types_seq = [e["type"] for e in events]
        first_done = types_seq.index("tool_done")
        assert types_seq[:first_done].count("tool_start") >= 2, types_seq
        # 3) real runtime (SAFE-batch: start before gather, done afterwards)
        assert dones[0].get("duration_ms", 0) > 0
        assert dones[1].get("duration_ms", 0) > 0

    @pytest.mark.asyncio
    async def test_same_name_two_calls_second_duration_is_own_span(self, monkeypatch):
        """G: 2 calls of the same name, each with its own t0 index
        W: on_tool_start / order start0,start1,done0,done1
        T: done1.duration_ms matches its own span (not 0)."""
        import core.chat as cc

        monkeypatch.setattr(cc, "MAX_TOOL_ITERATIONS", 1)

        async def fake_exec(name, args, policy=None):
            await asyncio.sleep(0.03)
            return "ok"

        monkeypatch.setattr(cc, "execute_tool", fake_exec)

        responses = [
            _ns_response(tool_calls=[
                _tool_call("read_file", {"path": "a"}),
                _tool_call("read_file", {"path": "b"}),
            ]),
            _ns_response(content="fertig"),
        ]

        async def _next_response(**kw):
            return responses.pop(0)

        mock_client = AsyncMock()
        mock_client.chat.side_effect = _next_response
        monkeypatch.setattr(cc, "build_provider_client", lambda provider: mock_client)
        monkeypatch.setattr(cc, "get_active_provider", lambda: cc.ModelProviderConfig(
            provider="local_ollama", model="gemma4:12b",
            base_url="http://127.0.0.1:11434", label="Local Ollama",
            offline_capable=True, requires_internet=False,
        ))

        from server.routes import chat as chat_route
        req = chat_route.StreamRequest(message="t", session_id="s1")
        resp = await chat_route.chat_stream(req)
        gen = resp.body_iterator
        raw_all = ""
        for _ in range(60):
            try:
                raw_all += await asyncio.wait_for(gen.__anext__(), 2.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
            if '"type": "done"' in raw_all:
                break

        dones = [e for e in _events(raw_all.split("\n\n")) if e.get("type") == "tool_done"]
        assert len(dones) >= 2
        assert dones[1].get("duration_ms", 0) > 0


# T4 fell away with R36: SUMMARY_FILE_MARKERS/_emit_file_markers were fast-path
# file markers (core/skill_fastpath deleted); agent-path artifacts now run
# through _FILE_RESULT_PREFIXES (chat.py) + normalize_tool_result.

# T6 · P1: done + : post before the sentinel, post-turn jobs afterwards

class TestStreamPostOrdering:

    @pytest.mark.asyncio
    async def test_given_done_frame_when_stream_ends_then_post_comment_before_close(self, monkeypatch):
        """G: stream with a done event
        W: run the event_generator through
        T: after `done` the stream carries the `: post` comment before the end,
           the data frames stay identical (done last among the data events)"""
        from server.routes import chat as chat_route

        async def fake_ct(**kwargs):
            cb = kwargs.get("on_chunk")
            if cb is not None:
                cb("hallo")
            return "hallo"

        monkeypatch.setattr(chat_route, "chat_with_tools", fake_ct)

        req = chat_route.StreamRequest(message="test", session_id="s1")
        resp = await chat_route.chat_stream(req)
        gen = resp.body_iterator
        raw_all = ""
        for _ in range(60):
            try:
                raw_all += await asyncio.wait_for(gen.__anext__(), 2.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                break

        events = _events(raw_all.split("\n\n"))
        assert events[-1].get("type") == "done", "done bleibt letzter data-Event"
        assert ": post" in raw_all, "post-Kommentar fehlt (Sentinel-Vorziehung nicht aktiv)"
        # Order in the raw stream: done before : post
        assert raw_all.index('"type": "done"') < raw_all.index(": post")
