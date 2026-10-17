"""J5 parity round: browser_scroll/browser_evaluate + clipboard + display-info.
Hermetic: Playwright page as a fake (evaluate-call log + preset return values)."""
from __future__ import annotations

import asyncio

import pytest


class FakePage:
    """Minimal page: logs evaluate calls, returns the values set in advance."""

    def __init__(self, results: list):
        self.calls: list[tuple[str, object]] = []
        self._results = results

    async def evaluate(self, expression, arg=None):
        self.calls.append((expression, arg))
        value = self._results[len(self.calls) - 1]
        if isinstance(value, Exception):
            raise value
        return value


def _make_manager(fake_page: FakePage):
    from core.browser import PlaywrightBrowserManager

    mgr = PlaywrightBrowserManager()
    mgr._playwright = object()  # prevent start() in _ensure_page
    mgr._browser = object()
    mgr._page = fake_page
    return mgr


# Manager level (logic)

@pytest.mark.asyncio
async def test_scroll_down_positive_delta():
    page = FakePage([600])
    mgr = _make_manager(page)
    out = await mgr.scroll("down", 600)
    assert "down 600px" in out and "600" in out
    expr, arg = page.calls[0]
    assert arg == [0, 600]


@pytest.mark.asyncio
async def test_scroll_up_negative_delta():
    page = FakePage([-800])
    mgr = _make_manager(page)
    await mgr.scroll("up", 800)
    _, arg = page.calls[0]
    assert arg == [0, -800]


@pytest.mark.asyncio
async def test_evaluate_json_serializes_result():
    page = FakePage([{"a": 1, "b": "z"}])
    mgr = _make_manager(page)
    out = await mgr.evaluate("document.something")
    assert '"a": 1' in out and '"b": "z"' in out


@pytest.mark.asyncio
async def test_evaluate_error_is_honest():
    page = FakePage([ValueError("boom")])
    mgr = _make_manager(page)
    out = await mgr.evaluate("1+")
    assert out.startswith("[Evaluate failed") and "boom" in out


@pytest.mark.asyncio
async def test_evaluate_size_cap():
    page = FakePage(["x" * 20000])
    mgr = _make_manager(page)
    out = await mgr.evaluate("big")
    assert len(out) <= 12100
    assert "truncated" in out


@pytest.mark.asyncio
async def test_evaluate_empty_expression_honest():
    page = FakePage([None])
    mgr = _make_manager(page)
    out = await mgr.evaluate("   ")
    assert "empty expression" in out


@pytest.mark.asyncio
async def test_display_info_formats_viewport():
    page = FakePage([{"viewport_width": 1280, "viewport_height": 800,
                      "device_pixel_ratio": 2, "scroll_height": 2400}])
    mgr = _make_manager(page)
    out = await mgr.display_info()
    assert "1280x800" in out and "dpr 2" in out and "2400" in out


# Tool level (forwarding)

@pytest.mark.asyncio
async def test_tool_layer_forwards_to_manager(monkeypatch):
    from core.tools import browser_tools

    class FakeMgr:
        def __init__(self):
            self.seen = []

        async def scroll(self, direction, amount):
            self.seen.append(("scroll", direction, amount))
            return "SC"

        async def evaluate(self, js):
            self.seen.append(("evaluate", js))
            return "EV"

        async def clipboard_read(self):
            self.seen.append(("clip_r",))
            return "CR"

        async def clipboard_write(self, text):
            self.seen.append(("clip_w", text))
            return "CW"

        async def display_info(self):
            self.seen.append(("disp",))
            return "DI"

    fake = FakeMgr()
    import core.browser as browser_module
    monkeypatch.setattr(browser_module, "browser_manager", fake)

    assert await browser_tools.browser_scroll("up", 100) == "SC"
    assert await browser_tools.browser_evaluate("1+1") == "EV"
    assert await browser_tools.clipboard_read() == "CR"
    assert await browser_tools.clipboard_write("txt") == "CW"
    assert await browser_tools.get_display_info() == "DI"
    assert ("scroll", "up", 100) in fake.seen
    assert ("evaluate", "1+1") in fake.seen
    assert ("clip_w", "txt") in fake.seen


# Registry + classification

def test_registry_exposes_j5_tools():
    from core.tools.registry import get_tool_schemas
    names = {s["function"]["name"] for s in get_tool_schemas()}
    assert {"browser_scroll", "browser_evaluate", "clipboard_read",
            "clipboard_write", "get_display_info"} <= names


def test_j5_read_only_tools_non_mutating():
    from core.tools.approval import classify_tool
    assert classify_tool("clipboard_read").is_mutating is False
    assert classify_tool("get_display_info").is_mutating is False


# Missing browser binary: one actionable line (2026-10-09)


def test_missing_chromium_becomes_one_actionable_error():
    """`playwright install` is a separate download, so "no browser" is a supported
    state and must read as one — this is the CI state of every leg, where the shipped
    `browser_exec` core tool answered with Playwright's Error and an 8-frame traceback.
    """
    import core.browser as br

    class _Missing:
        async def launch(self, **_kw):
            raise RuntimeError(
                "BrowserType.launch: Executable doesn't exist at "
                "/home/runner/.cache/ms-playwright/chromium-1200/chrome-linux/chrome"
            )

    class _PW:
        chromium = _Missing()

    with pytest.raises(br.BrowserUnavailable) as excinfo:
        asyncio.run(br._launch_chromium(_PW()))
    assert "python -m playwright install chromium" in str(excinfo.value)

    # The mapping must stay narrow: a different launch failure is NOT a missing
    # download, and rewriting it would hide the real cause behind an install hint.
    class _Other:
        async def launch(self, **_kw):
            raise RuntimeError("kernel refused")

    class _PW2:
        chromium = _Other()

    with pytest.raises(RuntimeError) as other:
        asyncio.run(br._launch_chromium(_PW2()))
    assert not isinstance(other.value, br.BrowserUnavailable)
    assert "kernel refused" in str(other.value)


@pytest.mark.asyncio
async def test_browser_exec_answers_the_hint_without_a_traceback(monkeypatch):
    import core.browser as br
    from core.tools import browser_tools

    async def refuse(self, *_args, **_kwargs):
        raise br.BrowserUnavailable(br.BROWSER_INSTALL_HINT)

    monkeypatch.setattr(br.PlaywrightBrowserManager, "new_tab", refuse)

    out = await browser_tools.browser_exec(
        code="new_tab('data:text/html,<h1>x</h1>')", session="j5-hint"
    )
    assert "playwright install chromium" in out
    assert "Traceback" not in out
