"""The plugin view carries scope beside provenance.

``public`` and ``personal`` stay the catalogue split. ``global`` and
``session`` are the scope split. A mode names a bundle only through
``MODE_PLUGINS``. The committed enabled bit is the one the lifecycle stored.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _catalog(tmp_path: Path) -> Path:
    catalog = tmp_path / "plugin-catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "version": 1,
                "public": [
                    {"name": name, "description": "d", "tags": [], "enabled": True}
                    for name in ("countdown", "web-research")
                ],
                "personal": [],
            }
        ),
        encoding="utf-8",
    )
    return catalog


@pytest.fixture()
def hermetic_config(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


def test_the_view_names_scope_module_and_modes_without_flipping_enabled(
    tmp_path, hermetic_config, monkeypatch
) -> None:
    from core import plugin_scope, plugin_store

    monkeypatch.setattr(
        plugin_scope,
        "MODE_PLUGINS",
        {
            "analyst": frozenset(),
            "architect": frozenset(),
            "operator": frozenset({"countdown"}),
            "creator": frozenset(),
        },
    )
    view = plugin_store.plugins_view(
        catalog_file=_catalog(tmp_path),
        registry_file=tmp_path / "plugins.json",
    )
    rows = {row["name"]: row for row in view["public"]}
    countdown = rows["countdown"]
    research = rows["web-research"]

    assert countdown["scope"] == "session"
    assert countdown["provided_by_modes"] == ["operator"]
    assert countdown["module"] == "ui/index.html"
    assert countdown["configuration"] == ""
    assert research["scope"] == "global"
    assert research["provided_by_modes"] == []
    assert research["module"] == "tools/handlers.py:web_search"
    assert research["configuration"] == "read, network"
    assert {row["name"] for row in view["session"]} == {"countdown"}
    assert "web-research" in {row["name"] for row in view["global"]}
    assert "countdown" not in {row["name"] for row in view["global"]}
    assert view["personal"] == []

    again = plugin_store.plugins_view(
        catalog_file=_catalog(tmp_path),
        registry_file=tmp_path / "plugins.json",
    )
    again_rows = {row["name"]: row for row in again["public"]}
    assert again_rows["countdown"]["enabled"] is countdown["enabled"]
    assert again_rows["web-research"]["enabled"] is research["enabled"]
