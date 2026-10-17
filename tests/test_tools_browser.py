"""
◑ Ephe – core.tools.browser_tools (Phase 0.8 TDD)
tests/test_tools_browser.py

Covers browser_go, browser_screenshot, browser_click, browser_type, browser_press.

Given / When / Then – strict adherence.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools.browser_tools import (
    browser_click,
    browser_go,
    browser_press,
    browser_screenshot,
    browser_type,
)


class TestBrowserGo:

    @pytest.mark.asyncio
    async def test_navigates_to_url(self):
        """
        GIVEN  a valid URL
        WHEN   browser_go("https://example.com") is called
        THEN   browser_manager.go is called with the URL
        """
        with patch("core.tools.browser_tools._get_browser_manager") as mock_bm:
            mock_bm.return_value.go = AsyncMock(return_value="Navigated to https://example.com")

            result = await browser_go("https://example.com")

            assert "Navigated" in result or "example" in result
            mock_bm.return_value.go.assert_called_once_with("https://example.com")


class TestBrowserScreenshot:

    @pytest.mark.asyncio
    async def test_saves_screenshot(self):
        """
        GIVEN  the browser is active
        WHEN   browser_screenshot() is called
        THEN   the screenshot is saved as a file
        AND    the return value contains "![Browser]"
        """
        with patch("core.tools.browser_tools._get_browser_manager") as mock_bm, \
             patch("core.tools.browser_tools.Path.mkdir"), \
             patch("builtins.open", new_callable=MagicMock):
            mock_bm.return_value.screenshot = AsyncMock(return_value="aW1hZ2U=")

            result = await browser_screenshot()

            assert "![Browser]" in result
            mock_bm.return_value.screenshot.assert_called_once()


class TestBrowserClick:

    @pytest.mark.asyncio
    async def test_clicks_target(self):
        """
        GIVEN  a description of a UI element
        WHEN   browser_click("Accept Cookies") is called
        THEN   browser_manager.click is called
        """
        with patch("core.tools.browser_tools._get_browser_manager") as mock_bm:
            mock_bm.return_value.click = AsyncMock(return_value="Clicked Accept Cookies")

            result = await browser_click("Accept Cookies")

            assert "Clicked" in result or "Accept" in result
            mock_bm.return_value.click.assert_called_once_with("Accept Cookies")


class TestBrowserType:

    @pytest.mark.asyncio
    async def test_types_text(self):
        """
        GIVEN  text to type
        WHEN   browser_type("Hello World") is called
        THEN   browser_manager.type_text is called with the text
        """
        with patch("core.tools.browser_tools._get_browser_manager") as mock_bm:
            mock_bm.return_value.type_text = AsyncMock(return_value="Typed text")

            result = await browser_type("Hello World")

            mock_bm.return_value.type_text.assert_called_once_with("Hello World")


class TestBrowserPress:

    @pytest.mark.asyncio
    async def test_presses_key(self):
        """
        GIVEN  a key name
        WHEN   browser_press("Enter") is called
        THEN   browser_manager.press is called with "Enter"
        """
        with patch("core.tools.browser_tools._get_browser_manager") as mock_bm:
            mock_bm.return_value.press = AsyncMock(return_value="Pressed Enter")

            result = await browser_press("Enter")

            mock_bm.return_value.press.assert_called_once_with("Enter")
