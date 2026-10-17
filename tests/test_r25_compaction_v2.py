"""R25: compaction v2 — memory preservation before discarding + honest budgets.

Roadmap R25.2: "summarising compaction with memory preservation
(Chroma comparison), honest token-budget display".

- compact_history calls an injectable sink per discarded Q/A pair
  (best effort — a sink fault must never block the compaction).
- The default sink writes via maybe_store_turn with source="compaction"
  (Chroma dedupe spans auto_memory + compaction).
- GET /api/context/budget returns real numbers (backend = the same ratio as the
  frontend meter: 4.2 chars/token).
"""

from __future__ import annotations

import sys

import pytest

import core.auto_memory as am
import core.conversation_compactor as cc
from core.conversation_compactor import compact_history


@pytest.fixture(autouse=True)
def _no_bpe(monkeypatch):
    """W16: the 4.2 expectations apply in the fallback path — BPE backend off."""
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    from core import usage
    usage.reset_tokenizer_cache()
    yield
    usage.reset_tokenizer_cache()


LONG_ANSWER = (
    "Eine echte Antwort mit vielen Detailinformationen und Beispielen, "
    "die die 120-Zeichen-Schwelle des Auto-Memory sicher überschreitet. "
    "Sie erklärt den Kontext vollständig und präzise für das Gedächtnis."
)


def _history(pairs: int) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": "sys"}]
    for i in range(pairs):
        out.append({"role": "user", "content": f"Frage {i} über das Projekt"})
        out.append({"role": "assistant", "content": f"Antwort {i} mit Details."})
    return out


# Memory sink


def test_compaction_calls_sink_for_discarded_pairs_only() -> None:
    sink_calls: list[tuple[str, str]] = []

    def sink(user: str, assistant: str) -> None:
        sink_calls.append((user, assistant))

    # 20 pairs = 41 messages (> 28) → first=1 protected, the last 10 stay,
    # middle = history[1:-10] = 30 messages = 15 pairs → 15 sink calls.
    out = compact_history(_history(20), memory_sink=sink)

    assert len(sink_calls) == 15
    assert sink_calls[0] == ("Frage 0 über das Projekt", "Antwort 0 mit Details.")
    assert sink_calls[-1][0] == "Frage 14 über das Projekt"  # u15 without a partner → no call
    # the recent turns are contained unchanged in the output
    assert any("Frage 19 über das Projekt" == m.get("content", "") for m in out)
    # W18: index 0 = the protected first one, index 1 = the ledger
    assert out[0]["role"] == "system" and out[0]["content"] == "sys"
    assert out[1]["role"] == "system"  # summary at the front


def test_compaction_without_sink_is_unchanged_behaviour() -> None:
    out = compact_history(_history(20))
    assert out[0]["role"] == "system"
    assert len(out) <= 12 + 1


def test_sink_errors_never_break_compaction() -> None:
    def bad_sink(user: str, assistant: str) -> None:
        raise RuntimeError("chroma down")

    out = compact_history(_history(20), memory_sink=bad_sink)
    assert out[0]["role"] == "system"


def test_below_threshold_no_sink_calls() -> None:
    calls: list = []
    compact_history(_history(5), memory_sink=lambda u, a: calls.append((u, a)))
    assert calls == []


def test_multi_bucket_message_lands_in_every_matching_section() -> None:
    """P0-4: a message with several category keywords has to stand in EVERY matching
    bucket (not just the last one — no last-write-wins)."""
    hist = [{"role": "user", "content": "Projekt X: Entscheidung Y"}] * 30
    out = compact_history(hist)
    ledger = out[1]["content"]
    # Both sections carry the same entry.
    assert "## Project facts" in ledger
    assert "## Decisions" in ledger
    proj_block = ledger.split("## Project facts", 1)[1].split("##", 1)[0]
    dec_block = ledger.split("## Decisions", 1)[1].split("##", 1)[0]
    assert "Projekt X: Entscheidung Y" in proj_block
    assert "Projekt X: Entscheidung Y" in dec_block


def test_no_keyword_message_falls_back_to_context_bucket() -> None:
    """No category-keyword hit → 'Other relevant context'."""
    hist = [{"role": "user", "content": "Alpha Beta Gamma"}] * 30
    out = compact_history(hist)
    ledger = out[1]["content"]
    ctx_block = ledger.split("## Other relevant context", 1)[1]
    assert "Alpha Beta Gamma" in ctx_block


def test_default_sink_uses_compaction_source(monkeypatch) -> None:
    recorded: list[dict] = []

    def fake_store(user_message, answer, source="auto_memory"):
        recorded.append({"user": user_message, "answer": answer, "source": source})
        return {"stored": True}

    # The lazy import inside default_memory_sink binds at runtime → patch the am module
    monkeypatch.setattr(am, "maybe_store_turn", fake_store)
    compact_history(_history(20), memory_sink=cc.default_memory_sink)
    assert recorded
    assert all(r["source"] == "compaction" for r in recorded)


# Checkpoint preservation (productive path, once per turn)


def test_preserve_compacted_pairs_is_incremental(tmp_path, monkeypatch) -> None:
    from core.compaction_memory import preserve_compacted_pairs

    stored: list[tuple[str, str]] = []

    def sink(user, assistant):
        stored.append((user, assistant))

    cp = tmp_path / "checkpoints.json"
    history = _history(20)  # 41 messages → 14 pairs discarded

    first = preserve_compacted_pairs("s1", messages=history, sink=sink, path=cp)
    second = preserve_compacted_pairs("s1", messages=history, sink=sink, path=cp)

    assert first == 15
    assert second == 0  # checkpoint: no re-work
    assert len(stored) == 15

    # A new turn (2 messages) → only the new pair falls outside the window
    grown = history + [
        {"role": "user", "content": "Frage 20 über das Projekt"},
        {"role": "assistant", "content": "Antwort 20 mit Details."},
    ]
    third = preserve_compacted_pairs("s1", messages=grown, sink=sink, path=cp)
    assert third == 1


