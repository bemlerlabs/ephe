"""W1-7 — the switch view carries the one surface a v2 bundle declares.

`core/plugin_store.plugins_view` is the payload behind the plugin settings rows.
A bundle that declares `components.ui` must arrive with its descriptor already
defaulted and flattened by `core/plugin_ui_capabilities.ui_descriptor`, so the
row can offer the surface without reading a manifest. A bundle without a
surface carries no `surface` key at all — the absence is the row's answer that
there is nothing here to open.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _catalog(tmp_path: Path, names: list[str]) -> Path:
    catalog = tmp_path / "plugin-catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "version": 1,
                "public": [
                    {"name": n, "description": "d", "tags": [], "enabled": True}
                    for n in names
                ],
                "personal": [],
            }
        ),
        encoding="utf-8",
    )
    return catalog


@pytest.fixture()
def hermetic_config(tmp_path, monkeypatch):
    """The view reads the shipped built-ins plus an empty user root."""
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


def test_the_countdown_row_carries_its_surface_descriptor(tmp_path, hermetic_config) -> None:
    from core import plugin_store

    view = plugin_store.plugins_view(
        catalog_file=_catalog(tmp_path, ["countdown", "documents"]),
        registry_file=tmp_path / "plugins.json",
    )
    rows = {row["name"]: row for row in view["public"]}

    surface = rows["countdown"]["surface"]
    assert surface["entry"] == "ui/index.html"
    assert surface["type"] == "floating-window"
    assert surface["title"] == "Countdown"
    assert surface["width"] == 260
    assert surface["height"] == 132
    assert surface["transparent"] is True
    assert surface["always_on_top"] is True
    assert surface["capabilities"] == ["audio-out", "dock-badge", "notifications"]
    assert surface["grants"] == []


def test_a_bundle_without_a_surface_key_stays_unopened(tmp_path, hermetic_config) -> None:
    from core import plugin_store

    view = plugin_store.plugins_view(
        catalog_file=_catalog(tmp_path, ["documents"]),
        registry_file=tmp_path / "plugins.json",
    )
    assert "surface" not in view["public"][0]
