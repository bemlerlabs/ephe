"""
◑ Ephe – the watch channel for a running browser session

GET /api/browser/watch/{session} → SSE, one base64 JPEG per event

The visible run needs a frame stream, and the two obvious transports are both wrong here.
A native window could paint the page itself, but that ties watching to the desktop and
leaves the PWA with nothing; a websocket over the loopback would be one more listener to
authenticate and one more thing for a firewall notice to explain. This rides the SSE shape
the app already consumes, with one difference that matters: the frame is the payload rather
than a description of one.

Three rules decide the rest.

**Read off the event loop.** A queued frame is taken with a blocking `Queue.get`, and on
this loop that starves the very CDP callback that would deliver it — the cast looks dead
while its own reader is what stopped it. Every wait therefore goes through a worker thread.

**Cast only while watched.** The engine is asked for frames when the first reader arrives
and told to stop when the last one leaves, because the measured cost of a cast is real
(54.5 % CPU against 28.8 % idle-cast at the chosen settings) and an unwatched run should
pay nothing for a view nobody is looking at.

**Say what is not there.** A frame arrives when the page changes, so a still page yields
almost none, and a pane that simply stops updating is indistinguishable from a viewer that
was left behind. Each stream opens with a `status` event naming what this session can do
(`casting`, or `watch_unavailable: <reason>`), and keepalives carry the age of the newest
frame so the surface can tell *unchanged* apart from *broken*.

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.refusals import Refused

router = APIRouter(tags=["browser"])

#: Keepalive cadence, and with it the resolution of "how stale is the newest frame".
_PING_SECONDS = 2.0


def _bus(session: str):
    from core import browser_frames

    return browser_frames.bus_for(session)


async def _next_frame(sub, timeout: float):
    """One blocking read, moved off the event loop for the reason in the module docstring."""
    return await asyncio.to_thread(sub.get, timeout)


@router.get("/browser/watch/{session}")
async def get_browser_watch(session: str) -> StreamingResponse:
    """The frames of one browser session, as they are produced."""
    from core.browser import browser_manager

    manager = browser_manager
    # Watching never creates a session. The name arrives over the wire, and a route that
    # started one on demand would hand any reachable caller a way to spawn browser
    # contexts without limit; a run only ever watches a session it already opened.
    if not manager.has_session(session):
        raise Refused("browser_session_unknown", session=session)
    refusal = await manager.start_watch(session)
    if refusal:
        raise Refused("browser_watch_unavailable", reason=refusal.split(": ", 1)[-1])

    bus = _bus(session)

    async def events():
        sub = bus.subscribe()
        try:
            payload = {"state": "casting", "session": session}
            yield f"event: status\ndata: {json.dumps(payload)}\n\n"
            idle = 0.0
            while True:
                frame = await _next_frame(sub, _PING_SECONDS)
                if frame is None:
                    idle += _PING_SECONDS
                    yield (
                        "event: keepalive\ndata: "
                        f"{json.dumps({'since_frame_s': round(idle, 1)})}\n\n"
                    )
                    continue
                idle = 0.0
                yield (
                    "event: frame\n"
                    f"data: {json.dumps(frame, ensure_ascii=False, separators=(',', ':'))}\n\n"
                )
        finally:
            sub.close()
            # The engine is only asked to cast while somebody is watching. Counting is the
            # bus's job; a second reader that arrives later has already been served by the
            # same cast, and the last one out stops it.
            if bus.stats()["subscribers"] == 0:
                # Scheduled, not awaited. This block runs inside the task the server cancels
                # when a reader leaves, and an await in a cancelled scope raises before the
                # engine is told to stop — the cast would then keep running for a pane nobody
                # watches, at the measured cost of a core.
                asyncio.ensure_future(manager.stop_watch(session))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/browser/watch/{session}/hold")
async def post_browser_hold(session: str, body: dict) -> dict:
    """Pause, resume, stop, take the page, or hand it back. The body is one action."""
    from core.browser import browser_manager
    from core.browser_run_view import (
        before_of,
        begin_takeover,
        bind_user_hold,
        finish_takeover,
        mode_of,
        parse_hold,
        pause,
        resume,
        stop,
    )

    if not browser_manager.has_session(session):
        raise Refused("browser_session_unknown", session=session)
    try:
        action = parse_hold(body)
    except ValueError:
        raise Refused("invalid_request") from None
    if action == "pause":
        if not pause(session):
            raise Refused("invalid_request")
    elif action == "resume":
        if not resume(session):
            raise Refused("invalid_request")
    elif action == "stop":
        stop(session)
    elif action == "takeover":
        before = await browser_manager.read_signature(session)
        if not begin_takeover(session, before):
            raise Refused("invalid_request")
    else:
        if mode_of(session) != "takeover":
            raise Refused("invalid_request")
        line = await browser_manager.reconcile_hold(session, before_of(session))
        finish_takeover(session, line)
        bind_user_hold(session, line)
        return {"session": session, "mode": "running", "evidence": line}
    return {"session": session, "mode": mode_of(session)}


@router.post("/browser/watch/{session}/act")
async def post_browser_act(session: str, body: dict) -> dict:
    """One pointer or key from the person holding the page. The answer carries no frame."""
    from core.browser import browser_manager
    from core.browser_run_view import accepts_user_act, parse_act

    if not browser_manager.has_session(session):
        raise Refused("browser_session_unknown", session=session)
    if not accepts_user_act(session):
        raise Refused("invalid_request")
    try:
        act = parse_act(body)
    except ValueError:
        raise Refused("invalid_request") from None
    try:
        await browser_manager.apply_user_act(session, act)
    except LookupError:
        raise Refused("browser_session_unknown", session=session) from None
    except ValueError:
        raise Refused("invalid_request") from None
    return {"session": session, "acted": act["kind"]}
