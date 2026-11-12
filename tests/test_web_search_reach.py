"""I1-7 (a): search results know the reach too — until now only fetch_url did.

``web_search`` hands the model URLs that it then opens with ``fetch_url``. The
wall stood at fetch_url, not at the list: a poisoned or simply internal index
could return `http://169.254.169.254/...`, `http://localhost:8765/...`
or `http://db.internal/...` as a hit. The model then ran into a blockade and
took it for a bug in the tool.

The check here is deliberately **name-based** (no resolver, no connection):
a result list must not be turned into a list of requests, and offline has to
produce the same answer as online.
"""
from __future__ import annotations

import asyncio
import socket
from unittest.mock import MagicMock, patch

import pytest

from core.net_guard import INTERNAL_NAME_SUFFIXES, reach_by_name
from core.tools.web_search import web_search
from tests.web_search_seam import web_search_module


# 1. reach_by_name: the reach from the name alone


def test_public_targets_are_reachable_and_do_not_complain():
    for url in (
        "https://example.com/article",
        "http://93.184.216.34/x",
        "https://docs.python.org/3/library/socket.html",
    ):
        reachable, reason = reach_by_name(url)
        assert reachable is True, url
        assert reason == "", url


def test_a_scheme_outside_the_channel_is_reachable_or_not():
    reachable, reason = reach_by_name("file:///etc/passwd")
    assert reachable is False
    assert "file" in reason


@pytest.mark.parametrize("url", ["http://[::1", "https://example.com:99999/"])
def test_a_malformed_hit_is_a_refusal_not_a_crash(url):
    # The result list is provider-controlled: one bad row must not turn the whole
    # search call into a ValueError.
    reachable, reason = reach_by_name(url)
    assert reachable is False
    assert reason.code == "url_malformed"
    assert reason.params == {"url": url}


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[fd00:ec2::254]/x",
        "http://metadata.google.internal/x",
        "http://localhost:8765/api/file?path=.ssh/id_rsa",
        "http://127.0.0.1/x",
        "http://10.1.2.3/x",
        "http://192.168.17.5/x",
        "http://[fe80::1]/x",
    ],
)
def test_internal_targets_are_worthless_as_a_hit(url):
    reachable, reason = reach_by_name(url)
    assert reachable is False
    assert reason


def test_internal_name_spaces_are_known_by_name_without_resolving(monkeypatch):
    def explosion(*_a, **_kw):
        raise AssertionError("reach_by_name does not resolve")

    monkeypatch.setattr(socket, "getaddrinfo", explosion)
    for host in ("api.internal", "db.svc", "printer.local", "app.svc.cluster.local"):
        assert reach_by_name(f"http://{host}/x")[0] is False, host
    # and a public name stays allowed, even though it was never resolved
    assert reach_by_name("https://example.com/x") == (True, "")


def test_the_suffix_table_holds_for_every_line():
    assert INTERNAL_NAME_SUFFIXES, "without the suffixes the name wall is a guess"
    for suffix in INTERNAL_NAME_SUFFIXES:
        assert suffix.startswith("."), suffix


def test_the_private_option_applies_here_but_never_to_metadata():
    assert reach_by_name("http://10.1.2.3/x")[0] is False
    assert reach_by_name("http://10.1.2.3/x", allow_private=True)[0] is True
    # but never the metadata network, even with the option set
    assert reach_by_name("http://169.254.169.254/x", allow_private=True)[0] is False


# 2. web_search attaches the reach to the line it concerns


def _fake_ddgs(results: list[dict]):
    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_instance.text.return_value = results
    return mock_instance


def _search_with(results: list[dict], monkeypatch) -> str:
    def _boom(*_a, **_kw):
        raise AssertionError("web_search resolves nothing in a test")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    with patch.object(web_search_module, "DDGS", return_value=_fake_ddgs(results)):
        return asyncio.run(web_search("ephe"))


def test_an_internal_hit_says_it_on_the_line_instead_of_the_model(monkeypatch):
    out = _search_with(
        [
            {"title": "Metadata", "href": "http://169.254.169.254/latest/meta-data/", "body": "b"},
            {"title": "Local", "href": "http://localhost:8765/api/file?path=.ssh/id_rsa", "body": "c"},
        ],
        monkeypatch,
    )
    assert out.count("Reach:") == 2
    assert "fetch_url does not open this target" in out


def test_a_public_hit_gets_no_warning_stuck_on_it(monkeypatch):
    out = _search_with(
        [{"title": "Docs", "href": "https://docs.python.org/3/library/socket.html", "body": "b"}],
        monkeypatch,
    )
    assert "Reach:" not in out
    assert "Source quality: official" in out


def test_the_reach_line_changes_nothing_about_the_order(monkeypatch):
    out = _search_with(
        [
            {"title": "Blog", "href": "https://somewhere.example/x", "body": "b"},
            {"title": "Docs", "href": "https://python.org/a", "body": "c"},
            {"title": "Bait", "href": "http://169.254.169.254/latest/meta-data/", "body": "d"},
        ],
        monkeypatch,
    )
    assert out.index("Docs") < out.index("Blog") < out.index("Bait")
    assert out.count("Reach:") == 1


def test_a_healthy_hit_touches_neither_network_nor_name(monkeypatch):
    seen = []

    def spy(host, *_a, **_kw):
        seen.append(host)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", spy)
    out = _search_with(
        [{"title": "x", "href": "https://example.com/a", "body": "b"}], monkeypatch
    )
    assert "Reach:" not in out
    assert seen == []
