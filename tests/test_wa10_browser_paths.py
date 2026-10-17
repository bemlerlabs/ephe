"""WA-10 — the browser manager's page-interaction paths (core/browser.py).

The ranked gap (docs/COVERAGE_GAPS_2026-10-11.md item 9) left core/browser.py at
57%: the constructor and the singleton were pinned, everything a session
actually does was not. These tests drive one manager per fake page and pin the
contract each method carries — a readable answer instead of a traceback, the URL
policy as the only navigation door, and the browser_exec helper namespace bound
to one session loop.
"""
from __future__ import annotations

import asyncio
import base64

import pytest

import core.browser as browser_mod
from core.browser import (
    BROWSER_INSTALL_HINT,
    BrowserUnavailable,
    PlaywrightBrowserManager,
    _launch_chromium,
)
from core.reason import Reason, reason
from core.tool_markers import BROWSER_DENIED_MARKER


# test doubles


class _FakeCDPSession:
    def __init__(self, result=None, error=None):
        self.result = {"ok": True} if result is None else result
        self.error = error
        self.sent: list[tuple] = []

    async def send(self, method, params=None):
        self.sent.append((method, params))
        if self.error is not None:
            raise self.error
        return self.result


class _FakeContext:
    def __init__(self, cdp=None):
        self._cdp = cdp or _FakeCDPSession()

    async def new_cdp_session(self):
        return self._cdp


class _FakeKeyboard:
    def __init__(self):
        self.typed: list[tuple] = []
        self.pressed: list[str] = []

    async def type(self, text, delay=None):
        self.typed.append((text, delay))

    async def press(self, key):
        self.pressed.append(key)


class _FakeMouse:
    def __init__(self):
        self.moves: list[tuple] = []
        self.clicks: list[tuple] = []

    async def move(self, x, y):
        self.moves.append((x, y))

    async def click(self, x, y):
        self.clicks.append((x, y))


class _FakePage:
    """One configurable page; every browser method reads or writes it."""

    def __init__(
        self,
        *,
        evaluate=None,
        evaluate_error=None,
        screenshot_bytes=b"\xff\xd8jpeg",
        goto_error=None,
        wait_error=None,
        fill_error=None,
    ):
        self._evaluate = evaluate
        self._evaluate_error = evaluate_error
        self._screenshot_bytes = screenshot_bytes
        self._goto_error = goto_error
        self._wait_error = wait_error
        self._fill_error = fill_error
        self.viewport_size = {"width": 1000, "height": 500}
        self.keyboard = _FakeKeyboard()
        self.mouse = _FakeMouse()
        self.context = _FakeContext()
        self.goto_calls: list[str] = []
        self.filled: tuple[str, str] | None = None

    async def goto(self, url, wait_until=None, timeout=None):
        if self._goto_error is not None:
            raise self._goto_error
        self.goto_calls.append(url)

    async def evaluate(self, code, *args):
        if self._evaluate_error is not None:
            raise self._evaluate_error
        if callable(self._evaluate):
            return self._evaluate(code, *args)
        return self._evaluate

    async def screenshot(self, type=None, quality=None):
        return self._screenshot_bytes

    async def wait_for_load_state(self, state=None, timeout=None):
        if self._wait_error is not None:
            raise self._wait_error

    async def fill(self, selector, text, timeout=None):
        if self._fill_error is not None:
            raise self._fill_error
        self.filled = (selector, text)


def _manager(fake: _FakePage) -> PlaywrightBrowserManager:
    mgr = PlaywrightBrowserManager()
    mgr._playwright = object()
    mgr._browser = object()
    mgr._page = fake
    return mgr


@pytest.fixture
def fast_sleep(monkeypatch):
    """The navigation render buffers are real waits; the tests do not need them."""

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(browser_mod.asyncio, "sleep", _noop)


# navigation: the URL policy is the only door


def test_go_returns_the_page_text_after_a_load(fast_sleep):
    fake = _FakePage(evaluate="hello page")
    mgr = _manager(fake)

    out = asyncio.run(mgr.go("https://example.com"))

    assert fake.goto_calls == ["https://example.com"]
    assert out == "hello page"


def test_a_load_failure_is_a_readable_line(fast_sleep):
    fake = _FakePage(goto_error=RuntimeError("net::ERR_NAME_NOT_RESOLVED"))
    mgr = _manager(fake)

    out = asyncio.run(mgr.go("https://nope.invalid"))

    assert out.startswith("Error loading https://nope.invalid:")
    assert "ERR_NAME_NOT_RESOLVED" in out


