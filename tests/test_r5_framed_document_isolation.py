"""tests/test_r5_framed_document_isolation.py — the isolation belongs on the response.

The starting point was a white rectangle: a PDF card in the workbench never showed
its page. The endpoint was innocent (200, application/pdf, inline, range requests).
Re-measured in real Chrome across three variants of the same frame:

    sandbox="allow-popups"                       -> sad document
    sandbox="allow-popups allow-same-origin"     -> sad document
    (no directive)                               -> the page

The viewer for PDFs is an extension, and an extension works in no sandboxed frame —
handing it back its origin is not enough. So for dead formats the directive stays
away entirely, and the isolation of what can carry scripts (html, svg, xml) is taken
over by the **response**: one rule at one place that every surface inherits which
embeds the file today or tomorrow. The attribute on the frame remains as a second
line for script formats.

Contract:
1. A file frame with a script format is isolated on the response.
2. A dead format (pdf, png) is NOT isolated — otherwise the preview is empty.
3. The app itself (its HTML, its JSON routes) stays untouched; a sandbox on
   index.html would switch the product off.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core import artifact_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    import core.tools.base as base
    import server.routes.files as files

    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setattr(artifact_store, "ARTIFACTS_DB", tmp_path / "artifacts.db")
    # Both file routes have their own ladder to the allowed roots — the check
    # belongs to the surface, not to the test, so branch off both.
    monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
    monkeypatch.setattr(files, "_get_allowed_roots", lambda: [tmp_path])
    from server.main import create_app

    return TestClient(create_app())


def _register(client, tmp_path, name: str, content: bytes, kind: str) -> str:
    path = tmp_path / name
    path.write_bytes(content)
    row = artifact_store.register_artifact(path=str(path), kind=kind, session_id="s1")
    return str(row["id"])


def _csp(response) -> str:
    return response.headers.get("content-security-policy", "")


def test_gegeben_markup_beim_einbetten_ist_die_antwort_dicht(client, tmp_path):
    """An html artefact must inherit the app origin in no frame — the response
    itself says sandbox, regardless of what a surface forgets."""
    art_id = _register(client, tmp_path, "seite.html", b"<script>alert(1)</script>", "html")
    r = client.get(f"/api/artifacts/{art_id}/file")
    assert r.status_code == 200
    assert "sandbox allow-popups" in _csp(r)
    assert "frame-ancestors 'self'" in _csp(r), "die eigene Vorschau darf einbetten"


def test_gegeben_totes_format_bleibt_der_rahmen_frei(client, tmp_path):
    """PDF and image are not isolated: otherwise the browser again shows its white
    rectangle instead of the page."""
    pdf = _register(client, tmp_path, "bericht.pdf", b"%PDF-1.4 fake", "pdf")
    png = _register(client, tmp_path, "bild.png", b"\x89PNG\r\n\x1a\n fake", "png")
    for art_id in (pdf, png):
        r = client.get(f"/api/artifacts/{art_id}/file")
        assert r.status_code == 200
        assert "sandbox" not in _csp(r)


def test_gegeben_datei_route_gilt_dasselbe_wie_die_werkbank(client, tmp_path):
    """/api/file is the older route of the same bytes (chat rail, agent pane) —
    it must not be the gap."""
    html = tmp_path / "alt.html"
    html.write_text("<p>hallo</p>")
    r = client.get("/api/file", params={"path": str(html)})
    assert "sandbox allow-popups" in _csp(r)

    pdf = tmp_path / "alt.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    assert "sandbox" not in _csp(client.get("/api/file", params={"path": str(pdf)}))


def test_gegeben_svg_wird_es_dicht_obwohl_es_ein_bild_ist(client, tmp_path):
    """SVG is an image that can carry scripts — it counts as a script format."""
    svg = tmp_path / "diagramm.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    r = client.get("/api/file", params={"path": str(svg)})
    assert "sandbox allow-popups" in _csp(r)


def test_die_app_selbst_bleibt_unangetastet(tmp_path, monkeypatch):
    """A sandbox on the app's own HTML or on a JSON answer would switch the surface
    off. The rule may only hit the two file routes."""
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Ephe</title>")
    monkeypatch.setenv("EPHE_FRONTEND_DIR", str(web))
    from server.main import create_app

    shell = TestClient(create_app())
    r = shell.get("/")
    assert r.status_code == 200
    assert "sandbox" not in _csp(r)
    assert "sandbox" not in _csp(shell.get("/api/sessions"))
