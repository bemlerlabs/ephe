"""The line between the register and the consumer (wave I3).

Until now settings.json was a sink: values were persisted but almost nobody read
them — and the three readers that did exist each copied
`load_deep_settings().get(section, {}).get(key)` with their own default
handling. These tests enforce the single access path: the deep `deep_*`
accessors — typed, clamped to the bounds, loud on an unknown key.

A typo in a consumer must not silently yield `None` — that would be the same
false statement as a button without a reader, only invisible.
"""
from __future__ import annotations

import json

import pytest

from core.settings_schema import (
    SCHEMA,
    deep_bool,
    deep_number,
    deep_select,
    deep_value,
    save_deep_settings,
    settings_path,
)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Move settings.json into a test room — ~/.ephe stays untouched."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    yield


def _write_raw(sections: dict) -> None:
    """Write straight in the file format (a foreign writer, not the store path)."""
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"version": 1, "sections": sections}, ensure_ascii=False),
        encoding="utf-8",
    )


# Default without an entry

def test_ohne_datei_gilt_der_register_default() -> None:
    assert deep_bool("appearance.update_check") is SCHEMA["appearance.update_check"]["default"]
    assert deep_number("appearance.font_scale") == SCHEMA["appearance.font_scale"]["default"]
    assert deep_select("chat.details_mode") == SCHEMA["chat.details_mode"]["default"]


def test_nur_die_angefasste_sektion_ist_gesetzt() -> None:
    assert save_deep_settings({"chat": {"chat.details_mode": "collapsed"}}) is True
    assert deep_select("chat.details_mode") == "collapsed"
    # A section never touched falls back completely, not to 0/False.
    assert deep_bool("plugins.plugin_autorun") is SCHEMA["plugins.plugin_autorun"]["default"]


# The user value wins

def test_gespeicherter_wert_gewinnt_gegen_den_default() -> None:
    assert save_deep_settings(
        {
            "appearance": {"appearance.update_check": False},
            "plugins": {"plugins.plugin_autorun": True, "plugins.plugin_signature_check": False},
        }
    )
    assert deep_bool("appearance.update_check") is False
    assert deep_bool("plugins.plugin_autorun") is True
    assert deep_bool("plugins.plugin_signature_check") is False


# Hard bounds

def test_ausserhalb_der_schranken_wird_geklemt_nicht_durchgereicht() -> None:
    """A settings.json edited by hand must not hand a consumer 10**9."""
    _write_raw({"appearance": {"appearance.font_scale": 10 ** 9}})
    assert deep_number("appearance.font_scale") == SCHEMA["appearance.font_scale"]["max"]
    _write_raw({"appearance": {"appearance.font_scale": -5}})
    assert deep_number("appearance.font_scale") == SCHEMA["appearance.font_scale"]["min"]


def test_unbekannte_selectoption_wird_zum_default() -> None:
    _write_raw({"chat": {"chat.details_mode": "breit"}})
    assert deep_select("chat.details_mode") in SCHEMA["chat.details_mode"]["options"]


def test_mutwilliger_typ_in_der_datei_faellt_auf_den_default_zurueck() -> None:
    _write_raw({"advanced": {"advanced.api_timeout": "zwoeihundert"}})
    assert deep_number("advanced.api_timeout") == SCHEMA["advanced.api_timeout"]["default"]


# Loud on misuse

def test_unbekannter_schluessel_wirft_laut() -> None:
    """A typo in the line must not silently be None."""
    with pytest.raises(KeyError):
        deep_value("appearance.fontGroesse")
    with pytest.raises(KeyError):
        deep_bool("safety.approval_profile")


def test_falscher_accessor_fuer_den_feldtyp_wirft() -> None:
    """deep_bool on a number field would be a silent permanent false report."""
    with pytest.raises(TypeError):
        deep_bool("appearance.font_scale")
    with pytest.raises(TypeError):
        deep_number("plugins.plugin_autorun")
    with pytest.raises(TypeError):
        deep_select("advanced.api_timeout")


# Freshness: no process may lag behind a save

def test_speicherung_ist_sofort_sichtbar() -> None:
    assert deep_number("advanced.api_timeout") == SCHEMA["advanced.api_timeout"]["default"]
    save_deep_settings({"advanced": {"advanced.api_timeout": 300}})
    assert deep_number("advanced.api_timeout") == 300


def test_fremdschreiber_wird_gesehen() -> None:
    """A second process (the CLI) writes the same file while the server runs —
    the line reads per call; no cache may go blind."""
    assert deep_number("advanced.api_timeout") == SCHEMA["advanced.api_timeout"]["default"]
    _write_raw({"advanced": {"advanced.api_timeout": 30}})
    assert deep_number("advanced.api_timeout") == 30


def test_defaultuebersteuerung_ohne_registerwert() -> None:
    assert deep_value("chat.details_mode", "collapsed") == "collapsed"
