"""S1 — the public registry mirror: generator and runtime.

The mirror is the breadth answer for the connector area: one full cursor
pass over the public registry (CC0 metadata), committed as a snapshot the
runtime serves without a network call. The curated bilingual catalog stays
the first rows; the mirror entries keep the publishers' own English text.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from core import mcp_catalog  # noqa: E402


def test_mirror_snapshot_serves_hundreds_of_connectors():
    entries = mcp_catalog.registry_entries()
    assert len(entries) > 500
    seen: set[str] = set()
    for entry in entries:
        assert {
            "id", "name", "description", "category", "docs", "version", "source",
        } <= set(entry)
        assert entry["source"] == "registry"
        assert entry["description"].isascii()
        assert entry["id"] not in seen
        seen.add(entry["id"])


def test_catalog_keeps_the_curated_rows():
    curated = mcp_catalog.catalog_entries()
    assert curated
    assert curated[0]["id"].startswith("mcp-")


def test_curated_tier_is_a_small_derived_window():
    entries = mcp_catalog.curated_entries()
    assert 200 <= len(entries) <= 600
    for entry in entries:
        assert entry.get("curated_reason") in {"pick", "recent", "popular"}
        assert entry["source"] == "registry"


def test_route_serves_three_tiers():
    from server.routes.mcp import get_discover_registry

    body = get_discover_registry()
    assert {"curated", "registry", "registry_count"} <= set(body)
    assert body["registry"] == [], "the full tier must not ride the default read"
    assert body["registry_count"] == len(mcp_catalog.registry_entries())
    assert 0 < len(body["curated"]) <= body["registry_count"]
    full = get_discover_registry(full=True)
    assert len(full["registry"]) == body["registry_count"]


def test_generator_follows_the_cursor_and_dedupes(monkeypatch):
    import catalog_discover

    pages = {
        "": {
            "metadata": {"nextCursor": "a/one:1.1.0", "count": 3},
            "servers": [
                {"server": {"name": "a/one", "title": "Alpha",
                            "description": "read files and folders", "version": "1.0.0",
                            "packages": [{"transport": {"type": "stdio"},
                                          "runtimeHint": "npx",
                                          "identifier": "alpha"}]},
                 "_meta": {"isLatest": False, "publishedAt": "2026-01-01T00:00:00Z"}},
                {"server": {"name": "a/one", "title": "Alpha",
                            "description": "read files and folders", "version": "1.1.0",
                            "packages": [{"transport": {"type": "stdio"},
                                          "runtimeHint": "npx",
                                          "identifier": "alpha@1.1"}]},
                 "_meta": {"isLatest": True, "publishedAt": "2026-02-01T00:00:00Z"}},
                {"server": {"name": "c/gamma", "title": "Gamma",
                            "description": "the gamma provider", "version": "1.0.0"},
                 "_meta": {"isLatest": True}},
            ],
        },
        "a/one:1.1.0": {
            "metadata": {"nextCursor": "", "count": 1},
            "servers": [
                {"server": {"name": "b/two", "title": "Beta",
                            "description": "postgres tools", "version": "2.0.0",
                            "remotes": [{"type": "streamable-http",
                                         "url": "https://beta.example/mcp"}]},
                 "_meta": {"isLatest": True}},
            ],
            "nextCursor": "",
        },
    }

    calls: list[str] = []

    def fake_fetch(url, **kwargs):
        cursor = ""
        if "cursor=" in url:
            quoted = url.split("cursor=", 1)[1].split("&")[0]
            cursor = urllib.parse.unquote(quoted)
        calls.append(cursor)
        return json.dumps(pages[cursor]).encode()

    monkeypatch.setattr(catalog_discover, "fetch", fake_fetch)
    # The filter reuses the language gate's marker vocabulary; the test
    # substitutes its own marker so no sample of foreign prose is stored here.
    monkeypatch.setattr("language_inventory.WORD", __import__("re").compile(r"\bgamma\b"))
    count, entries, errors = catalog_discover.mirror_registry()
    assert not errors
    assert count == 2
    assert calls == ["", "a/one:1.1.0"]
    by_id = {entry["id"]: entry for entry in entries}
    assert by_id["a-one"]["version"] == "1.1.0"
    assert by_id["b-two"]["category"] == "database"
    assert by_id["b-two"]["install_hint"].endswith("(streamable-http)")
    assert by_id["a-one"]["install_hint"] == "npx -y alpha@1.1 (stdio)"


def test_bootstrap_returns_one_frame(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as client:
        r = client.get("/api/discover/bootstrap")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"skills", "sources", "home", "catalog", "curated", "registry_count",
            "installed", "usage"} <= set(body)
    assert body["registry_count"] == len(mcp_catalog.registry_entries())
    assert isinstance(body["curated"], list)
    assert isinstance(body["skills"], list)
    assert isinstance(body["usage"], dict)


def test_the_launch_line_names_the_package():
    """A runtime alone is not a launch line: `npx (stdio)` names nothing a reader
    could type, and the identifier is what makes the entry installable."""
    import catalog_discover

    hint, _docs = catalog_discover._mirror_hint(
        {"name": "x/y", "packages": [{"transport": {"type": "stdio"},
                                      "runtimeHint": "npx", "identifier": "@x/y-mcp"}]}
    )
    assert hint == "npx -y @x/y-mcp (stdio)"


def test_a_package_coordinate_is_read_from_the_launch_line():
    import catalog_discover

    assert catalog_discover.package_of({"install_hint": "npx -y @a/b (stdio)"}) == ("npm", "@a/b")
    assert catalog_discover.package_of({"install_hint": "uvx mcp-server-x (stdio)"}) == ("pypi", "mcp-server-x")
    assert catalog_discover.package_of({"install_hint": "https://x/mcp (streamable-http)"}) is None


def test_the_curated_tier_spreads_over_the_categories():
    """Round-robin: no category takes a second entry before every other one that has
    one takes its first, so the shelf stays broad."""
    import collections

    entries = mcp_catalog.curated_entries()
    counts = collections.Counter(entry["category"] for entry in entries)
    assert len(counts) >= 8
    assert max(counts.values()) - min(counts.values()) <= 2
