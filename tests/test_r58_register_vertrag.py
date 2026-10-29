"""R58 — the contract of the deep register (wave 6, contract I3-6).

The original 'full matrix' pinned 15 sections and 80-95 fields. That exactly was
the mistake: what got counted was breadth, not effectiveness. I3-6 built back to
the nine fields a consumer calls through the accessor line. This test holds the
contract that replaced the matrix:

1. Every field is read (accessor call) and has a description text.
2. Every section is non-empty and sorted by its prefix.
3. Field hygiene: type/default/label/labelEn, number min/max (default inside),
   select options (default contained).
4. normalize_deep: clamping, types, unknown fields and sections get dropped.
5. deep_view: value from persistence, otherwise the default; hint only on read fields.
6. validate_sections: range violation and an illegal option raise (422).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings_hints import HINTS  # noqa: E402
from core.settings_schema import (  # noqa: E402
    SECTIONS,
    SCHEMA,
    deep_view,
    normalize_deep,
    validate_sections,
)
from tests.test_settings_surface_is_real import _read_keys  # noqa: E402

# I6-4: 'hooks' came with a reader (core/user_hooks.py), a guard rail and a text in
# both languages — that is exactly what the contract demands before a section may
# stand here.
SECTION_KEYS = {"chat", "appearance", "shortcuts", "advanced", "plugins", "memory",
                "ephemera", "cron", "hooks", "sol"}


def _fields_of(section_key: str) -> list[str]:
    for s in SECTIONS:
        if s["key"] == section_key:
            return list(s["fields"])
    return []


# 1/2. Contract: read, described, sectioned

def test_jedes_feld_wird_gelesen() -> None:
    """The core of the contract: a field without a reader is not a field."""
    toten = sorted(set(SCHEMA) - _read_keys())
    assert not toten, f"Felder ohne Accessor-Aufruf: {toten}"


def test_jedes_feld_ist_beschrieben() -> None:
    # Wave 2/B1: a multiline field is not a register row. Its card carries the copy
    # from the locale files (both languages), because the German half of a HINTS pair
    # may not grow any more. The keys below are that card's contract.
    cards = {"chat.custom_instructions": ("settings.customInstructionsTitle",
                                          "settings.customInstructionsHint"),
             "plugins.plugin_lifecycle_read_only": ("settings.pluginReadOnly",
                                                    "settings.pluginReadOnlyHint")}
    for key, keys in cards.items():
        import json
        from pathlib import Path as _P

        root = _P(__file__).resolve().parents[1] / "app" / "src" / "locales"
        for lang in ("en", "de"):
            data = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
            for dotted in keys:
                node = data
                for part in dotted.split("."):
                    node = node[part]
                assert isinstance(node, str) and node.strip(), (key, lang, dotted)
    fehlt = sorted(k for k in SCHEMA if k not in HINTS and k not in cards)
    assert not fehlt, f"gelesene Felder ohne Beschreibungstext: {fehlt}"


def test_sektionen_decken_das_register() -> None:
    assert {s["key"] for s in SECTIONS} == SECTION_KEYS
    for s in SECTIONS:
        assert s["fields"], f"section {s['key']} has no fields"
        assert all(k.startswith(f"{s['key']}.") for k in s["fields"])
    declared = {k for s in SECTIONS for k in s["fields"]}
    assert declared == set(SCHEMA), sorted(declared ^ set(SCHEMA))


# 3. Field hygiene (type bounds labels)

def test_every_field_has_type_default_labels():
    for fkey, meta in SCHEMA.items():
        assert meta["type"] in ("bool", "number", "select", "text"), fkey
        assert "default" in meta, fkey
        assert meta.get("label") and meta.get("labelEn"), fkey
        if meta["type"] == "number":
            assert meta["min"] <= meta["default"] <= meta["max"], fkey
        if meta["type"] == "select":
            assert meta["default"] in meta["options"], fkey


# 4. Roundtrip through normalize_deep / deep_view

def test_roundtrip_user_payload_matches_view(monkeypatch, tmp_path):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    payload = {
        "appearance": {"appearance.font_scale": 120, "appearance.update_check": False},
        "chat": {"chat.details_mode": "collapsed", "chat.show_reasoning": False},
        "advanced": {"advanced.api_timeout": 90},
        "plugins": {"plugins.plugin_autorun": True},
    }
    norm = normalize_deep(payload)
    for sec_key, fields in payload.items():
        for fkey, value in fields.items():
            assert norm[sec_key][fkey] == value, fkey

    from core import settings_schema as ss

    assert ss.save_deep_settings(norm) is True
    view = {s["key"]: {f["key"]: f["value"] for f in s["fields"]} for s in deep_view()}
    for sec_key, fields in payload.items():
        for fkey, value in fields.items():
            assert view[sec_key][fkey] == value, fkey


def test_normalize_clamps_and_drops_unknown():
    norm = normalize_deep({"appearance": {"appearance.font_scale": 10 ** 6,
                                          "appearance.bogus": 1}})
    assert norm["appearance"]["appearance.font_scale"] == SCHEMA["appearance.font_scale"]["max"]
    assert "appearance.bogus" not in norm["appearance"]
    norm2 = normalize_deep({"plugins": {"plugins.plugin_signature_check": "off"}})
    assert norm2["plugins"]["plugins.plugin_signature_check"] is False


def test_untouched_sections_are_not_injected():
    norm = normalize_deep({"chat": {"show_reasoning": True}})
    assert set(norm.keys()) == {"chat"}


# 5. deep_view: guard rails, step and the hint channel

def test_deep_view_reicht_grenzen_texte_und_werte(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    for key, meta in SCHEMA.items():
        entry = entries[key]
        assert entry["value"] == meta["default"], key
        if key in HINTS:
            assert entry["hint"] == HINTS[key][0] and entry["hintEn"] == HINTS[key][1], key
        elif meta.get("hintKey"):
            # The copy lives in the locale files, so the register carries the key
            # instead of a second German/English pair.
            assert entry["hintKey"] == meta["hintKey"], key
            assert "hint" not in entry and "hintEn" not in entry, key
        else:
            # A multiline field's copy lives in the locale files; its register entry
            # still carries the bound the editor uses.
            assert meta["type"] == "text" and meta.get("multiline") is True, key
            assert entry["maxChars"] == meta["max_chars"], key
        if meta["type"] == "number":
            assert (entry["min"], entry["max"]) == (meta["min"], meta["max"]), key
            assert entry["step"] > 0, key
        if meta["type"] == "select":
            assert entry["options"] == list(meta["options"]), key
            assert "step" not in entry, key


# 6. validate_sections 422 semantics

def test_validate_rejects_out_of_range():
    with pytest.raises(ValueError):
        validate_sections({"advanced": {"advanced.api_timeout": 10 ** 9}})
    with pytest.raises(ValueError):
        validate_sections({"chat": {"chat.details_mode": "breit"}})
    ok = validate_sections({"plugins": {"plugins.plugin_autorun": True}})
    assert ok == {"plugins": {"plugins.plugin_autorun": True}}