def test_a_coded_refusal_travels_as_a_reason(monkeypatch, fast_sleep):
    decision = reason("browser_scheme_blocked", "gopher: is blocked", scheme="gopher")
    monkeypatch.setattr(browser_mod, "url_policy", lambda _url: (False, decision))
    mgr = _manager(_FakePage())

    out = asyncio.run(mgr.go("gopher://127.0.0.1/"))

    assert isinstance(out, Reason)
    assert out.code == "browser_scheme_blocked"
    assert out.startswith(BROWSER_DENIED_MARKER)


def test_a_codeless_refusal_is_the_plain_marker_line(monkeypatch, fast_sleep):
    monkeypatch.setattr(browser_mod, "url_policy", lambda _url: (False, "plain refusal"))
    mgr = _manager(_FakePage())

    out = asyncio.run(mgr.go("javascript:alert(1)"))

    assert out == f"{BROWSER_DENIED_MARKER} plain refusal"
    assert not isinstance(out, Reason)


def test_new_tab_and_goto_url_go_through_go(fast_sleep):
    fake = _FakePage(evaluate="reached")
    mgr = _manager(fake)

    assert asyncio.run(mgr.new_tab("https://a.test")) == "reached"
    assert asyncio.run(mgr.goto_url("https://b.test")) == "reached"
    assert fake.goto_calls == ["https://a.test", "https://b.test"]


# text reading and screenshots


def test_get_text_marks_an_empty_body():
    mgr = _manager(_FakePage(evaluate=""))
    assert asyncio.run(mgr.get_text()) == "No visible text."


def test_get_text_truncates_a_huge_body():
    mgr = _manager(_FakePage(evaluate="x" * 16000))
    out = asyncio.run(mgr.get_text())
    assert out.startswith("x" * 15000)
    assert out.endswith("[page text truncated to 15,000 characters]")


def test_get_text_reports_a_read_failure():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("detached frame")))
    out = asyncio.run(mgr.get_text())
    assert out.startswith("Could not read text:")
    assert "detached frame" in out


def test_screenshot_returns_base64_jpeg():
    mgr = _manager(_FakePage(screenshot_bytes=b"\xff\xd8\xff payload"))
    out = asyncio.run(mgr.screenshot())
    assert base64.b64decode(out) == b"\xff\xd8\xff payload"


# click, type, press


def test_click_scales_normalized_coords_into_the_viewport(monkeypatch, fast_sleep):
    async def _bbox(*_a, **_k):
        return (0.2, 0.4, 0.4, 0.6)

    monkeypatch.setattr(browser_mod, "_get_bounding_box", _bbox)
    fake = _FakePage()
    mgr = _manager(fake)

    out = asyncio.run(mgr.click("Save"))

    assert out == "Click executed successfully."
    # center of the box is (0.5, 0.3) of a 1000x500 viewport -> (500, 150)
    assert fake.mouse.moves == [pytest.approx((500.0, 150.0))]
    assert fake.mouse.clicks == [pytest.approx((500.0, 150.0))]


@pytest.mark.parametrize("coords", ["UNSURE", None])
def test_click_reports_an_unfound_target(monkeypatch, coords, fast_sleep):
    async def _bbox(*_a, **_k):
        return coords

    monkeypatch.setattr(browser_mod, "_get_bounding_box", _bbox)
    mgr = _manager(_FakePage())

    out = asyncio.run(mgr.click("Ghost button"))

    assert out == "Error: target 'Ghost button' not found on the browser screen."


def test_type_text_types_into_the_keyboard(fast_sleep):
    fake = _FakePage()
    mgr = _manager(fake)

    out = asyncio.run(mgr.type_text("hello"))

    assert fake.keyboard.typed == [("hello", 20)]
    assert "hello" in out


def test_press_sends_the_key(fast_sleep):
    fake = _FakePage()
    mgr = _manager(fake)

    out = asyncio.run(mgr.press("Enter"))

    assert fake.keyboard.pressed == ["Enter"]
    assert "Enter" in out


# scroll


