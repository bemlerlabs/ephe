"""PE2E finding 3b — the plugin view names every installed bundle.

`GET /api/plugins` built `public`/`personal` from `plugin-catalog.json` and offered
`orphans` for everything else, so a bundle Creator Mode installed on this machine had
no row: the settings page could not show it, and the CLI read the same catalog. The
view now carries an `installed` list read from the plugin folders themselves, with the
switch state and the capabilities the manifest declares.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.plugin_bundle import mark_installed, write_bundle


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


def _row(view: dict, name: str) -> dict:
    rows = [row for row in view["installed"] if row["name"] == name]
    assert len(rows) == 1, f"{name!r} appears {len(rows)} times in the installed list"
    return rows[0]


def test_a_locally_installed_bundle_is_listed_with_state_and_capabilities(device) -> None:
    write_bundle(device / "plugins", "hello-widget", surface_title="Hello widget")
    mark_installed("hello-widget", enabled=False)

    from core import plugin_store

    view = plugin_store.plugins_view()
    row = _row(view, "hello-widget")

    assert row["version"] == "0.1.0"
    assert row["source"] == "user"
    assert row["trust"] == "local"
    assert row["state"] == "disabled"
    assert row["enabled"] is False
    assert row["in_catalog"] is False
    assert [tool["name"] for tool in row["capabilities"]["tools"]] == ["now"]
    assert row["capabilities"]["surface"]["title"] == "Hello widget"
    assert [command["name"] for command in row["capabilities"]["commands"]] == ["/ping"]


def test_the_bundle_without_a_catalog_row_is_not_only_an_orphan(device) -> None:
    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)

    from core import plugin_store

    view = plugin_store.plugins_view()
    catalog_names = [
        entry["name"] for segment in ("public", "personal") for entry in view[segment]
    ]

    # The catalogue keeps its own rows; the folder truth is the `installed` section, and it
    # carries the bundle whether or not a catalogue row exists for it.
    assert "hello-widget" not in catalog_names
    assert "hello-widget" in [row["name"] for row in view["installed"]]


def test_a_quarantined_folder_is_listed_as_an_error_row(device) -> None:
    broken = device / "plugins" / "broken"
    broken.mkdir(parents=True)
    (broken / "ephe-plugin.json").write_text("{not json", encoding="utf-8")

    from core import plugin_store

    view = plugin_store.plugins_view()
    row = _row(view, "broken")

    assert row["state"] == "error"
    assert row["enabled"] is False
    assert row["error"]
    assert row["capabilities"] == {
        "tools": [],
        "surface": None,
        "commands": [],
        "skills": [],
    }


def test_every_bundle_appears_once_and_a_builtin_names_its_own_face(device) -> None:
    from core import plugin_store

    view = plugin_store.plugins_view()
    names = [row["name"] for row in view["installed"]]

    assert names == sorted(set(names))
    countdown = _row(view, "countdown")
    assert countdown["source"] == "builtin"
    assert countdown["in_catalog"] is True
    assert countdown["capabilities"]["surface"]["title"] == "Countdown"


def test_the_route_serves_the_installed_list(device) -> None:
    write_bundle(device / "plugins", "hello-widget")
    mark_installed("hello-widget", enabled=False)

    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/plugins")
        view = response.json()

    assert response.status_code == 200
    row = _row(view, "hello-widget")
    assert row["state"] == "disabled"
    assert row["capabilities"]["tools"][0]["name"] == "now"
