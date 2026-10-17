"""G4: fetch_url is the only network tool that receives a URL directly from the
model — and it followed redirects blind. A prompt "fetch_url('http://169.254.
169.254/latest/meta-data/')" was therefore an AWS metadata reader, and a redirect
onto localhost made the very same roundtrip through one's own machine.

The rule tested here is the same as for the headless browser (wave G2):
bound the cluster by its reach, not by a guess.

Two separate checks:
- First the target address (scheme + resolved IPs), and THAT ON EVERY HOP — a
  302 onto loopback is exactly the attack.
- Then the quantity: an unlimited download is a memory-DoS in a process that runs
  on the user's machine.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket

import pytest

from core.net_guard import (
    MAX_DOWNLOAD_BYTES,
    address_is_public,
    check_url,
    guarded_fetch,
)
from core.tool_markers import FETCH_REFUSED_MARKER


def _resolver(table: dict[str, list[str]]):
    """Fake DNS: check_url should make no real lookups."""

    def resolve(host: str) -> list[str]:
        if host in table:
            return table[host]
        raise socket.gaierror(f"no such host {host}")

    return resolve


class _FakeResponse:
    """httpx streaming response: context manager with status_code/headers/aiter_bytes."""

    def __init__(
        self,
        status: int = 200,
        headers: dict | None = None,
        chunks: list[bytes] | None = None,
    ):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or [b"<html>ok</html>"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aclose(self):
        return None

    def aiter_bytes(self, chunk_size: int = 64 * 1024):
        chunks = self._chunks

        async def gen():
            for c in chunks:
                yield c

        return gen()


class _FakeRequest:
    """httpx.Request in miniature: url, headers, extensions — the guard needs nothing more."""

    def __init__(self, url: str, headers: dict | None = None):
        self.url = url
        # httpx headers are case-insensitive; the double mirrors that.
        self.headers = {str(k).lower(): v for k, v in (headers or {}).items()}
        self.extensions: dict = {}


class _FakeClient:
    """Scripts the redirect sequence: every station is recorded.

    The double follows the httpx call the guard really makes today, which is
    ``build_request`` + ``send`` since the IP pinning; the pre-pinning code used
    ``stream``. Otherwise the test would stay blind to the one line that closes
    the TOCTOU gap: that the connection goes to the resolved address.
    """

    script: list[_FakeResponse] = []
    seen: list[str] = []
    hosts: list[str] = []
    sni: list[str] = []

    def __init__(self, *a, **kw):
        self.args = kw

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def build_request(self, method: str, url: str, headers=None, **kw):
        assert method == "GET", f"der Guard soll nur lesen, nicht {method}"
        return _FakeRequest(url, dict(headers or {}))

    async def send(self, request, **kw):
        type(self).seen.append(str(request.url))
        type(self).hosts.append(str(request.headers.get("host", "")))
        type(self).sni.append(str(request.extensions.get("sni_hostname", "")))
        if not type(self).script:
            return _FakeResponse(200, chunks=[b"<html>done</html>"])
        return type(self).script.pop(0)


def _fake_dns(host: str, port: object = 0, *_a, **_kw):
    """The guard resolves via socket.getaddrinfo, so the stub sits on that call and
    reaches the guard through it. Anything unknown counts as public."""
    table = {
        "localhost": "127.0.0.1",
        "intranet.local": "10.1.2.3",
        "box": "192.168.17.5",
    }
    ip = table.get(host, "93.184.216.34")
    try:
        number = int(port) if port not in (None, "") else 0
    except (TypeError, ValueError):
        number = 0
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, number))]


@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeClient.script = []
    _FakeClient.seen = []
    _FakeClient.hosts = []
    _FakeClient.sni = []
    # The reach is opt-in via the environment — the test has to run deterministically
    # in the default (public), otherwise an exported value decides.
    monkeypatch.delenv("EPHE_FETCH_ALLOW_PRIVATE", raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns)
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    return _FakeClient


# 1. Reach: what may an address be at all


def test_cloud_metadata_ist_im_mer_gesperrt_auch_mit_private_opt_in():
    ok, why = check_url(
        "http://169.254.169.254/latest/meta-data/iam/",
        allow_private=True,
        resolver=_resolver({}),
    )
    assert not ok
    assert "169.254" in why or "Metadaten" in why


def test_link_local_und_unspecified_sind_immer_gesperrt():
    for url in (
        "http://169.254.169.254/",
        "http://0.0.0.0/",
        "http://[::]/",
        "http://metadata.google.internal/",
    ):
        ok, why = check_url(url, allow_private=True, resolver=_resolver({}))
        assert not ok, url


def test_loopback_und_private_netze_sind_opt_in():
    table = {
        "localhost": ["127.0.0.1", "::1"],
        "intranet.local": ["10.1.2.3"],
        "box": ["192.168.17.5"],
    }
    for url in ("http://localhost:8000/x", "http://intranet.local/", "http://box/"):
        ok, _why = check_url(url, resolver=_resolver(table))
        assert not ok, url
        ok, why = check_url(url, allow_private=True, resolver=_resolver(table))
        assert ok, f"{url}: {why}"


def test_oeffentliche_adresse_geht_und_liefert_die_aufgeloeste_notiz():
    ok, why = check_url("https://example.com/docs", resolver=_resolver({"example.com": ["93.184.216.34"]}))
    assert ok, why


def test_Schema_fremder_Protokolle_werden_abgelehnt():
    for url in ("file:///etc/passwd", "data:text/html,hi", "gopher://x/1", "ftp://x/y"):
        ok, why = check_url(url, resolver=_resolver({}))
        assert not ok, url
        assert "Schema" in why or "http" in why


def test_unaufloesbarer_host_ist_ein_fehler_kein_freifahrtschein():
    ok, why = check_url("http://nicht-vorhanden.invalid/", resolver=_resolver({}))
    assert not ok
    assert why.code == "not_resolvable"
    assert why.params == {"host": "nicht-vorhanden.invalid"}


def test_address_is_public_kennt_beide_adressfamilien():
    assert address_is_public("93.184.216.34") is None
    assert address_is_public("2001:4860:4860::8888") is None
    assert address_is_public("10.0.0.5") is not None
    assert address_is_public("fe80::1") is not None
    assert address_is_public("fc00::1") is not None
    assert ipaddress.ip_address  # import neighbour: the module should import cleanly


# 2. Every redirect hop is checked again


def test_redirect_auf_loopback_wird_nicht_benutzt(fake_httpx):
    fake_httpx.script = [
        _FakeResponse(302, {"location": "http://127.0.0.1:8765/api/file?path=.ssh/id_rsa"})
    ]
    status, text, note = asyncio.run(
        guarded_fetch("https://example.com/redirect-me", resolver=_resolver({"example.com": ["93.184.216.34"]}))
    )
    assert status == 0
    assert "abgelehnt" in text or "Gesperrt" in text.lower() or "loopback" in text.lower()
    # The hop was NEVER requested — otherwise the file would already have been read.
    # Requested was the resolved address (the pin); the Host header stays the name.
    assert fake_httpx.seen == ["https://93.184.216.34/redirect-me"]
    assert fake_httpx.hosts == ["example.com"]
    assert fake_httpx.sni == ["example.com"]
    assert note  # the refusal has to say why it refused


def test_redirect_kette_ueberschreitet_nicht_das_Hop_Budget(fake_httpx):
    fake_httpx.script = [_FakeResponse(302, {"location": f"https://example.com/hop{i}"}) for i in range(10)]
    status, text, note = asyncio.run(
        guarded_fetch("https://example.com/start", resolver=_resolver({"example.com": ["93.184.216.34"]}))
    )
    assert status == 0
    assert "redirect" in note.lower()
    assert len(fake_httpx.seen) <= 6


# 3. Data volume: a download runs on a budget


def test_download_wird_begrenzt_und_sagt_es_ehrlich(fake_httpx):
    big = [b"x" * (MAX_DOWNLOAD_BYTES + 10_000)]
    fake_httpx.script = [_FakeResponse(200, chunks=big)]
    status, text, note = asyncio.run(
        guarded_fetch("https://example.com/big.bin", resolver=_resolver({"example.com": ["93.184.216.34"]}))
    )
    assert status == 200
    assert len(text) <= MAX_DOWNLOAD_BYTES
    assert "capped" in note or "abgebrochen" in note


def test_koerper_ohne_cap_Angabe_nutzt_das_default(fake_httpx):
    fake_httpx.script = [_FakeResponse(200, chunks=[b"hallo"])]
    status, text, note = asyncio.run(
        guarded_fetch("https://example.com/ok", resolver=_resolver({"example.com": ["93.184.216.34"]}))
    )
    assert (status, text) == (200, "hallo")
    assert note == ""


# 4. fetch_url reaches the network through the guard


def test_fetch_url_reicht_metadaten_Ziel_ab_ohne_das_netz_zu_beruehren(fake_httpx):
    from core.tools import fetch_tools

    fetch_tools._FETCH_CACHE.clear()
    out = asyncio.run(fetch_tools.fetch_url("http://169.254.169.254/latest/meta-data/"))
    assert out.startswith(FETCH_REFUSED_MARKER) or "Fetch failed" in out, out
    # This is the actual proof: not a single roundtrip was made.
    assert fake_httpx.seen == []
    assert "169.254" in out or "Metadaten" in out


def test_fetch_url_holt_eine_oeffentliche_seite_durch_den_guard(fake_httpx):
    from core.tools import fetch_tools

    fetch_tools._FETCH_CACHE.clear()
    fake_httpx.script = [_FakeResponse(200, chunks=[b"<h1>Titel</h1><p>Text</p>"])]
    out = asyncio.run(fetch_tools.fetch_url("https://example.com/artikel"))
    assert "Titel" in out
    assert fake_httpx.seen == ["https://93.184.216.34/artikel"]
    assert fake_httpx.hosts == ["example.com"]
    assert fake_httpx.sni == ["example.com"]
