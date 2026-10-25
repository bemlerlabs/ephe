"""J3 parity round: fetch_url (URL→text, TTL cache, caps).
Hermetic: HTTP mocked through the module's own helper; no model is called."""
from __future__ import annotations

import pytest

from core.tools import fetch_tools
from core.tools.fetch_tools import _html_to_text, fetch_url

# Conversion

def test_html_to_text_converts_headings_and_lists():
    html = "<h2>Titel</h2><ul><li>a</li><li>b</li></ul><script>var x=1;</script>"
    out = _html_to_text(html)
    assert "## Titel" in out
    assert "- a" in out and "- b" in out
    assert "var x=1" not in out  # the script tag is removed


def test_html_to_text_size_cap():
    html = "<p>" + ("wort " * 4000) + "</p>"
    out = _html_to_text(html)
    assert len(out) <= fetch_tools._FETCH_HTML_CAP + 60
    assert "truncated" in out


# Cache behavior

@pytest.mark.asyncio
async def test_cache_hit_avoids_second_http(monkeypatch):
    calls = []

    async def fake_get(url):
        calls.append(url)
        return 200, "<h1>T</h1><p>inhalt</p>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    fetch_tools._FETCH_CACHE.clear()

    a = await fetch_url("https://example.org", "frage")
    b = await fetch_url("https://example.org", "frage")
    assert a == b and "# T" in a and "inhalt" in a
    assert len(calls) == 1  # second call comes from the TTL cache


@pytest.mark.asyncio
async def test_cache_expiry_triggers_refetch(monkeypatch):
    calls = []

    async def fake_get(url):
        calls.append(url)
        return 200, "<p>x</p>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    fetch_tools._FETCH_CACHE.clear()

    await fetch_url("https://example.org", "f")
    # Timestamp moved into the past → forced expiry
    stamp, doc = fetch_tools._FETCH_CACHE["https://example.org"]
    fetch_tools._FETCH_CACHE["https://example.org"] = (
        stamp - fetch_tools._FETCH_TTL_SECONDS - 1, doc,
    )
    await fetch_url("https://example.org", "f")
    assert len(calls) == 2


# Error paths + document mode

@pytest.mark.asyncio
async def test_offline_honest_error(monkeypatch):
    async def fail_get(url):
        raise OSError("offline")

    monkeypatch.setattr(fetch_tools, "_http_get", fail_get)
    fetch_tools._FETCH_CACHE.clear()

    res = await fetch_url("https://example.org", "f")
    assert "failed" in res.lower()
    assert getattr(res, "code", "") == "fetch_unreachable"


@pytest.mark.asyncio
async def test_http_status_failure_reported(monkeypatch):
    async def fake_get(url):
        return 404, "not found"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    fetch_tools._FETCH_CACHE.clear()

    res = await fetch_url("https://example.org", "f")
    assert "404" in res


@pytest.mark.asyncio
async def test_document_mode_without_prompt(monkeypatch):
    async def fake_get(url):
        return 200, "<h1>T</h1><p>inhalt</p>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    fetch_tools._FETCH_CACHE.clear()

    res = await fetch_url("https://example.org")
    assert "# T" in res and "inhalt" in res


@pytest.mark.asyncio
async def test_empty_url_is_honest():
    res = await fetch_url("", "f")
    assert "failed" in res.lower()


# Registry integration

def test_registry_exposes_fetch_url():
    from core.tools.registry import get_tool_schemas
    names = {s["function"]["name"] for s in get_tool_schemas()}
    assert "fetch_url" in names


def test_fetch_url_classified_read_only():
    from core.tools.approval import classify_tool
    assert classify_tool("fetch_url").is_mutating is False
