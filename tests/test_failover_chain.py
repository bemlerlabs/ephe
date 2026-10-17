"""tests/test_failover_chain.py — failover chain (R44, Deep-Audit 2026-09-16).

Provider failover chain: active → local_ollama → honest error.
resolve_failover_chain() is the pure, testable core logic; the chat path
records the failover reason in the kind=turn audit entry.
"""
from __future__ import annotations

from dataclasses import replace

from core.model_provider import (
    ModelProviderConfig,
    resolve_active_with_failover,
    resolve_failover_chain,
)


def _dgx() -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="openai_compatible",
        model="custom-model",
        base_url="http://dgx:8000/v1",
        label="DGX",
        offline_capable=False,
        requires_internet=True,
    )


def _ollama() -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="local_ollama",
        model="gemma4:12b",
        base_url="http://localhost:11434",
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    )


def test_given_remote_engine_when_chain_resolved_then_ollama_is_fallback():
    """GIVEN an active OpenAI-compatible engine (DGX)
    WHEN the failover chain is resolved
    THEN the active one stands first, local_ollama as second candidate behind it."""
    chain = resolve_failover_chain(_dgx())
    assert [c.provider for c in chain] == ["openai_compatible", "local_ollama"]


def test_given_local_ollama_when_chain_resolved_then_single_candidate():
    """GIVEN the active engine is already local_ollama
    WHEN the failover chain is resolved
    THEN it returns exactly one candidate (no duplicate)."""
    chain = resolve_failover_chain(_ollama())
    assert [c.provider for c in chain] == ["local_ollama"]


def test_given_none_when_chain_resolved_then_empty():
    """GIVEN no active engine (None)
    WHEN the failover chain is resolved
    THEN the chain is empty (fail-closed, no silent default)."""
    assert resolve_failover_chain(None) == []


def test_given_same_base_url_when_chain_resolved_then_deduped():
    """GIVEN the active and the fallback entry share provider+base_url+model
    WHEN the failover chain is resolved
    THEN the duplicate candidate appears only once."""
    same = replace(_ollama(), label="Dup")
    # identical (provider, base_url, model) → dedupe down to one
    chain = resolve_failover_chain(_ollama())
    keys = [(c.provider, c.base_url, c.model) for c in chain]
    assert len(keys) == len(set(keys))
    assert (same.provider, same.base_url, same.model) in keys


def test_failover_reason_is_reported_in_turn_audit(tmp_path, monkeypatch):
    """GIVEN a failover from DGX onto Ollama
    WHEN the turn audit entry is written
    THEN it carries the failover reason (from→to) in the detail field."""
    from core import audit_log

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    audit_log.audit_event(
        "turn",
        tool="skill",
        status="ok",
        duration_ms=12,
        detail="mode=full-access tools=0 failover=openai_compatible→local_ollama",
    )
    entries = audit_log.tail(kind="turn")
    assert entries and "failover=openai_compatible→local_ollama" in entries[0]["detail"]


# W3-37: the chain end to end against a REAL secondary over a real socket.
# No monkeypatched probe here — the secondary is a live HTTP server the chain
# actually reaches on 127.0.0.1. Exercises the full path: probe → fail over →
# record the reason → serve the turn from the secondary; and the fail-closed
# end (both candidates dead → active kept, no silent switch).

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from core.chat import chat_with_tools
from core.provider_errors import ProviderFailureKind
from core.tools import session_ctx

SECONDARY_ANSWER = "served by the secondary"


class _SecondaryOllama(BaseHTTPRequestHandler):
    """A real, minimal Ollama-native secondary: the /models probe and /api/chat.

    probe_provider() GETs ``{base_url}/models``; the native Ollama client POSTs
    ``{host}/api/chat``. Both are answered here so the same live server proves
    reachability and then serves the turn.
    """

    answer = SECONDARY_ANSWER
    hits: ClassVar[list[str]] = []

    def log_message(self, format, *args):
        pass

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json({"models": [{"name": "secondary", "model": "secondary"}]})
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        type(self).hits.append(self.path)
        if self.path.rstrip("/").endswith("/api/chat"):
            self._json(
                {
                    "model": "secondary",
                    "created_at": "2026-10-11T00:00:00Z",
                    "message": {"role": "assistant", "content": type(self).answer},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 1,
                    "eval_count": 1,
                    "prompt_eval_count": 1,
                }
            )
        else:
            self._json({"error": "not found"}, status=404)


