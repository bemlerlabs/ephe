"""A silent turn still shows a heartbeat.

The engine call between two tool rounds streams nothing, so a turn could stand
still for a minute with no frame at all and read as a hung run. The turn beat
sends one `progress` frame whenever nothing else went out for
`TURN_SILENT_BEAT_S`, and the frontend renders it as the live "Working for …"
line.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from server.routes import chat as chat_route


def _data_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for part in raw.split("\n\n"):
        part = part.strip()
        if part.startswith("data: "):
            events.append(json.loads(part[len("data: "):]))
    return events


async def _drive(monkeypatch, chat_impl) -> str:
    monkeypatch.setattr(chat_route, "chat_with_tools", chat_impl)
    monkeypatch.setattr(chat_route, "TURN_SILENT_BEAT_S", 0.2)
    req = chat_route.StreamRequest(message="ping", session_id="s-beat")
    resp = await chat_route.chat_stream(req)
    gen = resp.body_iterator
    chunks: list[str] = []
    while True:
        try:
            chunks.append(await asyncio.wait_for(gen.__anext__(), 10.0))  # type: ignore[attr-defined]
        except StopAsyncIteration:
            break
    return "".join(chunks)


@pytest.mark.asyncio
async def test_a_silent_turn_emits_progress_beats(monkeypatch):
    async def silent_turn(**kwargs):
        await asyncio.sleep(0.7)
        kwargs["on_chunk"]("done")
        return "done"

    raw = await _drive(monkeypatch, silent_turn)
    beats = [e for e in _data_events(raw) if e.get("type") == "progress" and e.get("phase") == "turn_beat"]
    assert len(beats) >= 2, [e.get("type") for e in _data_events(raw)]
    elapsed = [beat["elapsed_ms"] for beat in beats]
    assert elapsed == sorted(elapsed) and elapsed[-1] > elapsed[0]
    assert all(beat["turn_id"] for beat in beats)


@pytest.mark.asyncio
async def test_the_beat_stops_at_done(monkeypatch):
    async def quick_turn(**kwargs):
        kwargs["on_chunk"]("ok")
        return "ok"

    raw = await _drive(monkeypatch, quick_turn)
    types = [e.get("type") for e in _data_events(raw)]
    assert types[-1] == "done"
    assert "turn_beat" not in [e.get("phase") for e in _data_events(raw) if e.get("type") == "progress"]
