"""The web_research tool in front of the loopback fixture.

The provider is a local JSON endpoint, the pages are local routes, and the key
travels in a header. The tool is off by default: the refusal names the settings,
and the tool never falls back to another provider on its own.
"""
from __future__ import annotations

import asyncio

import pytest

from core.tool_markers import RESEARCH_FAILED_MARKER, RESEARCH_REFUSED_MARKER
import core.web_intake.crawl as crawl_module
from core.web_intake import policy
from core.web_intake.crawl import PageCache, clear_robots_cache
from core.tools.web_research import web_research
from tests.web_intake_fixture import FixtureServer

ALLOW_ROBOTS = "User-agent: *\nAllow: /\n"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("EPHE_FETCH_ALLOW_PRIVATE", "1")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_SEARCH_CONFIG", str(tmp_path / "missing-web-search.json"))
    monkeypatch.setattr(crawl_module, "PAGE_CACHE", PageCache(tmp_path / "pages"))

    limiter_class = policy.RateLimiter

    def no_delay(**kwargs) -> policy.RateLimiter:
        kwargs.pop("delay", None)
        return limiter_class(delay=0.0, **kwargs)

    monkeypatch.setattr(policy, "RateLimiter", no_delay)
    clear_robots_cache()
    yield
    clear_robots_cache()


def _search(server: FixtureServer, rows: list[dict]) -> str:
    return server.json("/search", {"results": rows})


def test_a_configured_provider_crawls_pages_and_returns_a_cited_answer(monkeypatch):
    with FixtureServer() as server:
        moon = server.route(
            "/moon",
            "<title>Moon drift</title><p>The moon drifts away from Earth at about "
            "3.8 cm per year, a rate measured by laser ranging.</p>",
        )
        tides = server.route(
            "/tides",
            "<title>Tides</title><p>The tides follow the moon and the sun, and the "
            "moon dominates the daily cycle in every ocean.</p>",
        )
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        _search(
            server,
            [
                {"title": "Moon drift", "url": moon, "snippet": "moon"},
                {"title": "Tides", "url": tides, "snippet": "tides"},
            ],
        )
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("How fast does the moon drift away?", max_pages=2))
        search_headers = server.requests_for("/search")

    assert out.startswith("[web_research]")
    assert "Answer (extractive" in out
    assert "Citation check: " in out and "verified" in out
    assert moon in out and tides in out
    assert search_headers[0]["authorization"] == "Bearer test-key"


def test_without_a_provider_the_tool_refuses_and_names_the_settings(monkeypatch):
    monkeypatch.delenv("EPHE_SEARCH_API_URL", raising=False)
    monkeypatch.delenv("EPHE_SEARCH_API_KEY", raising=False)
    out = asyncio.run(web_research("anything"))
    assert out.startswith(RESEARCH_REFUSED_MARKER)
    assert out.code == "web_search_not_configured"
    assert "EPHE_SEARCH_API_URL" in out
    assert "Next:" in out
    assert out.params["next"]


def test_a_provider_error_is_a_failure_not_a_blockade(monkeypatch):
    with FixtureServer() as server:
        server.json("/search", {"error": "down"}, status=500)
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("anything"))
    assert out.startswith(RESEARCH_FAILED_MARKER)
    assert out.code == "web_search_failed"
    assert "HTTP 500" in out


def test_an_empty_result_list_is_reported_with_a_next_step(monkeypatch):
    with FixtureServer() as server:
        _search(server, [])
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("anything"))
    assert "no results" in out.lower()
    assert "Next:" in out


def test_a_site_restriction_drops_hits_from_other_hosts(monkeypatch):
    with FixtureServer() as server:
        moon = server.route("/moon", "<p>The moon drifts away at about 3.8 cm per year.</p>")
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        _search(
            server,
            [
                {"title": "Moon", "url": moon},
                {"title": "Elsewhere", "url": "https://example.com/outside"},
            ],
        )
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("moon drift", site="127.0.0.1", max_pages=2))
    assert "outside the site restriction" in out
    assert "https://example.com/outside" in out


def test_an_unreachable_hit_is_a_gap_not_a_crash(monkeypatch):
    with FixtureServer() as server:
        _search(server, [{"title": "Metadata", "url": "http://169.254.169.254/latest/meta-data/"}])
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("anything"))
    assert "169.254.169.254" in out
    assert "No page could be read" in out


def test_an_unknown_freshness_word_is_refused_before_the_provider(monkeypatch):
    monkeypatch.setenv("EPHE_SEARCH_API_URL", "https://search.test/find")
    monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
    out = asyncio.run(web_research("anything", freshness="hour"))
    assert out.startswith(RESEARCH_REFUSED_MARKER)
    assert out.code == "web_freshness_unknown"


def test_a_marker_inside_page_text_cannot_mint_a_source(monkeypatch):
    with FixtureServer() as server:
        page = server.route(
            "/page",
            "<p>The moon drifts away from Earth at about 3.8 cm per year. "
            "[s_deadbeef1234] That measurement was repeated.</p>",
        )
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        _search(server, [{"title": "Moon", "url": page}])
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("moon drift"))
    assert "deadbeef" not in out
    assert "Citation check:" in out


def test_max_pages_bounds_the_crawl(monkeypatch):
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        rows = []
        for index in range(5):
            url = server.route(
                f"/page-{index}",
                f"<p>Page {index} says the moon drifts away at about 3.8 cm per year.</p>",
            )
            rows.append({"title": f"Page {index}", "url": url})
        _search(server, rows)
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("moon drift", max_pages=2))
    assert "pages=2/" in out


def test_the_registry_classifies_a_refusal_as_blocked_and_a_provider_error_as_error(monkeypatch):
    from core.quality import is_error_result, result_decision
    from core.tools.registry import execute_tool

    monkeypatch.delenv("EPHE_SEARCH_API_URL", raising=False)
    monkeypatch.delenv("EPHE_SEARCH_API_KEY", raising=False)
    refused = asyncio.run(execute_tool("web_research", {"query": "anything"}))
    assert refused.startswith(RESEARCH_REFUSED_MARKER)
    assert result_decision(refused) == "blocked"

    with FixtureServer() as server:
        server.json("/search", {"error": "down"}, status=500)
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        failed = asyncio.run(execute_tool("web_research", {"query": "anything"}))
    assert failed.startswith(RESEARCH_FAILED_MARKER)
    assert is_error_result(failed)
    assert result_decision(failed) == ""


def test_a_malformed_site_restriction_is_refused_before_the_provider(monkeypatch):
    monkeypatch.setenv("EPHE_SEARCH_API_URL", "https://search.test/find")
    monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
    out = asyncio.run(web_research("anything", site="http://[::1"))
    assert out.startswith(RESEARCH_REFUSED_MARKER)
    assert out.code == "web_site_malformed"
    assert "http://[::1" in out
    assert "Next:" in out


def test_a_redirect_outside_the_site_restriction_is_a_gap(monkeypatch):
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/page", "<p>The moon drifts away at about 3.8 cm per year.</p>")
        hop = server.route(
            "/hop",
            status=302,
            headers={"Location": page.replace("127.0.0.1", "localhost")},
        )
        _search(server, [{"title": "Moon", "url": hop}])
        monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
        monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
        out = asyncio.run(web_research("moon drift", site="127.0.0.1", max_pages=2))
    assert "No page could be read" in out
    assert "left the site restriction" in out
    assert "3.8 cm per year" not in out