@pytest.mark.parametrize(
    "direction, expected_xy",
    [("down", [0, 600]), ("up", [0, -600]), ("left", [-600, 0]), ("right", [600, 0])],
)
def test_scroll_translates_the_direction_into_deltas(direction, expected_xy):
    seen = {}

    def _eval(code, args=None):
        seen["delta"] = args
        return 42

    mgr = _manager(_FakePage(evaluate=_eval))
    out = asyncio.run(mgr.scroll(direction, 600))

    assert seen["delta"] == expected_xy
    assert out == f"Scrolled {direction} 600px — scrollY now 42."


def test_scroll_clamps_the_amount():
    seen = {}

    def _eval(code, args=None):
        seen["delta"] = args
        return 0

    mgr = _manager(_FakePage(evaluate=_eval))
    asyncio.run(mgr.scroll("down", 10**9))
    assert seen["delta"] == [0, 10000]


def test_scroll_reports_a_failure():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("no window")))
    out = asyncio.run(mgr.scroll("down"))
    assert out == "[Scroll failed: no window]"


# evaluate and the JSON fallback


def test_evaluate_returns_json_and_truncates():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: {"blob": "y" * 20000}))
    out = asyncio.run(mgr.evaluate("document.title"))
    assert out.endswith("[truncated to 12,000 characters]")


def test_evaluate_refuses_an_empty_expression():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: None))
    assert asyncio.run(mgr.evaluate("   ")) == "[Evaluate failed: empty expression]"


def test_evaluate_reports_a_page_error():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("boom")))
    assert asyncio.run(mgr.evaluate("1+1")) == "[Evaluate failed: boom]"


def test_evaluate_falls_back_to_str_for_a_non_serializable_result():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: {1, 2, 3}))
    out = asyncio.run(mgr.evaluate("new Set([1,2,3])"))
    assert out.startswith("{") and "1" in out


def test_js_is_evaluate_with_a_thinner_name():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: "42"))
    # evaluate JSON-serializes its result, so a string arrives quoted.
    assert asyncio.run(mgr.js("6*7")) == '"42"'


# clipboard and display


def test_clipboard_read_returns_the_text():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: "copied"))
    assert asyncio.run(mgr.clipboard_read()) == "copied"


def test_clipboard_read_reports_a_failure():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("denied")))
    assert asyncio.run(mgr.clipboard_read()) == "[Clipboard read failed: denied]"


def test_clipboard_write_confirms():
    seen = {}

    def _eval(code, arg=None):
        seen["arg"] = arg
        return None

    mgr = _manager(_FakePage(evaluate=_eval))
    out = asyncio.run(mgr.clipboard_write("payload"))
    assert seen["arg"] == "payload"
    assert out == "Clipboard updated."


def test_clipboard_write_reports_a_failure():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("nope")))
    assert asyncio.run(mgr.clipboard_write("x")) == "[Clipboard write failed: nope]"


def test_display_info_formats_the_viewport():
    info = {"viewport_width": 1000, "viewport_height": 500, "device_pixel_ratio": 2, "scroll_height": 3000}
    mgr = _manager(_FakePage(evaluate=lambda code, *a: info))
    out = asyncio.run(mgr.display_info())
    assert out == "viewport 1000x500, dpr 2, scroll_height 3000"


def test_display_info_reports_a_failure():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("gone")))
    assert asyncio.run(mgr.display_info()) == "[Display info failed: gone]"


def test_display_info_rejects_a_non_dict_result():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: 7))
    out = asyncio.run(mgr.display_info())
    assert out.startswith("[Display info failed: unexpected")


# load settling and page info


def test_wait_for_load_swallows_a_timeout():
    mgr = _manager(_FakePage(wait_error=TimeoutError("networkidle never came")))
    assert asyncio.run(mgr.wait_for_load()) == "load settled"


def test_page_info_returns_the_summary_dict():
    summary = {"title": "Docs", "url": "https://x.test", "text": "body"}
    mgr = _manager(_FakePage(evaluate=lambda code, *a: summary))
    assert asyncio.run(mgr.page_info()) == summary


def test_page_info_reports_a_failure():
    mgr = _manager(_FakePage(evaluate_error=RuntimeError("crashed")))
    assert asyncio.run(mgr.page_info()) == {"error": "crashed"}


def test_page_info_wraps_a_non_dict_result():
    mgr = _manager(_FakePage(evaluate=lambda code, *a: "raw text"))
    assert asyncio.run(mgr.page_info()) == {"raw": "raw text"}


