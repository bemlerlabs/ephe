"""fetch_url returns text, and every failure names its own outcome.

The old contract answered a prompt inside the tool through a local client. On a
hosted engine that call could only fail, and the failure arrived as an ordinary
result. These tests pin the replacement: the text is the result, and a failure is
a coded ``Reason`` whose first word the card can show.
"""
from __future__ import annotations

import pytest

from core.quality import result_decision
from core.reason import reason
from core.tool_markers import FETCH_FAILED_MARKER, FETCH_REFUSED_MARKER
from core.tools import fetch_tools
from core.tools.fetch_tools import FetchRefused, FetchTransport, fetch_url


@pytest.fixture(autouse=True)
def _clean_cache():
    fetch_tools._FETCH_CACHE.clear()
    yield
    fetch_tools._FETCH_CACHE.clear()


def _serves(monkeypatch, status: int, body: str):
    calls = []

    async def fake_get(url):
        calls.append(url)
        return status, body

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    return calls


def _raises(monkeypatch, exc: BaseException):
    async def fake_get(url):
        raise exc

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)


@pytest.mark.asyncio
async def test_success_without_prompt_returns_the_document(monkeypatch):
    _serves(monkeypatch, 200, "<h1>Titel</h1><p>Inhalt</p>")

    out = await fetch_url("https://example.test/page")

    assert "# Titel" in out and "Inhalt" in out


@pytest.mark.asyncio
async def test_success_with_prompt_returns_text_not_an_answer(monkeypatch):
    _serves(monkeypatch, 200, "<p>Der Seitentext.</p>")

    out = await fetch_url("https://example.test/page", "what does the page say?")

    assert "Der Seitentext." in out
    assert out == await fetch_url("https://example.test/page")


@pytest.mark.asyncio
async def test_http_error_carries_status_and_code(monkeypatch):
    _serves(monkeypatch, 403, "forbidden")

    out = await fetch_url("https://example.test/secret")

    assert str(out).startswith(FETCH_FAILED_MARKER)
    assert out.code == "fetch_http_error"
    assert out.params == {"status": "403", "url": "https://example.test/secret"}
    assert "403" in out


@pytest.mark.asyncio
async def test_timeout_is_its_own_code(monkeypatch):
    _raises(monkeypatch, FetchTransport("example.test: TimeoutException"))

    out = await fetch_url("https://example.test/slow")

    assert str(out).startswith(FETCH_FAILED_MARKER)
    assert out.code == "fetch_timeout"


@pytest.mark.asyncio
async def test_unreachable_host_is_not_a_timeout(monkeypatch):
    _raises(monkeypatch, FetchTransport("example.test: ConnectError"))

    out = await fetch_url("https://example.test/gone")

    assert out.code == "fetch_unreachable"


@pytest.mark.asyncio
async def test_empty_url_is_coded():
    out = await fetch_url("   ")

    assert str(out).startswith(FETCH_FAILED_MARKER)
    assert out.code == "fetch_empty_url"


@pytest.mark.asyncio
async def test_refused_target_keeps_the_blockade_axis(monkeypatch):
    note = reason(
        "metadata_host", "169.254.169.254 is the metadata endpoint", host="169.254.169.254"
    )
    _raises(monkeypatch, FetchRefused(note))

    out = await fetch_url("http://169.254.169.254/latest/meta-data/")

    assert str(out).startswith(FETCH_REFUSED_MARKER)
    assert out.code == "metadata_host"
    assert out.params["host"] == "169.254.169.254"
    assert result_decision(out) == "blocked"


@pytest.mark.asyncio
async def test_blocked_scheme_is_coded(monkeypatch):
    note = reason("scheme_blocked", "file: is blocked", scheme="file")
    _raises(monkeypatch, FetchRefused(note))

    out = await fetch_url("file:///etc/passwd")

    assert out.code == "fetch_scheme_blocked"
    assert out.params["scheme"] == "file"
    assert str(out).startswith(FETCH_REFUSED_MARKER)


@pytest.mark.asyncio
async def test_uncoded_refusal_gets_the_generic_code(monkeypatch):
    _raises(monkeypatch, FetchRefused("Redirect without a target."))

    out = await fetch_url("https://example.test/redirect")

    assert out.code == "fetch_refused"
    assert str(out).startswith(FETCH_REFUSED_MARKER)


@pytest.mark.asyncio
async def test_cache_hit_avoids_a_second_request(monkeypatch):
    calls = _serves(monkeypatch, 200, "<p>einmal</p>")

    first = await fetch_url("https://example.test/cached")
    second = await fetch_url("https://example.test/cached")

    assert first == second
    assert calls == ["https://example.test/cached"]
