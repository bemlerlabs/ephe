"""W1-b — reading view (server/routes/reader.py).

The contract the surface needs:

1. Only http(s) gets through; anything else is a line of reason, not an error.
2. The title comes from <title>, else og:title, else the host.
3. The text is the reading version: an <article>/<main> node wins, the
   page frame (nav, footer) drops out.
4. If the reach guard cannot fetch the target, the answer says why — the
   route has no network window of its own.
5. A response >= 400 is not text but a reason.
6. The truncation of the reduced text becomes a flag, not leftover text in the body.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools import fetch_tools  # noqa: E402
from server.main import create_app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(create_app())


ARTIKEL = (
    "<html><head><title>Ephe Handbuch — Kapitel 3</title>"
    '<meta property="og:title" content="Kapitel 3">'
    "<script>var unsichtbar = 1;</script></head>"
    "<body><nav>Navigationsmüll</nav>"
    "<article><h1>Kapitel 3</h1><p>Der Cell-Rahmen hält die Sitzung "
    "zusammen, weil er sie abschließen kann.</p>"
    "<ul><li>erstens</li><li>zweitens</li></ul></article>"
    "<footer>Fußzeilenmüll</footer></body></html>"
)


def test_nur_http_kommt_durch(client):
    for bad in ("", "datei:/etc/passwd", "javascript:alert(1)", "localhost:8765"):
        antwort = client.get("/api/reader", params={"url": bad}).json()
        assert antwort["ok"] is False
        assert antwort["text"] == ""
        assert "http" in antwort["reason"]


def test_titel_und_lesefassung(client, monkeypatch):
    async def fake_get(url):
        return 200, ARTIKEL

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://example.org/a"}).json()

    assert data["ok"] is True
    assert data["title"] == "Ephe Handbuch — Kapitel 3"
    assert "Cell-Rahmen" in data["text"]
    assert "- erstens" in data["text"]
    assert "var unsichtbar" not in data["text"]
    assert "Navigationsmüll" not in data["text"]
    assert "Fußzeilenmüll" not in data["text"]
    assert data["target"] == "https://example.org/a"
    assert data["chars"] == len(data["text"])


def test_ohne_article_gewinnt_der_rest(client, monkeypatch):
    html = "<html><head><title>Nur Text</title></head><body><p>Ein Absatz ohne Rahmen.</p></body></html>"

    async def fake_get(url):
        return 200, html

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://example.org"}).json()

    assert data["ok"] is True
    assert "Ein Absatz ohne Rahmen." in data["text"]


def test_og_title_ohne_title_tag(client, monkeypatch):
    html = '<html><head><meta property="og:title" content="Aus Open Graph"></head><body><p>Text</p></body></html>'

    async def fake_get(url):
        return 200, html

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://example.org"}).json()
    assert data["title"] == "Aus Open Graph"


def test_kein_title_kein_og_nimmt_den_host(client, monkeypatch):
    async def fake_get(url):
        return 200, "<html><body><p>Text ohne Kopf</p></body></html>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://sub.example.org/x"}).json()
    assert data["title"] == "sub.example.org"


def test_verweigertes_ziel_nennt_den_grund(client, monkeypatch):
    async def refused(url):
        raise fetch_tools.FetchRefused("[verweigert] loopback ist nicht erlaubt")

    monkeypatch.setattr(fetch_tools, "_http_get", refused)
    data = client.get("/api/reader", params={"url": "http://127.0.0.1:1/"}).json()

    assert data["ok"] is False
    assert "loopback" in data["reason"]
    assert data["chars"] == 0


def test_zeitfehler_ist_ein_grund_und_kein_absturz(client, monkeypatch):
    async def boom(url):
        raise TimeoutError("zu langsam")

    monkeypatch.setattr(fetch_tools, "_http_get", boom)
    data = client.get("/api/reader", params={"url": "https://example.org"}).json()

    assert data["ok"] is False
    # The class name and the message stay in the log; the pane gets a fixed sentence.
    assert data["reason"] == "The page could not be read."
    assert "TimeoutError" not in data["reason"]


def test_fuenfhundert_ist_kein_text(client, monkeypatch):
    async def fake_get(url):
        return 503, "<html><body>Später</body></html>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://example.org"}).json()

    assert data["ok"] is False
    assert "503" in data["reason"]


def test_kuerzung_wird_flag(client, monkeypatch):
    lang = "<html><body><article><p>" + ("wort " * 4000) + "</p></article></body></html>"

    async def fake_get(url):
        return 200, lang

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://example.org"}).json()

    assert data["truncated"] is True
    assert "truncated at" not in data["text"]
    assert data["chars"] == len(data["text"])


def test_leere_seite_luegt_nicht(client, monkeypatch):
    async def fake_get(url):
        return 200, "<html><body>   </body></html>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    data = client.get("/api/reader", params={"url": "https://example.org"}).json()

    assert data["ok"] is False
    assert data["reason"]
