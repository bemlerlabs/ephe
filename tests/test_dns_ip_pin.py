"""I1-7 (b): the DNS TOCTOU gap of the fetch channel is closed, not explained.

Before: ``check_url`` resolved the hostname and checked the address — and httpx
then connected once more against the same name. Whoever controls the nameservers
moves the record between check and connection: what gets checked is a public
address, what gets connected is 127.0.0.1 (Ephe's own file reader) or
169.254.169.254.

The fix is pinning: the request goes to the address that was checked, and for TLS
the original name remains the certificate subject (``sni_hostname``). So the
certificate still validates against the hostname, while the connection goes where
the check looked.

Proved against real httpx (``MockTransport``), not a hand-built double —
otherwise the old call API would once again be the evidence.
"""
from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from core.net_guard import guarded_fetch, pinned_request


# 1. The pin helper is a pure function


def test_https_pin_setzt_die_Adresse_in_die_URL_und_den_Namen_in_den_Zuename():
    url, sni, host_header = pinned_request(
        "https://example.com/artikel?x=1#k", ("93.184.216.34",)
    )
    assert url == "https://93.184.216.34/artikel?x=1#k"
    assert sni == "example.com"
    assert host_header == "example.com"


def test_default_Port_falls_t_aus_der_Pin_URL_aber_nicht_aus_dem_Host_Kopf():
    plain, _, host_header = pinned_request("https://example.com/x", ("93.184.216.34",))
    assert ":443" not in plain
    assert host_header == "example.com"
    exotic, _, host_with_port = pinned_request("https://example.com:8443/x", ("93.184.216.34",))
    assert exotic == "https://93.184.216.34:8443/x"
    assert host_with_port == "example.com:8443"


def test_http_Pin_nutzt_Port_80_und_kennt_kein_TLS_Zertifikats_Zuename():
    url, sni, host_header = pinned_request("http://example.com/y", ("93.184.216.34",))
    assert url == "http://93.184.216.34/y"
    assert sni == ""
    assert host_header == "example.com"


def test_Klammern_um_die_IPv6_Adresse_weil_ein_Doppelpunkt_ohne_Syntax_waere():
    url, _sni, host_header = pinned_request("https://example.com/z", ("2001:db8::1",))
    assert url == "https://[2001:db8::1]/z"
    assert host_header == "example.com"


def test_Basic_Auth_und_Query_bleiben_an_Bord_der_Pin_URL():
    url, _sni, host_header = pinned_request("https://u:p@example.com/s?q=1", ("93.184.216.34",))
    assert url == "https://u:p@93.184.216.34/s?q=1"
    assert host_header == "example.com"


def test_IP_Literal_wird_nicht_umgeschrieben_und_erhaelt_keinen_Zuename():
    url, sni, host_header = pinned_request("http://93.184.216.34:8080/a", ("93.184.216.34",))
    assert url == "http://93.184.216.34:8080/a"
    assert sni == ""
    assert host_header == "93.184.216.34:8080"


def test_Klammern_um_eine_IPv6_Zieladresse_hoert_man_auch_im_Host_Kopf():
    url, sni, host_header = pinned_request("https://[2001:db8::5]:8443/a", ("2001:db8::1",))
    assert url == "https://[2001:db8::1]:8443/a"
    assert sni == ""
    assert host_header == "[2001:db8::5]:8443"


def test_Schema_lose_URL_inferiert_https_wie_die_Pruefung_selbst():
    url, sni, _host = pinned_request("example.com/a", ("93.184.216.34",))
    assert url == "https://93.184.216.34/a"
    assert sni == "example.com"


# 2. The roundtrip goes to the checked address


def _recording_transport(seen: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "url": str(request.url),
                "host": request.headers.get("host", ""),
                "sni": request.extensions.get("sni_hostname", ""),
            }
        )
        return httpx.Response(200, text="<html>ok</html>")

    return httpx.MockTransport(handler)


