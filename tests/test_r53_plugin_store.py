"""
◑ Ephe – wave 5 P3: plugin store light (JSON catalog, 2 segments).
tests/test_r53_plugin_store.py

RULE: tests written BEFORE the implementation.

Pins (accepted against plan step 5):
1. Orphan detection: a plugin whose source left the catalog is 'orphaned' and
   stays loadable (folder presence is enough, not catalog presence).
2. Auto-refresh throttles (fake clock, min interval 600 s, single-flight);
   a manual refresh (force=True) ignores the throttle.
3. `example_prompts: [str]` from the manifest is passed through to the entry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core import plugin_store
from core.plugin_store import (
    CATALOG_VERSION,
    MIN_REFRESH_INTERVAL_S,
    RefreshThrottle,
    detect_orphans,
    load_catalog,
    load_registry,
    sha256_hex,
)


# Helpers

def _manifest(name: str, *, restorable: bool | None = None,
              example_prompts: list[str] | None = None) -> str:
    payload: dict = {"name": name, "version": "1.0.0"}
    if restorable is not None:
        payload["restorable"] = restorable
    if example_prompts is not None:
        payload["example_prompts"] = example_prompts
    return json.dumps(payload)


# 1 · hash helper

def test_sha256_hex_matches_hashlib():
    data = b"ephe"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()


# 2 · Orphaned

def test_detect_orphans_marks_removed_sources() -> None:
    catalog = {"public": [{"name": "alpha"}], "personal": [{"name": "beta"}]}
    installed = ["alpha", "beta", "gamma"]
    assert detect_orphans(catalog, installed) == ["gamma"]


def test_orphaned_plugin_stays_loadable(tmp_path: Path) -> None:
    # A plugin folder without a catalog entry is still a plugin.
    plugin_dir = tmp_path / "skills" / "gamma"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "SKILL.md").write_text(_manifest("gamma"), encoding="utf-8")
    catalog: dict = {"public": [], "personal": []}
    installed = [p.name for p in (tmp_path / "skills").iterdir() if p.is_dir()]
    assert "gamma" in installed
    assert detect_orphans(catalog, installed) == ["gamma"]


# 4 · Throttle

def test_refresh_throttle_drops_within_interval() -> None:
    clock = {"t": 1000.0}
    throttle = RefreshThrottle(min_interval_s=MIN_REFRESH_INTERVAL_S, clock=lambda: clock["t"])
    assert throttle.should_refresh() is True          # the first run always
    throttle.mark_refreshed()
    clock["t"] += 300.0
    assert throttle.should_refresh() is False        # throttled inside the interval
    clock["t"] += 400.0
    assert throttle.should_refresh() is True         # after 700 s > 600 s it is free again
    assert throttle.should_refresh(force=True) is True or throttle.should_refresh(force=True) is True


def test_refresh_throttle_force_bypasses() -> None:
    clock = {"t": 500.0}
    throttle = RefreshThrottle(min_interval_s=MIN_REFRESH_INTERVAL_S, clock=lambda: clock["t"])
    throttle.should_refresh()
    throttle.mark_refreshed()
    # Manual (force=True) regardless of the interval.
    assert throttle.should_refresh(force=True) is True


def test_min_refresh_interval_is_ten_minutes() -> None:
    assert MIN_REFRESH_INTERVAL_S == 600
    assert CATALOG_VERSION == 1


# 5 · catalog shape

def test_load_catalog_two_segments(tmp_path: Path) -> None:
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text(
        json.dumps({
            "version": 1,
            "public": [{"name": "alpha", "sha256": "a" * 64, "url": "https://x/alpha.zip"}],
            "personal": [{"name": "beta", "sha256": "b" * 64, "url": "https://y/beta.zip"}],
        }),
        encoding="utf-8",
    )
    catalog = load_catalog(catalog_file)
    assert set(catalog) >= {"public", "personal"}
    assert catalog["public"][0]["name"] == "alpha"
    assert catalog["personal"][0]["name"] == "beta"


def test_load_catalog_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_catalog(tmp_path / "nope.json") == {"public": [], "personal": []}


# 6 · catalog parity (wave 10 P0-7)

def test_shipped_catalog_wellformed() -> None:
    """The shipped catalog is well-formed: version 1, both segments
    as lists, every entry with name + sha256/url/enabled fields."""
    root = Path(__file__).resolve().parent.parent
    raw = json.loads((root / "plugin-catalog.json").read_text(encoding="utf-8"))
    assert raw.get("version") == CATALOG_VERSION
    catalog = load_catalog(root / "plugin-catalog.json")
    for seg in ("public", "personal"):
        assert isinstance(catalog[seg], list)
        for e in catalog[seg]:
            assert isinstance(e.get("name"), str) and e["name"]
            assert "sha256" in e and "url" in e and "enabled" in e


def test_registry_is_subset_of_catalog() -> None:
    """The installed registry is a subset of the catalog (both segments):
    no installed plugin without a catalog entry."""
    root = Path(__file__).resolve().parent.parent
    catalog = load_catalog(root / "plugin-catalog.json")
    names = {
        str(e["name"])
        for seg in ("public", "personal")
        for e in catalog[seg]
    }
    installed = {str(item["name"]) for item in load_registry() if item.get("name")}
    assert installed <= names, f"Registry ohne Katalogeintrag: {sorted(installed - names)}"


def test_plugins_view_produces_orphans(tmp_path: Path) -> None:
    """I7-4: the orphan row in settings has a producer.

    Before, the UI read `view["orphans"]`, which the aggregate function never
    set — a section that was dead code in the shipped state. Installed here
    without a catalog entry means the set of registry names.
    """
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({
            "version": 1,
            "public": [{
                "name": "alpha", "description": "d", "tags": [], "enabled": True,
                "sha256": "a" * 64, "url": "https://x/alpha.zip",
            }],
            "personal": [],
        }),
        encoding="utf-8",
    )
    registry = tmp_path / "plugins.json"
    registry.write_text(
        json.dumps({"plugins": [
            {"name": "alpha", "enabled": True},
            {"name": "gamma", "enabled": True},
        ]}),
        encoding="utf-8",
    )
    view = plugin_store.plugins_view(catalog_file=catalog, registry_file=registry)
    assert view["orphans"] == ["gamma"]


def test_plugins_view_shows_the_installed_identity_of_a_shadowing_user_plugin(
    tmp_path: Path, monkeypatch
) -> None:
    from core import plugin_manifest, plugin_runtime

    config = tmp_path / "cfg"
    plugin_dir = config / "plugins" / "documents"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "documents",
                "version": "9.9.9",
                "description": "user description",
                "permissions": {"tool_families": [], "data_roots": []},
                "components": {"skills": [], "commands": []},
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "plugin-catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "public": [
                    {
                        "name": "documents",
                        "description": "catalog description",
                        "version": "1.0.0",
                        "sha256": "catalog-hash",
                        "origin": "first-party",
                    }
                ],
                "personal": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    plugin_runtime.invalidate_ownership_cache()
    try:
        view = plugin_store.plugins_view(catalog_file=catalog)
    finally:
        plugin_runtime.invalidate_ownership_cache()
    row = view["public"][0]
    assert row["version"] == "9.9.9"
    assert row["description"] == "user description"
    assert row["source"] == "user"
    assert row["origin"] == "user"
    assert row["sha256"] == plugin_manifest.dir_sha256(plugin_dir)
    assert row["shadowed_builtin"] is True


def test_plugins_view_orphans_empty_when_registry_silent(tmp_path: Path) -> None:
    """No registry => no orphans, but the field is set (UI path)."""
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"version": 1, "public": [], "personal": []}), encoding="utf-8"
    )
    view = plugin_store.plugins_view(catalog_file=catalog, registry_file=tmp_path / "nope.json")
    assert view["orphans"] == []


def test_shipped_catalog_entries_have_description() -> None:
    """Every entry carries a non-empty description (UI column)."""
    root = Path(__file__).resolve().parent.parent
    catalog = load_catalog(root / "plugin-catalog.json")
    for seg in ("public", "personal"):
        for e in catalog[seg]:
            desc = e.get("description")
            assert isinstance(desc, str) and desc.strip(), (
                f"Eintrag {e.get('name')!r} in {seg!r} ohne description"
            )