@pytest.fixture()
def secondary_engine():
    """A live Ollama-native secondary on a real loopback port, torn down after."""
    handler = type("BoundSecondary", (_SecondaryOllama,), {"hits": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield url, handler
    finally:
        server.shutdown()
        server.server_close()


def _closed_port_base_url() -> str:
    """A base URL on a closed loopback port — a real endpoint that refuses."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"http://127.0.0.1:{port}/v1"


def _unreachable_remote() -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="openai_compatible",
        model="remote-model",
        base_url=_closed_port_base_url(),
        label="Unreachable remote",
        offline_capable=False,
        requires_internet=True,
    )


@pytest.mark.asyncio
async def test_chain_fails_over_to_a_real_secondary(secondary_engine, monkeypatch):
    """GIVEN the active engine is unreachable and a live Ollama secondary answers /models
    WHEN the chain resolves
    THEN the secondary wins and the failover reason is recorded — no probe stub."""
    url, _handler = secondary_engine
    monkeypatch.setenv("EPHE_MODEL", "secondary-model")
    monkeypatch.setenv("EPHE_LOCAL_OLLAMA_BASE_URL", url)

    resolved = await resolve_active_with_failover(_unreachable_remote())

    assert resolved is not None
    assert resolved.provider == "local_ollama"
    assert resolved.base_url == url
    note = session_ctx.get_failover_note()
    # The contract is that the note names both ends and the classified cause. Which cause it
    # is depends on how the probe failed on this box — a fast refusal reads transport, a slow
    # runner reads timeout — so this names the taxonomy rather than one member of it.
    assert "openai_compatible" in note and "local_ollama" in note, note
    assert note.endswith(tuple(f"({kind.value})" for kind in ProviderFailureKind)), note


@pytest.mark.asyncio
async def test_turn_is_served_end_to_end_from_the_real_secondary(
    secondary_engine, monkeypatch
):
    """GIVEN the active engine is unreachable and a live Ollama secondary is up
    WHEN a full chat turn runs
    THEN the answer arrives from the secondary over real HTTP and the note is set."""
    url, handler = secondary_engine
    monkeypatch.setenv("EPHE_MODEL", "secondary-model")
    monkeypatch.setenv("EPHE_LOCAL_OLLAMA_BASE_URL", url)

    chunks: list[str] = []
    result = await chat_with_tools(
        model="secondary-model",
        history=[{"role": "user", "content": "ping"}],
        on_chunk=chunks.append,
        provider_config=_unreachable_remote(),
    )

    assert result == SECONDARY_ANSWER
    assert "".join(chunks) == SECONDARY_ANSWER
    assert any(p.rstrip("/").endswith("/api/chat") for p in handler.hits), (
        "the turn was not served by the secondary engine"
    )
    note = session_ctx.get_failover_note()
    # The contract is that the note names both ends and the classified cause. Which cause it
    # is depends on how the probe failed on this box — a fast refusal reads transport, a slow
    # runner reads timeout — so this names the taxonomy rather than one member of it.
    assert "openai_compatible" in note and "local_ollama" in note, note
    assert note.endswith(tuple(f"({kind.value})" for kind in ProviderFailureKind)), note


@pytest.mark.asyncio
async def test_chain_fails_closed_when_no_candidate_is_reachable(monkeypatch):
    """GIVEN the active engine and the secondary are both unreachable
    WHEN the chain resolves
    THEN the active config is kept and no failover is recorded — honest error, no silent switch."""
    monkeypatch.setenv("EPHE_MODEL", "secondary-model")
    monkeypatch.setenv("EPHE_LOCAL_OLLAMA_BASE_URL", _closed_port_base_url())

    active = _unreachable_remote()
    resolved = await resolve_active_with_failover(active)

    assert resolved is active
    assert session_ctx.get_failover_note() == ""
