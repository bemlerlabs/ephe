"""The featured tier: a short list of verified publishers above the long tail.

Every entry names its publisher, a documentation URL, an evidence link and a
transport that was checked when the tier was written. The icons are vendor icons
fetched once into the tree, so a render never calls a third party.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


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


def test_no_curated_row_claims_a_shared_launchers_downloads() -> None:
    import json

    tier = json.loads(
        (ROOT / "marketplace" / "registry-curated.json").read_text(encoding="utf-8")
    )["entries"]
    for entry in tier:
        assert "mcp-proxy-for-aws" not in str(entry.get("install_hint") or ""), entry["id"]
