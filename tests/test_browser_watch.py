"""#88 (first slice) — the agent's own page, cast to anyone who asks to watch it.

The design decisions here are all measurements, recorded in
`~/ephe-notes/PLAN_BROWSER_AND_AGENT_VIEW_2026-11-05.md`: `Page.startScreencast` only exists
on a **page-level** CDP session (the context-level one answers "'Page.startScreencast' wasn't
found"), frames are damage-driven so pacing belongs to us, and the protocol's un-acked
window is three frames, which means an ack that waits on a slow reader stalls the page.

What this file pins: a real cast produces a real frame; a cast that cannot start is
*reported* rather than left to look like a still page; the pacing drops intermediate frames
instead of buffering them; and a late joiner is handed the newest frame rather than a blank
pane.
"""
from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import browser_frames
from core.browser import PlaywrightBrowserManager, _WATCH_MIN_INTERVAL


def _jpeg_is_real(data: str) -> bool:
    try:
        raw = base64.b64decode(data)
    except Exception:  # noqa: BLE001 — a bad payload is simply not a frame
        return False
    return raw[:2] == b"\xff\xd8" and len(raw) > 200


# The bus, without an engine


def test_a_late_subscriber_is_handed_the_newest_frame() -> None:
    bus = browser_frames.FrameBus()
    bus.publish({"jpeg": "first"})

    late = bus.subscribe()
    try:
        # the frame already on screen, then the next one
        assert late.get(0.2)["jpeg"] == "first"
        bus.publish({"jpeg": "second"})
        assert late.get(0.2)["jpeg"] == "second"
    finally:
        late.close()


def test_a_reader_that_falls_behind_loses_the_stale_frame() -> None:
    """One slot per reader: the point of a watch is what is on screen now."""
    bus = browser_frames.FrameBus()
    sub = bus.subscribe()
    for index in range(1, 5):
        bus.publish({"jpeg": f"f{index}"})

    assert sub.get(0.2)["jpeg"] == "f4"
    assert bus.stats()["dropped"] == 3, "four frames into one slot"
    sub.close()


def test_closing_a_subscription_stops_the_delivery() -> None:
    bus = browser_frames.FrameBus()
    sub = bus.subscribe()
    sub.close()
    bus.publish({"jpeg": "x"})

    assert bus.stats()["subscribers"] == 0
    assert sub.get(0.05) is None


# The refusal path, with a page that has no CDP at all


class _NoCdpPage:
    viewport_size = {"width": 800, "height": 500}

    class _Context:
        async def new_cdp_session(self, page):
            raise RuntimeError("devtools protocol is not available")

    context = _Context()


def _manager(page) -> PlaywrightBrowserManager:
    manager = PlaywrightBrowserManager()
    manager._page = page
    return manager


def test_an_engine_that_cannot_cast_says_so_instead_of_showing_nothing() -> None:
    """A silent failure here is indistinguishable from a page that has not changed."""
    manager = _manager(_NoCdpPage())

    reason = asyncio.run(manager.start_watch("nose"))

    assert reason.startswith("watch_unavailable:"), reason
    assert manager.is_watched("nose") is False
    asyncio.run(manager.stop_watch("nose"))


# A real cast, on the installed engine


def test_a_watched_page_produces_a_real_frame() -> None:
    manager = PlaywrightBrowserManager()

    async def run() -> tuple[str, dict]:
        try:
            page = await manager._ensure_page("watched")
        except Exception as exc:  # noqa: BLE001 — the binary may not be installed here
            pytest.skip(f"no chromium available: {str(exc)[:90]}")
        try:
            await page.set_content(
                "<body style='height:3000px'><h1 id='t'>before</h1></body>"
            )
            bus = browser_frames.bus_for("watched")
            # subscribe before the cast starts: the engine emits a frame as soon as the
            # cast begins, and a change of text alone may add no further one for seconds
            sub = bus.subscribe()
            refusal = await manager.start_watch("watched")
            assert refusal == "", refusal
            assert manager.is_watched("watched") is True
            await page.evaluate("() => { document.getElementById('t').textContent = 'after'; }")
            deadline = _WATCH_MIN_INTERVAL * 8 + 2.0
            loop = asyncio.get_running_loop()
            started = loop.time()
            frame: dict = {}
            while loop.time() - started < deadline:
                # `Queue.get(timeout=...)` blocks the thread, and on the event loop that
                # means the CDP callback is never delivered — the cast looks dead while it
                # is only being starved by its own reader. Off-thread, as the SSE route
                # will have to do as well.
                got = await asyncio.to_thread(sub.get, 0.25)
                if got and got.get("jpeg"):
                    frame = got
                    break
            return "", frame
        finally:
            await manager.stop_watch("watched")
            await manager._browser.close()

    _, frame = asyncio.run(run())

    assert frame, "the cast produced no frame while a page visibly changed"
    assert _jpeg_is_real(frame["jpeg"]), f"not a jpeg payload: {str(frame)[:60]}"
    # the page was opened at 1280x800 and the cast is requested at 800x500: a viewer that
    # scales by anything else will place its overlay wrong
    assert frame.get("viewport_width") == 1280, frame
    assert frame.get("cast_width") == 800 and frame.get("cast_height") == 500, frame
    print(f"\nbrowser-watch: frame of {len(frame['jpeg'])} b64 chars, "
          f"page {frame.get('viewport_width')}x{frame.get('viewport_height')} "
          f"cast {frame.get('cast_width')}x{frame.get('cast_height')}")


def test_a_session_that_stops_casting_stops_producing_frames() -> None:
    manager = PlaywrightBrowserManager()

    async def run() -> bool:
        try:
            page = await manager._ensure_page("stopped")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no chromium available: {str(exc)[:90]}")
        await page.set_content("<h1>x</h1>")
        await manager.start_watch("stopped")
        await manager.stop_watch("stopped")
        return manager.is_watched("stopped")

    watched_after_stop = asyncio.run(run())
    assert watched_after_stop is False
