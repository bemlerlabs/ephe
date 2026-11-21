"""The web intake parts that decide without a network.

Policy bounds, robots parsing, the rate limiter's clock, the evidence ids, the
citation check and the provider's response mapping. The crawl and the tool have
their own files against a loopback fixture.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import core.web_intake.search as search_module
from core.web_intake import policy
from core.web_intake.crawl import extract_links, html_to_text, page_title
from core.web_intake.evidence import EvidenceStore
from core.web_intake.search import SearchConfig, hits_from_payload, search
from core.web_intake.verify import verify_claims


def test_limits_are_clamped_not_trusted():
    assert policy.normalize_limits(99, 5) == (policy.MAX_PAGES, policy.MAX_DEPTH)
    assert policy.normalize_limits(0, 0) == (1, 1)
    assert policy.normalize_limits("3", "2") == (3, 2)
    assert policy.normalize_limits(None, None) == (policy.DEFAULT_PAGES, policy.DEFAULT_DEPTH)


def test_freshness_words_become_windows_and_nonsense_is_refused():
    assert policy.normalize_freshness("any") == ""
    assert policy.normalize_freshness("WEEK") == "week"
    assert policy.cache_window_seconds("day") == 86_400
    with pytest.raises(ValueError):
        policy.normalize_freshness("hour")


def test_content_type_whitelist_reads_the_media_type_before_the_parameters():
    assert policy.content_type_allowed("text/html; charset=utf-8")
    assert policy.content_type_allowed("TEXT/PLAIN")
    assert not policy.content_type_allowed("application/pdf")
    assert not policy.content_type_allowed("")


def test_site_scope_names_a_host_and_keeps_its_subdomains():
    assert policy.site_host("https://docs.python.org/3/library/") == "docs.python.org"
    assert policy.site_host("docs.python.org") == "docs.python.org"
    assert policy.in_site("https://docs.python.org/3/", "python.org")
    assert policy.in_site("https://python.org/", "python.org")
    assert not policy.in_site("https://example.com/", "python.org")


def test_robots_rules_allow_refuse_and_state_a_delay():
    allow = policy.RobotsRules.from_text("User-agent: *\nAllow: /\n")
    assert allow.allows("https://example.com/a") == (True, "")
    deny = policy.RobotsRules.from_text("User-agent: *\nDisallow: /private\n")
    assert deny.allows("https://example.com/private/x")[0] is False
    slow = policy.RobotsRules.from_text("User-agent: *\nCrawl-delay: 3\n")
    assert slow.crawl_delay == 3.0
    capped = policy.RobotsRules.from_text("User-agent: *\nCrawl-delay: 99\n")
    assert capped.crawl_delay == policy.MAX_CRAWL_DELAY_SECONDS
    blocked = policy.RobotsRules.blocked("robots.txt answered HTTP 503")
    assert blocked.allows("https://example.com/a")[0] is False


def test_rate_limiter_waits_the_remaining_delay_on_an_injected_clock():
    now = [0.0]
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = policy.RateLimiter(clock=lambda: now[0], sleep=fake_sleep)

    async def run() -> None:
        await limiter.wait("host")
        now[0] += 0.25
        await limiter.wait("host", 2.0)
        await limiter.wait("other-host")

    asyncio.run(run())
    assert slept == [1.75]


def test_evidence_ids_are_stable_per_text_and_change_with_it():
    store = EvidenceStore()
    first = store.add(
        url="https://example.com/a#part",
        title="A",
        fetched_at="2026-11-11T22:00:00Z",
        content_type="text/html",
        extract="the moon drifts away",
    )
    assert first.url == "https://example.com/a"
    again = store.add(
        url="https://example.com/a",
        title="A",
        fetched_at="2026-11-11T23:00:00Z",
        content_type="text/html",
        extract="the moon drifts away",
    )
    assert again.source_id == first.source_id
    assert len(store) == 1
    changed = store.add(
        url="https://example.com/a",
        title="A",
        fetched_at="2026-11-11T23:30:00Z",
        content_type="text/html",
        extract="the moon drifts away faster",
    )
    assert changed.source_id != first.source_id
    assert len(store) == 1
    assert store.get(first.source_id) is not None


def _store_with(text: str) -> tuple[EvidenceStore, str]:
    store = EvidenceStore()
    source = store.add(
        url="https://example.com/moon",
        title="Moon",
        fetched_at="2026-11-11T22:00:00Z",
        content_type="text/html",
        extract=text,
    )
    return store, source.source_id


def test_a_verbatim_sentence_passes_the_citation_check():
    store, source_id = _store_with("The moon drifts away at about 3.8 cm per year.")
    report = verify_claims([f"The moon drifts away at about 3.8 cm per year. [{source_id}]"], store)
    assert report.checked == 1
    assert report.verified == 1
    assert report.ok


def test_a_quoted_anchor_is_checked_inside_the_named_source():
    store, source_id = _store_with("The measurement is 3.8 cm per year and it is old.")
    good = verify_claims([f'The result reads "3.8 cm per year" [{source_id}]'], store)
    assert good.verified == 1
    bad = verify_claims([f'The result reads "4.1 cm per year" [{source_id}]'], store)
    assert bad.verified == 0
    assert bad.rejected
    assert "anchor not in" in bad.issues[0]


def test_missing_and_unknown_sources_are_reported_not_dropped():
    store, _source_id = _store_with("some source text")
    uncited = verify_claims(["A claim with no source."], store)
    assert uncited.verified == 0
    assert "no source named" in uncited.issues[0]
    unknown = verify_claims(["A claim [s_000000000000]"], store)
    assert unknown.rejected
    assert "unknown source id" in unknown.issues[0]


def test_html_reduction_keeps_structure_and_drops_scripts():
    text = html_to_text(
        "<h2>Plan</h2><ul><li>One</li></ul><script>bad()</script><p>Body</p>"
    )
    assert "## Plan" in text
    assert "- One" in text
    assert "bad()" not in text
    assert html_to_text("x" * 50, cap=10).endswith("[... truncated at 10 chars]")


def test_title_and_links_are_read_relative_to_the_page():
    html = (
        "<title> Field &amp; Notes </title>"
        '<a href="/b#part">B</a><a href="mailto:x@example.com">M</a>'
        '<a href="https://other.test/c">C</a>'
    )
    assert page_title(html) == "Field &amp; Notes"
    links = extract_links(html, "https://example.com/a")
    assert links == ("https://example.com/b", "https://other.test/c")


def test_provider_rows_accept_the_documented_shape_and_the_usual_aliases():
    documented = {"results": [{"url": "https://a.test/1", "title": "A", "snippet": "s"}]}
    alias = {"web": {"results": [{"link": "https://b.test/2", "name": "B", "description": "d"}]}}
    assert [hit.url for hit in hits_from_payload(documented, 5)] == ["https://a.test/1"]
    assert [hit.title for hit in hits_from_payload(alias, 5)] == ["B"]
    assert hits_from_payload({"unexpected": []}, 5) == []
    rows = [{"url": f"https://a.test/{index}"} for index in range(3)]
    assert len(hits_from_payload({"results": rows}, 2)) == 2


def test_provider_config_reads_a_file_and_lets_the_environment_win(monkeypatch, tmp_path):
    config_file = tmp_path / "web-search.json"
    config_file.write_text(
        json.dumps({"url": "https://file.test/search", "key": "file-key", "provider": "file"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("EPHE_SEARCH_CONFIG", str(config_file))
    for name in (
        "EPHE_SEARCH_API_URL",
        "EPHE_SEARCH_API_KEY",
        "EPHE_SEARCH_PROVIDER",
        "EPHE_SEARCH_KEY_HEADER",
        "EPHE_SEARCH_KEY_PREFIX",
        "EPHE_SEARCH_QUERY_PARAM",
        "EPHE_SEARCH_COUNT_PARAM",
        "EPHE_SEARCH_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)
    stored = SearchConfig.from_environment()
    assert stored.url == "https://file.test/search"
    assert stored.headers() == {"Authorization": "Bearer file-key"}
    monkeypatch.setenv("EPHE_SEARCH_API_URL", "https://env.test/search")
    monkeypatch.setenv("EPHE_SEARCH_API_KEY", "env-key")
    live = SearchConfig.from_environment()
    assert live.url == "https://env.test/search"
    assert live.key == "env-key"


def test_search_sends_the_key_in_a_header_and_never_in_the_url(monkeypatch):
    captured: dict = {}

    async def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")

        class Response:
            status = 200
            text = '{"results": [{"url": "https://a.test/1", "title": "A"}]}'
            note = ""

        return Response()

    monkeypatch.setattr(search_module, "guarded_get", fake_get)
    config = SearchConfig(url="https://search.test/find", key="secret-key")
    hits = asyncio.run(search(config, "moon drift", limit=3, freshness="week"))
    assert [hit.url for hit in hits] == ["https://a.test/1"]
    assert "secret-key" not in captured["url"]
    assert "q=moon+drift" in captured["url"]
    assert "freshness=week" in captured["url"]
    assert captured["headers"] == {"Authorization": "Bearer secret-key"}


def test_a_malformed_href_is_skipped_and_the_rest_kept():
    links = extract_links(
        '<a href="http://[::1">bad</a><a href="/ok">ok</a>',
        "https://example.com/base",
    )
    assert links == ("https://example.com/ok",)


def test_a_malformed_url_is_outside_the_site_and_never_raises():
    # `in_site` reads provider-supplied links, so a bad string is outside the site.
    assert policy.in_site("http://[::1", "example.com") is False
    assert policy.in_site("https://example.com:99999/", "example.com") is False