def test_der_Request_geht_zur_geprueften_Adresse_und_der_Name_bleibt_Host_Kopf():
    monkey_seen: list = []
    status, _text, _note = asyncio.run(
        guarded_fetch(
            "https://example.com/artikel",
            resolver=lambda host: ["93.184.216.34"],
            transport=_recording_transport(monkey_seen),
        )
    )
    assert status == 200
    assert monkey_seen == [
        {
            "url": "https://93.184.216.34/artikel",
            "host": "example.com",
            "sni": "example.com",
        }
    ]


def test_umziehender_Nameserver_kann_die_Verbindung_nicht_mehr_umziehen():
    """The attack itself: first resolution public, second resolution loopback.

    Without a pin the second resolution would be the connection — with a pin only
    the checked address is connected, and the second answer achieves nothing.
    """
    calls: list[str] = []

    def rebinding_resolver(host: str) -> list[str]:
        calls.append(host)
        return ["127.0.0.1"] if len(calls) > 1 else ["93.184.216.34"]

    seen: list = []
    status, _text, _note = asyncio.run(
        guarded_fetch(
            "https://rebind.example/x",
            resolver=rebinding_resolver,
            transport=_recording_transport(seen),
        )
    )
    assert status == 200
    assert seen[0]["url"] == "https://93.184.216.34/x"
    assert "127.0.0.1" not in seen[0]["url"]


def test_Redirect_Hop_wird_geprueft_und_sein_Ziel_gepinnt():
    hop: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        hop.append(str(request.url))
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "https://weiter.example/z"})
        return httpx.Response(200, text="<html>fertig</html>")

    table = {"start.example": ["93.184.216.34"], "weiter.example": ["93.184.216.99"]}
    status, text, _note = asyncio.run(
        guarded_fetch(
            "https://start.example/a",
            resolver=lambda host: table[host],
            transport=httpx.MockTransport(handler),
        )
    )
    assert (status, text) == (200, "<html>fertig</html>")
    assert hop == ["https://93.184.216.34/a", "https://93.184.216.99/z"]


def test_Redirect_auf_loopback_bleibt_auch_mit_Pin_ausgesperrt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8765/api/file?path=.ssh/id_rsa"})

    status, text, note = asyncio.run(
        guarded_fetch(
            "https://start.example/a",
            resolver=lambda host: ["93.184.216.34"],
            transport=httpx.MockTransport(handler),
        )
    )
    assert status == 0
    assert "loopback" in text.lower()
    assert note


# 3. The check itself stays as strict as it always was


def test_mehrere_A_Eintraege_blockiert_einer_gilt_die_Pruefung_fuer_alle():
    """Pinning is no all-clear: one address in the metadata range is enough."""
    from core.net_guard import check_url

    allowed, reason = check_url(
        "https://multi.example/x",
        resolver=lambda host: ["93.184.216.34", "169.254.169.254"],
    )
    assert allowed is False
    assert "metadata" in reason


def test_der_Guard_ruft_keinen_echten_Nameserver(monkeypatch):
    def explosion(*_a, **_kw):
        raise AssertionError("der Guard loest im Test nicht selbst auf")

    monkeypatch.setattr(socket, "getaddrinfo", explosion)
    seen: list = []
    status, _text, _note = asyncio.run(
        guarded_fetch(
            "https://example.com/x",
            resolver=lambda host: ["93.184.216.34"],
            transport=_recording_transport(seen),
        )
    )
    assert status == 200
    assert seen[0]["url"] == "https://93.184.216.34/x"


@pytest.mark.parametrize(
    "name",
    ["localhost", "api.internal", "db.svc.cluster.local", "printer.local"],
)
def test_interne_Namensraeume_sind_auch_ohne_Aufloesung_ausserhalb_der_Reichweite(name):
    from core.net_guard import reach_by_name

    reachable, reason = reach_by_name(f"http://{name}:8765/api/file?path=.ssh/id_rsa")
    assert reachable is False
    assert reason