# form fill and coordinate click


def test_fill_input_reports_the_selector():
    fake = _FakePage()
    mgr = _manager(fake)
    out = asyncio.run(mgr.fill_input("#email", "a@b.test"))
    assert fake.filled == ("#email", "a@b.test")
    assert out == "filled #email"


def test_fill_input_reports_a_failure():
    mgr = _manager(_FakePage(fill_error=RuntimeError("no such node")))
    assert asyncio.run(mgr.fill_input("#missing", "x")) == "[fill failed: no such node]"


def test_click_at_xy_clicks_the_given_point(fast_sleep):
    fake = _FakePage()
    mgr = _manager(fake)
    out = asyncio.run(mgr.click_at_xy(10, 20))
    assert fake.mouse.moves == [(10, 20)]
    assert fake.mouse.clicks == [(10, 20)]
    assert out == "clicked at 10,20"


# screenshot capture to disk


def test_capture_screenshot_writes_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(tmp_path))
    mgr = _manager(_FakePage(screenshot_bytes=b"jpeg-bytes"))

    path = asyncio.run(mgr.capture_screenshot())

    assert path.startswith(str(tmp_path))
    assert path.endswith(".jpeg")
    with open(path, "rb") as handle:
        assert handle.read() == b"jpeg-bytes"


# raw CDP


def test_cdp_serializes_the_result():
    cdp = _FakeCDPSession(result={"frameTree": "root"})
    fake = _FakePage()
    fake.context = _FakeContext(cdp)
    mgr = _manager(fake)

    out = asyncio.run(mgr.cdp("Page.getFrameTree"))

    assert out == '{"frameTree": "root"}'
    assert cdp.sent == [("Page.getFrameTree", None)]


def test_cdp_reports_a_failure():
    cdp = _FakeCDPSession(error=RuntimeError("Unknown command"))
    fake = _FakePage()
    fake.context = _FakeContext(cdp)
    mgr = _manager(fake)

    assert asyncio.run(mgr.cdp("Nope.run")) == "[cdp failed: Unknown command]"


# the session loop


def test_a_session_reuses_its_loop():
    try:
        first = browser_mod._get_or_create_loop("wa10-reuse")
        second = browser_mod._get_or_create_loop("wa10-reuse")
        assert first is second
    finally:
        loop = browser_mod._SESSION_LOOPS.pop("wa10-reuse", None)
        if loop is not None:
            loop.close()


def test_a_closed_loop_is_replaced():
    try:
        first = browser_mod._get_or_create_loop("wa10-closed")
        first.close()
        second = browser_mod._get_or_create_loop("wa10-closed")
        assert second is not first
    finally:
        loop = browser_mod._SESSION_LOOPS.pop("wa10-closed", None)
        if loop is not None and not loop.is_closed():
            loop.close()


# a page injected after the outer check is still observed


class _InjectingLock:
    """Simulates the race the inner ``_page`` re-check guards against."""

    def __init__(self, manager, page):
        self._manager = manager
        self._page = page

    async def __aenter__(self):
        self._manager._page = self._page
        return self

    async def __aexit__(self, *exc):
        return False


def test_ensure_page_rechecks_the_injected_page_under_the_lock():
    injected = _FakePage()
    mgr = PlaywrightBrowserManager()
    mgr._page = None
    mgr._lock = _InjectingLock(mgr, injected)

    assert asyncio.run(mgr._ensure_page()) is injected


# the launch path: no injected page, so a real context/page must be born


class _FakeBrowserContext:
    """One page context; carries what ``new_context`` was asked to build."""

    def __init__(self):
        self.pages: list = []
        self.viewport = None
        self.user_agent = None

    async def new_page(self):
        page = _FakePage()
        self.pages.append(page)
        return page


class _FakeBrowser:
    def __init__(self):
        self.contexts: list[_FakeBrowserContext] = []

    async def new_context(self, viewport=None, user_agent=None):
        context = _FakeBrowserContext()
        context.viewport = viewport
        context.user_agent = user_agent
        self.contexts.append(context)
        return context


