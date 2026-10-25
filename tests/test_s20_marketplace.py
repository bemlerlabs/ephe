"""S20: one marketplace index, with a field contract an entry has to hold.

The three catalogs named the same plugins side by side; this pins the migration
into `marketplace/index.json`, the fields every entry must carry, the alias map
that resolves a legacy name to exactly one entry, and the Superpowers pack that
is the first third-party pack in the index.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core import marketplace_catalog as mc
from core import marketplace_index

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "marketplace" / "index.json"


def _index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_the_committed_index_is_fresh() -> None:
    summary = mc.migrate(ROOT)
    assert summary["changed"] is False
    assert summary["verified"] == summary["entries"]


def test_every_entry_carries_the_contract_fields() -> None:
    parsed = mc.validate_catalog(_index())
    for plugin in parsed["plugins"]:
        checks = plugin["verification"]["checks"]
        assert all(checks[name] for name in mc._REQUIRED_CHECKS), plugin["name"]
        assert plugin["license"]
        for version in plugin["versions"]:
            assert marketplace_index._HEX64.match(version["source"]["sha256"])


def test_the_duplicates_between_the_catalogs_are_reported() -> None:
    summary = mc.migrate(ROOT)
    duplicated = {row["id"] for row in summary["duplicates"]}
    assert {"web-research", "code-shell", "documents"} <= duplicated
    assert all(len(row["catalogs"]) > 1 for row in summary["duplicates"])


def test_the_aliases_resolve_a_legacy_name_to_one_entry() -> None:
    index = _index()
    assert marketplace_index.canonical_name(index, "web-search") == "web-research"
    assert marketplace_index.canonical_name(index, "coding-suite") == "code-shell"
    assert marketplace_index.canonical_name(index, "unknown-plugin") == "unknown-plugin"


def test_an_alias_cannot_shadow_a_real_entry() -> None:
    raw = copy.deepcopy(_index())
    raw["aliases"]["memory"] = "web-research"
    with pytest.raises(marketplace_index.IndexError) as exc:
        marketplace_index.validate_index(raw)
    assert exc.value.code == "alias_collision"


def test_an_alias_to_a_missing_entry_is_refused() -> None:
    raw = copy.deepcopy(_index())
    raw["aliases"]["old-name"] = "does-not-exist"
    with pytest.raises(marketplace_index.IndexError) as exc:
        marketplace_index.validate_index(raw)
    assert exc.value.code == "alias_target"


def test_an_entry_without_a_licence_is_refused() -> None:
    raw = copy.deepcopy(_index())
    raw["plugins"][0].pop("license", None)
    with pytest.raises(mc.CatalogError) as exc:
        mc.validate_catalog(raw)
    assert exc.value.code == "license"


def test_an_entry_missing_a_contract_field_is_refused() -> None:
    raw = copy.deepcopy(_index())
    raw["plugins"][0]["verification"]["checks"]["sha256"] = False
    with pytest.raises(mc.CatalogError) as exc:
        mc.validate_catalog(raw)
    assert exc.value.code == "incomplete"


def test_the_superpowers_pack_is_complete() -> None:
    entry = next(p for p in _index()["plugins"] if p["name"] == "superpowers")
    assert entry["license"] == "MIT"
    assert entry["icon"]["light"].endswith("superpowers.svg")
    assert entry["description"]["de"] and entry["description"]["en"]
    assert entry["publisher"]["name"]
    assert entry["verification"]["content"] == "verified"

    pack = ROOT / "marketplace" / "sources" / "superpowers"
    manifest = json.loads((pack / "ephe-plugin.json").read_text(encoding="utf-8"))
    provenance = json.loads((pack / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert len(manifest["components"]["skills"]) == 10
    assert manifest["components"]["tools"] == []
    assert len(provenance["excluded_skills"]) == 4
    assert provenance["license"]["id"] == "MIT"


def test_the_coverage_names_the_gap_instead_of_padding() -> None:
    block = mc.coverage(_index())
    assert block["target"] == 25
    assert block["verified"] == block["entries"]
    assert block["gap"] == max(0, 25 - block["verified"])
