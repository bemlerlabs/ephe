"""The crawl in front of the loopback fixture: robots, ETag, redirects, caps.

No test reaches a real host. The fixture server binds 127.0.0.1 on a kernel
port, and ``EPHE_FETCH_ALLOW_PRIVATE=1`` is what makes that address reachable —
the default refusal is proved in the private-address case.
"""
from __future__ import annotations

import asyncio

import pytest

from core.web_intake import policy
import core.web_intake.crawl as crawl_module
from core.web_intake.crawl import PageCache, clear_robots_cache, crawl
from tests.web_intake_fixture import FixtureServer

ALLOW_ROBOTS = "User-agent: *\nAllow: /\n"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("EPHE_FETCH_ALLOW_PRIVATE", "1")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(crawl_module, "PAGE_CACHE", PageCache(tmp_path / "pages"))
    clear_robots_cache()
    yield
    clear_robots_cache()


def _limiter() -> policy.RateLimiter:
    return policy.RateLimiter(delay=0.0)


def _run(seeds, **kwargs):
    kwargs.setdefault("max_pages", 2)
    kwargs.setdefault("depth", 1)
    kwargs.setdefault("limiter", _limiter())
    return asyncio.run(crawl(list(seeds), **kwargs))


def test_an_allowed_page_is_read_and_reduced_to_text():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route(
            "/page",
            "<title>Drift</title><h1>Drift</h1><p>The moon drifts away at about 3.8 cm per year.</p>",
        )
        run = _run([page])
    assert [entry.url for entry in run.pages] == [page]
    assert "3.8 cm per year" in run.pages[0].text
    assert run.pages[0].title == "Drift"


def test_robots_disallow_keeps_the_page_unrequested():
    with FixtureServer() as server:
        server.route(
            "/robots.txt",
            "User-agent: *\nDisallow: /private\n",
            content_type="text/plain",
        )
        page = server.route("/private/report", "<p>secret</p>")
        run = _run([page])
        requested = server.requests_for("/private/report")
    assert run.pages == []
    assert run.gaps[0].code == "robots_disallowed"
    assert requested == []


def test_robots_that_answers_5xx_keeps_the_crawler_out():
    with FixtureServer() as server:
        server.route("/robots.txt", "down", status=503, content_type="text/plain")
        page = server.route("/page", "<p>text</p>")
        run = _run([page])
        requested = server.requests_for("/page")
    assert run.pages == []
    assert "HTTP 503" in run.gaps[0].reason
    assert requested == []


def test_an_etag_is_revalidated_and_a_304_reuses_the_stored_text():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/page", "<p>cached text</p>", etag='"v1"')
        first = _run([page])
        second = _run([page])
        headers = server.requests_for("/page")
    assert first.pages[0].from_cache is False
    assert second.pages[0].from_cache is True
    assert second.pages[0].text == "cached text"
    assert [entry.get("if-none-match") for entry in headers] == [None, '"v1"']


def test_a_redirect_chain_is_followed_through_the_guard():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        target = server.route("/page", "<p>after two hops</p>")
        server.route("/hop-one", status=302, headers={"Location": "/hop-two"})
        server.route("/hop-two", status=302, headers={"Location": "/page"})
        run = _run([server.url("/hop-one")])
    assert len(run.pages) == 1
    assert run.pages[0].url == target
    assert "after two hops" in run.pages[0].text


def test_a_private_address_is_refused_before_any_request(monkeypatch):
    monkeypatch.delenv("EPHE_FETCH_ALLOW_PRIVATE", raising=False)
    with FixtureServer() as server:
        page = server.route("/page", "<p>text</p>")
        run = _run([page])
        requests = list(server.requests)
    assert run.pages == []
    assert "loopback" in run.gaps[0].reason.lower() or "blocked by default" in run.gaps[0].reason.lower()
    assert requests == []


def test_a_page_above_the_byte_cap_is_a_gap_not_a_truncated_source(monkeypatch):
    monkeypatch.setattr(policy, "MAX_PAGE_BYTES", 1_000)
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/huge", "x" * 1_500)
        run = _run([page])
    assert run.pages == []
    assert run.gaps[0].code == "too_large"


def test_a_content_type_outside_the_whitelist_is_a_gap():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/file", "<p>text</p>", content_type="application/pdf")
        run = _run([page])
    assert run.pages == []
    assert run.gaps[0].code == "content_type"


def test_depth_two_follows_same_host_links_and_stops_at_max_pages():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        server.route("/seed", '<p>seed</p><a href="/child">child</a><a href="https://other.invalid/x">out</a>')
        server.route("/child", "<p>child text</p>")
        seed = server.url("/seed")
        run = _run([seed], max_pages=2, depth=2)
        requests = [path for path, _headers in server.requests]
    assert [entry.url for entry in run.pages] == [server.url("/seed"), server.url("/child")]
    assert "/x" not in requests
    assert requests.count("/seed") == 1


def test_depth_one_reads_the_seed_only():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        server.route("/seed", '<p>seed</p><a href="/child">child</a>')
        server.route("/child", "<p>child text</p>")
        run = _run([server.url("/seed")], max_pages=4, depth=1)
        child = server.requests_for("/child")
    assert [entry.url for entry in run.pages] == [server.url("/seed")]
    assert child == []


def test_a_freshness_window_reuses_a_cached_page_without_a_request():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/page", "<p>cached text</p>", etag='"v1"')
        first = _run([page])
        second = _run([page], freshness="day")
        requests = server.requests_for("/page")
    assert first.pages[0].from_cache is False
    assert second.pages[0].from_cache is True
    assert len(requests) == 1


def test_a_malformed_seed_is_a_gap_not_a_crash():
    run = _run(["http://[::1"])
    assert run.pages == []
    assert run.gaps
    assert run.gaps[0].code == "url_malformed"


def test_a_malformed_href_does_not_cost_the_page_its_other_links():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        seed = server.route(
            "/seed",
            '<p>seed</p><a href="http://[::1">bad</a><a href="/child">child</a>',
        )
        child = server.route("/child", "<p>child text</p>")
        run = _run([seed], max_pages=2, depth=2)
    assert [entry.url for entry in run.pages] == [seed, child]


def test_a_redirect_outside_the_site_restriction_is_a_gap():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/page", "<p>after the redirect</p>")
        server.route(
            "/hop",
            status=302,
            headers={"Location": page.replace("127.0.0.1", "localhost")},
        )
        run = _run([server.url("/hop")], site="127.0.0.1", max_pages=2)
    assert run.pages == []
    assert run.gaps
    assert run.gaps[0].code == "site_scope"
    assert "site restriction" in run.gaps[0].reason


def test_a_redirect_inside_the_site_restriction_is_read():
    with FixtureServer() as server:
        server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
        page = server.route("/page", "<p>after the redirect</p>")
        server.route("/hop", status=302, headers={"Location": page})
        run = _run([server.url("/hop")], site="127.0.0.1", max_pages=2)
    assert [entry.url for entry in run.pages] == [page]
    assert run.gaps == []
