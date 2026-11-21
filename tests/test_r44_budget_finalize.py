"""
◑ Ephe – R44: cap end with a real closing (the finalize round after budget exhaustion).
tests/test_r44_budget_finalize.py

Problem (live audit 28.09.): at cap end the answer stopped at the raw
"[Ephe] Tool budget exhausted …" and WITHOUT a substantive closing — the user
only saw the system line. R44: after the cap comes ONE follow-up round without
tools; the model summary is streamed, the unfinished note hangs on as a
status line. If the follow-up fails: honestly only the note.

RULE: tests BEFORE the implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Msg:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Resp:
    def __init__(self, content):
        self.message = _Msg(content)


class _StubClient:
    def __init__(self, content="Zusammenfassung: 4 Dateien geaendert.", fail=False):
        self.content = content
        self.fail = fail
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return _Resp(self.content)


@pytest.mark.asyncio
async def test_finalize_returns_summary_plus_note():
    """GIVEN a stub client with a closing text (the ollama branch)
    WHEN _finalize_budget_exhausted()
    THEN the result carries the summary text AND the unfinished note with the number;
    the summary was additionally flushed via on_chunk."""
    from core.chat import _finalize_budget_exhausted

    chunks: list[str] = []
    out = await _finalize_budget_exhausted(
        client=_StubClient(),
        provider=SimpleNamespace(provider="ollama"),
        model="gemma4:12b",
        messages=[],
        tools=None,
        on_chunk=chunks.append,
        on_phase=None,
        budget_cap=10,
    )
    assert "Zusammenfassung: 4 Dateien geaendert." in out
    assert "budget exhausted" in out
    assert "10" in out
    assert any("Zusammenfassung" in c for c in chunks)


@pytest.mark.asyncio
async def test_finalize_falls_back_to_note_on_client_error():
    """GIVEN a client that fails on every call
    WHEN _finalize_budget_exhausted()
    THEN only the unfinished note comes back — an honest fail, no crash."""
    from core.chat import _finalize_budget_exhausted

    out = await _finalize_budget_exhausted(
        client=_StubClient(fail=True),
        provider=SimpleNamespace(provider="ollama"),
        model="gemma4:12b",
        messages=[],
        tools=None,
        on_chunk=None,
        on_phase=None,
        budget_cap=10,
    )
    assert "budget exhausted" in out
    assert "unfinished" in out
