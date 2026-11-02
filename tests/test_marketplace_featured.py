"""The featured tier: a short list of verified publishers above the long tail.

Every entry names its publisher, a documentation URL, an evidence link and a
transport that was checked when the tier was written. The icons are vendor icons
fetched once into the tree, so a render never calls a third party.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FETCHER = ROOT / "scripts" / "fetch_marketplace_icons.py"


def _load_fetcher():
    spec = importlib.util.spec_from_file_location("fetch_marketplace_icons_under_test", FETCHER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_tier_is_ranked_and_every_row_carries_evidence() -> None:
    from core.mcp_catalog import featured_entries

    entries = featured_entries()
    assert len(entries) >= 12
    ranks = [int(entry["rank"]) for entry in entries]
    assert ranks == sorted(ranks)
    for entry in entries:
        assert entry["source"] == "featured"
        assert entry["docs"].startswith("https://"), entry["id"]
        assert entry["install_hint"], entry["id"]
        assert entry["transport"] in {"http", "stdio"}, entry["id"]
        assert entry["evidence"], entry["id"]
        assert all(url.startswith("https://") for url in entry["evidence"])
        assert entry["why"]


def test_every_featured_icon_is_a_png_in_the_tree() -> None:
    from core.mcp_catalog import featured_entries

    directory = ROOT / "marketplace" / "icons" / "providers"
    for entry in featured_entries():
        path = directory / f"{entry['icon']}.png"
        assert path.is_file(), f"{entry['icon']}: no icon in the tree"
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", entry["icon"]
    sources = (directory / "SOURCES.json").read_text(encoding="utf-8")
    assert '"source"' in sources


def test_the_icon_route_serves_a_png_and_refuses_a_bad_slug() -> None:
    from fastapi import HTTPException

    from server.routes.discover import discover_icon

    response = discover_icon("github")
    assert response.media_type == "image/png"
    with pytest.raises(HTTPException):
        discover_icon("../etc/passwd")
    with pytest.raises(HTTPException):
        discover_icon("no-such-vendor")


def test_a_curated_icon_slug_survives_the_loader_and_a_broken_one_does_not(
    tmp_path, monkeypatch
) -> None:
    """The curated tier may name a vendor icon; the load is the gate.

    A slug the icon route could never resolve is dropped before the frame is
    served, so `/discover/bootstrap` stays deterministic and offline whatever
    the data file holds."""
    import json

    from core import mcp_catalog

    path = tmp_path / "registry-curated.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {"id": "ok", "name": "Ok", "icon": "github"},
                    {"id": "url", "name": "Url", "icon": "https://example.com/x.png"},
                    {"id": "traversal", "name": "Traversal", "icon": "../etc/passwd"},
                    {"id": "bare", "name": "Bare"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_catalog, "_CURATED_PATH", path)
    entries = {entry["id"]: entry for entry in mcp_catalog.curated_entries()}
    assert entries["ok"]["icon"] == "github"
    assert "icon" not in entries["url"]
    assert "icon" not in entries["traversal"]
    assert "icon" not in entries["bare"]


def test_no_curated_row_claims_a_shared_launchers_downloads() -> None:
    import json

    tier = json.loads(
        (ROOT / "marketplace" / "registry-curated.json").read_text(encoding="utf-8")
    )["entries"]
    for entry in tier:
        assert "mcp-proxy-for-aws" not in str(entry.get("install_hint") or ""), entry["id"]


def test_the_curated_pass_reads_a_hosted_icon_and_refuses_another_domain() -> None:
    fetch = _load_fetcher()
    # A root-relative href resolves on the publisher's own host.
    page = '<head><link rel="icon" href="/fav.ico"></head>'
    assert fetch._parse_icon_href(page, "mcp.acme.com") == "https://mcp.acme.com/fav.ico"
    # An apple-touch-icon is the same fallback; a relative path stays on the host.
    touch = '<link rel="apple-touch-icon" href="icons/touch.png">'
    assert fetch._parse_icon_href(touch, "acme.com") == "https://acme.com/icons/touch.png"
    # A stylesheet link and a foreign host are both no answer.
    assert fetch._parse_icon_href('<link rel="stylesheet" href="/a.css">', "acme.com") == ""
    assert fetch._parse_icon_href(
        '<link rel="icon" href="https://cdn.other.test/x.ico">', "acme.com"
    ) == ""


def test_the_curated_pass_refuses_a_mark_over_the_size_budget() -> None:
    fetch = _load_fetcher()
    assert fetch._accept(b"png" * 3) is True
    assert fetch._accept(b"x" * (fetch.MAX_ICON_BYTES + 1)) is False
    assert fetch._accept(None) is False


def test_the_curated_pass_prefers_the_favicon_before_the_homepage(monkeypatch) -> None:
    fetch = _load_fetcher()

    def fake_fetch(url):
        if url == "https://acme.com/favicon.ico":
            return b"raw"
        raise AssertionError(f"the homepage should not be asked when the favicon answers: {url}")

    monkeypatch.setattr(fetch, "_fetch", fake_fetch)
    monkeypatch.setattr(fetch, "_png", lambda raw: b"small")
    got = fetch._resolve_icon("acme.com")
    assert got is not None and got[1] == "https://acme.com/favicon.ico"


def test_the_curated_fallback_lands_on_the_homepage_href(monkeypatch) -> None:
    fetch = _load_fetcher()

    def fake_fetch(url):
        if url == "https://acme.com/favicon.ico":
            return None
        if url == "https://acme.com/":
            return b'<link rel="icon" href="fav.png">'
        if url == "https://acme.com/fav.png":
            return b"raw"
        raise AssertionError(f"unexpected request {url}")

    monkeypatch.setattr(fetch, "_fetch", fake_fetch)
    monkeypatch.setattr(fetch, "_png", lambda raw: b"small")
    got = fetch._resolve_icon("acme.com")
    assert got is not None and got[1] == "https://acme.com/fav.png"


def test_the_curated_pass_keeps_one_host_per_slug_in_name_order() -> None:
    fetch = _load_fetcher()
    entries = [
        {"install_hint": "https://www.acme.com/mcp (streamable-http)"},
        {"install_hint": "https://acme.com/mcp (streamable-http)"},
        {"install_hint": "npx -y only-package (stdio)"},
        {"install_hint": "https://{server_address}/mcp (streamable-http)"},
    ]
    targets = fetch.curated_targets(entries)
    assert targets == {"acme-com": "acme.com"}
