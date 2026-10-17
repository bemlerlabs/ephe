"""W7 — own Chromium: PlaywrightBrowserManager 1:1 (singleton + viewport/UA).

Reference parity: ONE browser, ONE context, ONE page — repeated
`_ensure_page` calls create nothing new. The viewport is pinned to 1280×800
and the user agent stays constant (deterministic screenshots).
"""
from __future__ import annotations

import asyncio

import core.browser as browser_mod


class _Page:
    pass


class _Ctx:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.pages = 0

    async def new_page(self) -> _Page:
        self.pages += 1
        return _Page()


class _Browser:
    def __init__(self) -> None:
        self.contexts: list[_Ctx] = []

    async def new_context(self, **kwargs) -> _Ctx:
        ctx = _Ctx(kwargs)
        self.contexts.append(ctx)
        return ctx


class _Chromium:
    def __init__(self) -> None:
        self.launches = 0
        self.browser = _Browser()

    async def launch(self, headless: bool = True) -> _Browser:
        self.launches += 1
        return self.browser


class _PW:
    def __init__(self) -> None:
        self.chromium = _Chromium()


class _PWFactory:
    def __init__(self) -> None:
        self.pw = _PW()
        self.starts = 0

    async def start(self) -> _PW:
        self.starts += 1
        return self.pw


def test_browser_singleton_1_zu_1(monkeypatch):
    """GIVEN the manager is provisioned twice
    WHEN _ensure_page runs once each
    THEN there is exactly ONE Playwright start, ONE browser, ONE context
    and both calls return the very same page."""
    factory = _PWFactory()
    monkeypatch.setattr(browser_mod, "async_playwright", lambda: factory)
    manager = browser_mod.PlaywrightBrowserManager()

    page_1 = asyncio.run(manager._ensure_page())
    page_2 = asyncio.run(manager._ensure_page())

    assert page_1 is page_2
    assert factory.starts == 1
    assert factory.pw.chromium.launches == 1
    assert len(factory.pw.chromium.browser.contexts) == 1
    assert factory.pw.chromium.browser.contexts[0].pages == 1


def test_viewport_and_user_agent_fixed(monkeypatch):
    """GIVEN the context gets created
    WHEN the call arguments are inspected
    THEN the viewport is 1280×800 and the UA is pinned constant."""
    factory = _PWFactory()
    monkeypatch.setattr(browser_mod, "async_playwright", lambda: factory)
    manager = browser_mod.PlaywrightBrowserManager()

    asyncio.run(manager._ensure_page())

    kwargs = factory.pw.chromium.browser.contexts[0].kwargs
    assert kwargs["viewport"] == {"width": 1280, "height": 800}
    ua = kwargs["user_agent"]
    assert ua.startswith("Mozilla/5.0")
    assert "Chrome/120.0.0.0" in ua
