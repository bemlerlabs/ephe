"""Description duty: every real control belongs with a text (wave I3).

The settings surface should explain what a value changes — but an explained button
without a reader sells false depth. Both directions are therefore errors: wired
without a text (unexplained) and a text without wiring (decoration). The same
detector as in tests/test_settings_surface_is_real.py sets the standard: a field
counts as a control when a consumer calls it through the accessor line by its full
key.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings_hints import HINTS  # noqa: E402
from core.settings_schema import SCHEMA, deep_view  # noqa: E402
from tests.test_settings_surface_is_real import _read_keys  # noqa: E402

MIN_LEN = 24
MAX_LEN = 240


def _normal(text: str) -> str:
    return " ".join(text.strip().lower().split()).rstrip(".!?")


# Both directions of the duty

def _row_keys() -> list[str]:
    """Wired fields that render as a register row.

    A multiline field has no row: it is edited in a full-width card whose title and
    explanation come from the locale files (the de/en pair HINTS carries would be a
    second copy of the same sentence). The duty below is about rows, so those fields
    are the one shape it does not cover.
    """
    return [k for k in _read_keys() if not SCHEMA.get(k, {}).get("multiline")]


def test_jeder_regler_hat_einen_text() -> None:
    # A field may carry its explanation as a locale key when the text belongs to
    # the product surface rather than to this German-annotated register.
    fehlt = sorted(
        k
        for k in _row_keys()
        if k not in HINTS and not SCHEMA.get(k, {}).get("hintKey")
    )
    assert not fehlt, f"verdrahtete Felder ohne Erklaerung: {fehlt}"


def test_kein_text_ohne_regler() -> None:
    dekoriert = sorted(k for k in HINTS if k not in _read_keys())
    assert not dekoriert, (
        "Beschreibungstexte fuer Felder ohne Leser — ein toter Knopf mit "
        f"schoenem Text ist eine Falschaussage: {dekoriert}"
    )


def test_kein_text_fuer_ein_fremdes_feld() -> None:
    fremde = sorted(k for k in HINTS if k not in SCHEMA)
    assert not fremde, f"HINTS kennt Felder, die das Register nicht hat: {fremde}"


# Shape of the texts

@pytest.mark.parametrize("key", sorted(HINTS))
def test_text_hat_beide_sprachen_in_guter_form(key: str) -> None:
    pair = HINTS[key]
    assert isinstance(pair, tuple) and len(pair) == 2, key
    de, en = pair
    for text in (de, en):
        assert MIN_LEN <= len(text) <= MAX_LEN, f"{key}: {len(text)} Zeichen"
    assert de != en, f"{key}: de und en sind identisch"
    # An echo of the label explains nothing.
    meta = SCHEMA[key]
    assert _normal(de) != _normal(meta["label"]), f"{key}: de wiederholt nur das Label"
    assert _normal(en) != _normal(meta["labelEn"]), f"{key}: en wiederholt nur das Label"


@pytest.mark.parametrize("key", sorted(HINTS))
def test_text_ist_kein_platzhalter(key: str) -> None:
    for text in HINTS[key]:
        for word in ("TODO", "tbd", "XXX", "lorem"):
            assert word.lower() not in text.lower(), f"{key}: Platzhalter {word!r}"


# The channel up into the API view

def test_deep_view_reicht_beide_sprachen_durch(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    wired = _read_keys()
    for key, (de, en) in HINTS.items():
        assert entries[key]["hint"] == de
        assert entries[key]["hintEn"] == en
    for key in entries:
        if key not in wired:
            assert "hint" not in entries[key], f"{key}: Feld ohne Leser traegt Text"


def test_deep_view_hat_keinen_halben_kanal(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the read without the write (or the other way round) leaves the client idling."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    for entry in (f for s in deep_view() for f in s["fields"]):
        assert ("hint" in entry) == ("hintEn" in entry), entry["key"]


def test_a_hint_key_reaches_the_view_without_a_second_copy(tmp_path, monkeypatch) -> None:
    """A product-copy hint lives in the locale, not as a second HINTS pair."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core.settings_schema import deep_view

    entries = {field["key"]: field for section in deep_view() for field in section["fields"]}
    entry = entries["plugins.plugin_lifecycle_read_only"]

    assert entry["labelKey"] == "settings.pluginReadOnly"
    assert entry["hintKey"] == "settings.pluginReadOnlyHint"
    assert "hint" not in entry and "hintEn" not in entry
    assert entry["label"] and entry["labelEn"]