def test_preserve_skips_below_threshold_and_empty_session(tmp_path) -> None:
    from core.compaction_memory import preserve_compacted_pairs

    calls: list = []
    assert preserve_compacted_pairs("s1", messages=_history(5), sink=lambda u, a: calls.append(1),
                                    path=tmp_path / "cp.json") == 0
    assert preserve_compacted_pairs("", messages=_history(20), sink=lambda u, a: calls.append(1),
                                    path=tmp_path / "cp.json") == 0
    assert calls == []


def test_preserve_without_messages_loads_session(tmp_path, monkeypatch) -> None:
    import core.multi_session as ms
    from core.compaction_memory import preserve_compacted_pairs

    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", d)
    monkeypatch.setattr(ms, "REGISTRY_FILE", d / "registry.json")

    sid = ms.create_session("Lang")["id"]
    ms.save_messages(sid, [
        msg
        for i in range(20)
        for msg in (
            {"role": "user", "content": f"Frage {i} zum Thema"},
            {"role": "assistant", "content": f"Antwort {i}."},
        )
    ])  # type: ignore[arg-type]

    stored: list = []
    n = preserve_compacted_pairs(sid, sink=lambda u, a: stored.append((u, a)),
                                 path=tmp_path / "cp.json")
    assert n == 15
    assert stored[0][0] == "Frage 0 zum Thema"


# maybe_store_turn: source parameter + spanning dedupe


class _FakeMemory:
    def __init__(self, hits: list[dict] | None = None) -> None:
        self.hits = hits or []
        self.stored: list[dict] = []

    def search(self, text: str, top_k: int = 3) -> list[dict]:
        return self.hits

    def store(self, text: str, metadata: dict | None = None) -> None:
        self.stored.append({"text": text, "metadata": metadata or {}})


@pytest.fixture()
def fake_memory(monkeypatch):
    mem = _FakeMemory()
    monkeypatch.setattr(am, "_memory_factory", lambda: mem)
    return mem


def test_store_turn_compaction_source_is_persisted(fake_memory) -> None:
    out = am.maybe_store_turn("Eine ausführliche Frage zum Projekt", LONG_ANSWER, source="compaction")
    assert out["stored"] is True
    assert fake_memory.stored[0]["metadata"]["source"] == "compaction"


def test_dedupe_covers_both_sources(fake_memory) -> None:
    fake_memory.hits = [{"score": 0.9, "metadata": {"source": "auto_memory"}}]
    out = am.maybe_store_turn("Eine ausführliche Frage zum Projekt", LONG_ANSWER, source="compaction")
    assert out == {"stored": False, "reason": "duplicate"}
    assert fake_memory.stored == []


def test_compaction_entry_blocks_auto_memory_duplicate(fake_memory) -> None:
    fake_memory.hits = [{"score": 0.92, "metadata": {"source": "compaction"}}]
    out = am.maybe_store_turn("Eine ausführliche Frage zum Projekt", LONG_ANSWER)
    assert out == {"stored": False, "reason": "duplicate"}


def test_below_threshold_no_false_duplicate(fake_memory) -> None:
    fake_memory.hits = [{"score": 0.5, "metadata": {"source": "auto_memory"}}]
    out = am.maybe_store_turn("Eine ausführliche Frage zum Projekt", LONG_ANSWER)
    assert out["stored"] is True


# Honest budget display (backend endpoint)


def test_context_budget_route_counts_real_messages(tmp_path, monkeypatch) -> None:
    import core.multi_session as ms
    import os
    from pathlib import Path as P

    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", d)
    monkeypatch.setattr(ms, "REGISTRY_FILE", d / "registry.json")
    for var in ("EPHE_MEMORY_DIR", "EPHE_PROFILE_PATH", "EPHE_CORRECTIONS_PATH",
                "EPHE_FEEDBACK_DIR", "EPHE_SKILLS_DIR"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))

    # The window under test follows the active tier, and both sides of that are the
    # user's now: the tag he runs and the tier that names it. Nothing ships either
    # (owner decision 2026-10-11), so the test states them.
    import core.model_config as mc
    from core.model_config import ModelTier

    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    monkeypatch.setenv("EPHE_MODEL", "gemma4:12b")
    monkeypatch.setattr(mc, "TIER_MAP", {
        ModelTier.FAST: mc.ModelConfig(name="gemma4:12b", tier=ModelTier.FAST),
    })

    sid = ms.create_session("Budget")["id"]
    msgs = [{"role": "user", "content": "x" * 420}]  # 420 chars / 4.2 = 100 tokens
    ms.save_messages(sid, msgs)

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/api/context/budget", params={"session_id": sid})
        assert resp.status_code == 200
        body = resp.json()
        assert body["message_count"] == 1
        assert body["estimated_tokens"] == 100
        # P0-1: the window follows the active tier (FAST 16384), not the legacy 8192.
        assert body["window_source"] == "tier"
        assert body["window_tokens"] == 16384
        assert body["percent"] == round(100 / 16384 * 100, 2)
        assert body["compaction_active"] is False
        assert body["compaction_threshold"] == cc.DEFAULT_MAX_MESSAGES
