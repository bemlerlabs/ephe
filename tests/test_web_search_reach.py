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


def test_oeffentliche_Treffer_sind_erreichbar_und_beklagen_sich_nicht():
    for url in (
        "https://example.com/artikel",
        "http://93.184.216.34/x",
        "https://docs.python.org/3/library/socket.html",
    ):
        reachable, reason = reach_by_name(url)
        assert reachable is True, url
        assert reason == "", url


def test_Schema_ausserhalb_des_Kanals_ist_erreicht_oder_nicht():
    reachable, reason = reach_by_name("file:///etc/passwd")
    assert reachable is False
    assert "Datei" in reason or "file" in reason


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
def test_interne_Ziele_sind_als_Treffer_nichts_wert(url):
    reachable, reason = reach_by_name(url)
    assert reachable is False
    assert reason


def test_interne_Namensraeume_erkennt_man_am_Namen_ohne_Aufloesung(monkeypatch):
    def explosion(*_a, **_kw):
        raise AssertionError("reach_by_name loest nicht auf")

    monkeypatch.setattr(socket, "getaddrinfo", explosion)
    for host in ("api.internal", "db.svc", "printer.local", "app.svc.cluster.local"):
        assert reach_by_name(f"http://{host}/x")[0] is False, host
    # and a public name stays allowed, even though it was never resolved
    assert reach_by_name("https://example.com/x") == (True, "")


def test_Endungs_Tabelle_gilt_fuer_jede_Zeile():
    assert INTERNAL_NAME_SUFFIXES, "ohne Endungen ist die Namensmauer eine Vermutung"
    for suffix in INTERNAL_NAME_SUFFIXES:
        assert suffix.startswith("."), suffix


def test_die_private_Option_gilt_auch_hier_aber_nicht_fuer_Metadaten():
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
        raise AssertionError("web_search sucht im Test, es wird nicht aufgelöst")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    with patch.object(web_search_module, "DDGS", return_value=_fake_ddgs(results)):
        return asyncio.run(web_search("ephe"))


def test_interner_Treffer_sagt_es_der_Zeile_statt_dem_Modell_zu_entscheiden(monkeypatch):
    out = _search_with(
        [
            {"title": "Metadaten", "href": "http://169.254.169.254/latest/meta-data/", "body": "b"},
            {"title": "Local", "href": "http://localhost:8765/api/file?path=.ssh/id_rsa", "body": "c"},
        ],
        monkeypatch,
    )
    assert out.count("Reach:") == 2
    assert "fetch_url does not open this target" in out


def test_oeffentlicher_Treffer_bekommt_keine_Warnung_aufgeklebt(monkeypatch):
    out = _search_with(
        [{"title": "Doku", "href": "https://docs.python.org/3/library/socket.html", "body": "b"}],
        monkeypatch,
    )
    assert "Reach:" not in out
    assert "Source quality: official" in out


def test_die_Reichweite_Zeile_aendert_nichts_an_der_Reihenfolge(monkeypatch):
    out = _search_with(
        [
            {"title": "Blog", "href": "https://irgendwo.example/x", "body": "b"},
            {"title": "Doku", "href": "https://python.org/a", "body": "c"},
            {"title": "Köder", "href": "http://169.254.169.254/latest/meta-data/", "body": "d"},
        ],
        monkeypatch,
    )
    assert out.index("Doku") < out.index("Blog") < out.index("Köder")
    assert out.count("Reach:") == 1


def test_gesunder_Treffer_beruehrt_weder_Netz_noch_Namen(monkeypatch):
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
