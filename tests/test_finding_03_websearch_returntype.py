"""
tests/test_finding_03_websearch_returntype.py

Finding 3: the web_search() signature promised list[dict], but the function
returned str. Fix: the signature was corrected to -> str.

Given-When-Then Tests:
  1. GIVEN valid query WHEN web_search() returns results THEN type is str
  2. GIVEN valid query WHEN no results found THEN type is str (not list)
  3. GIVEN empty query WHEN web_search() THEN raises ValueError
"""
import asyncio
import re
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

import pytest

from tests.web_search_seam import web_search_module


# Test 1: GIVEN results WHEN search THEN returns str

@pytest.mark.asyncio
async def test_given_results_when_search_then_returns_str():
    """GIVEN DuckDuckGo returns results WHEN web_search() THEN return type is str."""
    mock_results = [
        {"title": "Test", "href": "https://example.com", "body": "A test result"},
    ]

    with patch.object(web_search_module, "DDGS") as MockDDGS:
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.return_value = mock_results
        MockDDGS.return_value = mock_instance

        from core.tools import web_search
        result = await web_search("test query")

    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert [urlparse(u).netloc for u in re.findall(r"https?://\S+", result)] == ["example.com"]
    assert "Test" in result


# Test 2: GIVEN no results WHEN search THEN returns str (not list)

@pytest.mark.asyncio
async def test_given_no_results_when_search_then_returns_str():
    """GIVEN DuckDuckGo returns empty WHEN web_search() THEN returns str, not list."""
    with patch.object(web_search_module, "DDGS") as MockDDGS:
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.return_value = []
        MockDDGS.return_value = mock_instance

        from core.tools import web_search
        result = await web_search("nonexistent query")

    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert "No results found" in result


# Test 3: GIVEN empty query WHEN search THEN ValueError

@pytest.mark.asyncio
async def test_given_empty_query_when_search_then_raises_valueerror():
    """GIVEN empty string WHEN web_search() THEN raises ValueError."""
    from core.tools import web_search

    with pytest.raises(ValueError, match="empty"):
        await web_search("")

    with pytest.raises(ValueError, match="empty"):
        await web_search("   ")


def test_web_search_has_hard_timeout():
    """W19-Bench finding: DDGS (the primp backend) hangs intermittently forever —
    web_search has to wrap the whole search operation in a hard asyncio.wait_for,
    otherwise the agent loop stalls (bench: 700s+ of silence)."""
    import importlib
    import inspect
    import sys

    ws = sys.modules.get("core.tools.web_search") or importlib.import_module("core.tools.web_search")

    src = inspect.getsource(ws.web_search)
    assert "wait_for" in src, "web_search spannt die Suche nicht in wait_for ein"
    assert ws.WEB_SEARCH_TIMEOUT_SECONDS <= 60.0
