"""server/routes/events.py — one stream for the live surfaces (L1).

The fleet and the cell life used to be read on two client beats (3 s and 5 s). This
route carries both as one server-sent event: a snapshot is re-read on a short tick,
only a changed snapshot leaves the process, and a reconnect needs no replay because
every frame is the full state. The client keeps its polls as the fallback for a
browser without a stream or a listener that has not opened yet.

The tick is a measurement, not a claim: `TICK_SECONDS` is the worst-case delay
between a state change and the frame that carries it. An event-hook version (the
<8 ms target of the directive) belongs to the writers; this route reads finished
snapshots.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from core.ephemeral_cell import cell_life
from server.routes.workspaces import fleet_payload

router = APIRouter(tags=["Events"])

TICK_SECONDS = 0.25
FLEET_EVERY_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0
MAX_STREAMS = 16
_active = 0


def _snapshot(session: str | None, *, read_fleet: bool) -> dict[str, Any]:
    """The state one frame carries. The fleet half is re-read at its own beat."""
    snap: dict[str, Any] = {}
    if read_fleet:
        snap["fleet"] = fleet_payload()
    snap["cell"] = cell_life(session) if session else None
    return snap


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


async def _frames(request: Request, session_id: str | None):
    """The frames of one connection; the route's counter is released here."""
    try:
        yield ": connected\n\n"
        yield "event: hello\ndata: " + json.dumps(
            {"interval_ms": int(TICK_SECONDS * 1000), "session": session_id or ""}
        ) + "\n\n"
        last_sent = ""
        frame_id = 0
        loop = asyncio.get_running_loop()
        last_fleet = 0.0
        last_keepalive = loop.time()
        while True:
            if await request.is_disconnected():
                break
            now = loop.time()
            read_fleet = now - last_fleet >= FLEET_EVERY_SECONDS or last_fleet == 0.0
            fresh = await asyncio.to_thread(_snapshot, session_id, read_fleet=read_fleet)
            if read_fleet:
                last_fleet = now
            # Keep the last fleet half on a tick that did not re-read it.
            if not read_fleet:
                previous = json.loads(last_sent) if last_sent else {}
                if "fleet" in previous:
                    fresh["fleet"] = previous["fleet"]
            encoded = _canonical(fresh)
            if encoded != last_sent:
                frame_id += 1
                last_sent = encoded
                last_keepalive = now
                yield f"id: {frame_id}\nevent: multiplex\ndata: {encoded}\n\n"
            elif now - last_keepalive >= KEEPALIVE_SECONDS:
                last_keepalive = now
                yield ": keepalive\n\n"
            await asyncio.sleep(TICK_SECONDS)
    finally:
        global _active
        _active = max(0, _active - 1)


@router.get("/events/multiplex")
async def multiplex(
    request: Request,
    session: str = Query(default=""),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """SSE: ``hello`` once, then a full ``multiplex`` snapshot whenever it changed.

    ``Last-Event-ID`` is accepted and ignored on purpose: a snapshot has no delta to
    replay, so the first frame after a reconnect is already complete.
    """
    global _active
    if _active >= MAX_STREAMS:
        raise HTTPException(status_code=503, detail="too many live streams")
    _active += 1
    session_id = session.strip() or None
    _ = last_event_id
    return StreamingResponse(
        _frames(request, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