def test_ensure_page_launches_a_browser_and_opens_one_session_page(monkeypatch):
    started = {"start": 0, "launch": 0}

    class _Startup:
        async def start(self):
            started["start"] += 1
            return "PW"

    monkeypatch.setattr(browser_mod, "async_playwright", lambda: _Startup())

    async def _launch(pw):
        started["launch"] += 1
        assert pw == "PW"
        return _FakeBrowser()

    monkeypatch.setattr(browser_mod, "_launch_chromium", _launch)

    mgr = PlaywrightBrowserManager()
    page = asyncio.run(mgr._ensure_page("fresh"))

    assert started == {"start": 1, "launch": 1}
    assert mgr._playwright == "PW"
    assert mgr._pages["fresh"][1] is page
    context = mgr._browser.contexts[0]
    assert context.viewport == {"width": 1280, "height": 800}
    assert "Chrome/120" in context.user_agent
    assert context.pages == [page]


def test_ensure_page_reuses_an_open_session_page_without_relaunching(monkeypatch):
    mgr = PlaywrightBrowserManager()
    mgr._playwright = object()
    mgr._browser = _FakeBrowser()
    existing = _FakePage()
    mgr._pages["s"] = ("ctx", existing)

    def _must_not_restart():
        raise AssertionError("a running browser must not restart")

    monkeypatch.setattr(browser_mod, "async_playwright", _must_not_restart)

    assert asyncio.run(mgr._ensure_page("s")) is existing
    assert mgr._browser.contexts == []


# launch: the missing browser binary is one actionable line


class _LaunchChromium:
    def __init__(self, error=None, browser="BROWSER"):
        self._error = error
        self._browser = browser

    async def launch(self, headless=True):
        if self._error is not None:
            raise self._error
        return self._browser


class _LaunchPlaywright:
    def __init__(self, chromium):
        self.chromium = chromium


def test_launch_maps_a_missing_binary_to_one_actionable_error():
    pw = _LaunchPlaywright(_LaunchChromium(error=Exception("Executable doesn't exist at /x/chromium")))
    with pytest.raises(BrowserUnavailable) as excinfo:
        asyncio.run(_launch_chromium(pw))
    assert BROWSER_INSTALL_HINT in str(excinfo.value)


def test_launch_reraises_an_unrelated_startup_error():
    pw = _LaunchPlaywright(_LaunchChromium(error=Exception("sandbox crash")))
    with pytest.raises(Exception, match="sandbox crash"):
        asyncio.run(_launch_chromium(pw))


def test_launch_returns_the_browser_when_it_starts():
    pw = _LaunchPlaywright(_LaunchChromium(browser="started"))
    assert asyncio.run(_launch_chromium(pw)) == "started"


# the browser_exec helper namespace


def test_make_browser_helpers_exposes_the_documented_names(monkeypatch):
    monkeypatch.setattr(browser_mod, "browser_manager", _manager(_FakePage(evaluate=lambda c, *a: "ok")))
    helpers = browser_mod.make_browser_helpers("wa10-helpers")

    assert set(helpers) >= {
        "new_tab", "goto_url", "wait_for_load", "page_info", "js",
        "fill_input", "click_at_xy", "capture_screenshot", "cdp", "browser_manager",
    }
    assert helpers["js"]("1") == '"ok"'
    loop = browser_mod._SESSION_LOOPS.pop("wa10-helpers", None)
    if loop is not None:
        loop.close()


def test_a_helper_runs_its_coroutine_on_the_session_loop(monkeypatch):
    mgr = _manager(_FakePage(evaluate=lambda c, *a: "coro-ran"))
    monkeypatch.setattr(browser_mod, "browser_manager", mgr)

    helpers = browser_mod.make_browser_helpers("wa10-run")
    try:
        assert helpers["js"]("6*7") == '"coro-ran"'
    finally:
        loop = browser_mod._SESSION_LOOPS.pop("wa10-run", None)
        if loop is not None:
            loop.close()


def test_a_helper_returns_a_synchronous_result_unchanged(monkeypatch):
    mgr = _manager(_FakePage())

    def _sync_new_tab(url, session="default"):
        return f"sync:{session}:{url}"

    mgr.new_tab = _sync_new_tab
    monkeypatch.setattr(browser_mod, "browser_manager", mgr)

    helpers = browser_mod.make_browser_helpers("wa10-sync")
    try:
        assert helpers["new_tab"]("https://x.test") == "sync:wa10-sync:https://x.test"
    finally:
        loop = browser_mod._SESSION_LOOPS.pop("wa10-sync", None)
        if loop is not None:
            loop.close()
