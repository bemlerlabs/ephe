"""W2-92 — a browser step answers with what the environment said.

`core/browser.py` used to end every action with its own account: "Click executed
successfully." That is the same class of claim as a model reporting a test it never ran, and
the watchable run cannot be built on it. The contract pinned here is narrow: after an action,
read the page once (address, title, node count, text length, scroll, focus, checked count),
compare against what this manager last read for that session, and say `observed` only when a
number moved — otherwise `unproven`, with the reason.

The first action of a session is the interesting case, because it needs a baseline that does
not exist yet. `_baseline_or_none` reads and stores it; the test below makes the page answer
differently on each read, so a dropped baseline shows up as a wrong verdict rather than as a
pass. That is the bug this file exists to keep dead.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.browser import STEP_EVIDENCE_PREFIX, PlaywrightBrowserManager, step_evidence


def _payload(answer: str) -> dict:
    assert answer.startswith(STEP_EVIDENCE_PREFIX), answer[:80]
    return json.loads(answer[len(STEP_EVIDENCE_PREFIX):].split("\n", 1)[0])


def _seen(**over) -> dict:
    base = {
        "url": "https://example.test/a",
        "title": "A",
        "nodes": 40,
        "text_len": 300,
        "scroll_y": 0,
        "active": "BODY",
        "checked": 0,
    }
    base.update(over)
    return base


# The pure contract


def test_a_step_is_unproven_when_the_page_did_not_answer() -> None:
    line = step_evidence("browser_click", _seen(), None)
    payload = _payload(line)
    assert payload["verdict"] == "unproven"
    assert payload["reason"] == "the page returned nothing readable"


def test_a_step_is_unproven_when_nothing_was_read_before_it() -> None:
    """A signature on its own proves nothing; only a move between two does."""
    payload = _payload(step_evidence("browser_click", None, _seen()))
    assert payload["verdict"] == "unproven"
    assert payload["reason"] == "no state was read before the action"


def test_a_step_is_unproven_when_nothing_the_page_shows_changed() -> None:
    seen = _seen()
    payload = _payload(step_evidence("browser_click", seen, dict(seen)))
    assert payload["verdict"] == "unproven"
    assert payload["reason"] == "nothing observable changed"
    assert payload["delta"] == {
        "nodes": 0, "text_len": 0, "scroll_y": 0, "checked": 0
    }


def test_a_moved_signature_is_observed_with_the_numbers_that_moved() -> None:
    payload = _payload(
        step_evidence("browser_click", _seen(), _seen(nodes=61, text_len=440))
    )
    assert payload["verdict"] == "observed"
    assert payload["delta"]["nodes"] == 21
    assert payload["delta"]["text_len"] == 140
    assert payload["url"] == "https://example.test/a"


def test_a_navigation_or_a_title_move_is_evidence_by_itself() -> None:
    payload = _payload(
        step_evidence("browser_go", _seen(), _seen(url="https://example.test/b", title="B"))
    )
    assert payload["verdict"] == "observed"
    assert payload["delta"]["url_changed"] == 1
    assert payload["delta"]["title_changed"] == 1


def test_a_failed_action_reports_unproven_with_its_own_reason() -> None:
    payload = _payload(step_evidence("browser_click", None, None, error="timeout"))
    assert payload["verdict"] == "unproven" and payload["reason"] == "timeout"


# The manager side


class _FakePage:
    """A page that answers the observation script, once per call, from a list."""

    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, answers: list[dict]) -> None:
        self._answers = answers
        self.calls = 0
        self.mouse = self
        self.keyboard = self

    async def screenshot(self, *args, **kwargs):
        # raw bytes, as the engine returns them; the manager base64s them
        return b"\xff\xd8\xff\xe0fakejpeg\xff\xd9"

    async def evaluate(self, script, *args):
        self.calls += 1
        # past the last scripted answer the page has simply stopped changing
        return dict(self._answers[min(self.calls, len(self._answers)) - 1])

    # a click or a key press is allowed to happen silently in this fake
    async def move(self, *_a, **_k):
        return None

    async def click(self, *_a, **_k):
        return None

    async def type(self, *_a, **_k):
        return None

    async def press(self, *_a, **_k):
        return None


def _patch_locator(replacement):
    """Swap the vision helper `click` uses, and hand back the undo."""
    import core.browser as module

    previous = module._get_bounding_box
    module._get_bounding_box = replacement
    return lambda: setattr(module, "_get_bounding_box", previous)


def _manager_with(page: _FakePage) -> PlaywrightBrowserManager:
    manager = PlaywrightBrowserManager()
    manager._page = page
    return manager


def test_a_first_action_is_measured_against_a_baseline_read_for_it() -> None:
    """The baseline has to survive the action that was measured against it.

    Two different answers with one action in between can only yield `observed` if the
    read taken before the action survived it.
    """
    page = _FakePage([_seen(), _seen(nodes=88, text_len=512)])
    manager = _manager_with(page)
    seen: list[str] = []

    async def fake_locator(b64_img: str, target: str):
        seen.append(target)
        return [0.4, 0.4, 0.6, 0.6]

    monkeypatched = _patch_locator(fake_locator)
    try:
        answer = asyncio.run(manager.click("anything"))
    finally:
        monkeypatched()
    assert seen == ["anything"], "the locator was never asked, so nothing was clicked"

    payload = _payload(answer)
    assert payload["verdict"] == "observed", answer
    assert payload["delta"]["nodes"] == 48


def test_the_next_action_compares_against_the_last_observation() -> None:
    # one read before the first action, one after it, and the second action only reads
    # after — its "before" is the signature the first action already left behind.
    page = _FakePage([_seen(), _seen(nodes=41), _seen(nodes=41, scroll_y=900)])
    manager = _manager_with(page)

    first = _payload(asyncio.run(manager.type_text("hello")))
    second = _payload(asyncio.run(manager.press("Enter")))

    assert first["verdict"] == "observed" and first["delta"]["nodes"] == 1
    assert second["verdict"] == "observed" and second["delta"]["scroll_y"] == 900


def test_an_action_on_a_page_that_stops_answering_is_unproven_not_crashed() -> None:
    class _Broken(_FakePage):
        async def evaluate(self, script, *args):
            raise RuntimeError("target closed")

    broken = _Broken([_seen()])
    manager = _manager_with(broken)

    answer = asyncio.run(manager.press("Enter"))

    assert _payload(answer)["verdict"] == "unproven"


def test_the_evidence_line_stays_worth_its_bytes_in_the_audit_row() -> None:
    """`audit_event` truncates its detail, so an evidence line has to fit beside it."""
    line = step_evidence(
        "browser_go", _seen(), _seen(url="https://example.test/" + "x" * 300,
                                     title="T" * 300, nodes=999)
    )
    assert len(line) < 300, line
    assert _payload(line)["verdict"] == "observed"


# Measured on a real engine, reported as a number rather than enforced as one


def test_the_observation_round_trip_on_a_real_page() -> None:
    """Prints what one extra read costs; asserts only that it is correct.

    No ceiling is asserted here on purpose. A wall-clock number in a parallel test run
    describes the machine, and every timing budget this repository owns lives in the
    serial segment for that reason (tests/timing_segment.py).
    """
    import time

    try:
        from playwright.async_api import async_playwright
    except ImportError:  # pragma: no cover — the lane carries it
        pytest.skip("the automation library is not installed")

    async def measure() -> tuple[float, int]:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as exc:  # noqa: BLE001 — an engine that is not installed
                pytest.skip(f"no chromium binary: {str(exc)[:80]}")
            try:
                manager = _manager_with(await browser.new_page())
                page = manager._page
                await page.set_content("<ul>" + "<li>i</li>" * 40 + "</ul>")
                first = await manager._observe("default")
                started = time.perf_counter()
                second = await manager._observe("default")
                elapsed_ms = (time.perf_counter() - started) * 1000
                assert first and second
                return elapsed_ms, int(second["nodes"])
            finally:
                await browser.close()

    elapsed_ms, nodes = asyncio.run(measure())
    assert nodes > 40, nodes
    print(f"\nstep-evidence: one observation round trip measured {elapsed_ms:.1f} ms")
