"""I6-3 — The behaviour sliders reach the core, not just the surface.

A field in the register is a control only once production code reads its value
(tests/test_settings_surface_is_real.py checks the call). This test checks
the other half: that the call also takes effect. Both fields used to live as
a constant in core/chat.py — without a test the handover to the slider would be
a claim.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from core.settings_schema import save_deep_settings, validate_sections  # noqa: E402


def _set(**fields: int) -> None:
    assert save_deep_settings(validate_sections({"chat": fields}))


def test_der_werkzeug_kap_liest_die_steuerung(empty_ephe_home) -> None:
    """Default = the earlier constant; a set value replaces it."""
    from core.chat import _cap_tool_result, _tool_result_cap
    from core.settings_schema import SCHEMA

    assert _tool_result_cap() == SCHEMA["chat.tool_result_chars"]["default"]
    capped = _cap_tool_result("x" * 40000)
    assert len(capped) == 32000 + len(" …[truncated at 32000 chars]")

    _set(**{"chat.tool_result_chars": 5000})
    assert _tool_result_cap() == 5000
    short = _cap_tool_result("y" * 40000)
    assert len(short) == 5000 + len(" …[truncated at 5000 chars]")
    # below the cap the output stays untouched — no marker, no cut
    assert _cap_tool_result("z" * 5000) == "z" * 5000


def test_die_nudge_zahl_liest_die_steuerung(empty_ephe_home) -> None:
    """0 attempts means: the aborted plan stays as it is."""
    from core.chat import _continue_attempts

    assert _continue_attempts() == 2  # Default = the previous 'nudge_used < 2'
    _set(**{"chat.continue_attempts": 0})
    assert _continue_attempts() == 0
    _set(**{"chat.continue_attempts": 5})
    assert _continue_attempts() == 5


def test_die_schranken_sind_im_payload(empty_ephe_home) -> None:
    """The client clamps before sending — it needs min/max/step from the server."""
    from core.settings_schema import deep_view

    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    for key in ("chat.tool_result_chars", "chat.continue_attempts"):
        entry = entries[key]
        assert entry["type"] == "number"
        assert entry["min"] < entry["default"] < entry["max"], key
        assert entry["step"] == 1, key
        assert entry["hint"] and entry["hintEn"], key


def test_ausserhalb_der_schranke_ist_kein_schreibfall(empty_ephe_home) -> None:
    with pytest.raises(ValueError):
        validate_sections({"chat": {"chat.tool_result_chars": 5}})
    with pytest.raises(ValueError):
        validate_sections({"chat": {"chat.continue_attempts": 9}})


def test_jede_auswahl_hat_einen_text_in_beiden_sprachen(empty_ephe_home) -> None:
    """A selection value must not be an English word in the German interface.

    The value stays the identifier (validation, persistence); what the user
    sees comes from `optionLabels` in the register. If a value is missing, the
    surface shows the bare identifier — exactly the language leak this field
    had until now."""
    from core.settings_hints import HINTS
    from core.settings_schema import SCHEMA, deep_view

    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    selects = [k for k, m in SCHEMA.items() if m["type"] == "select"]
    assert selects, "das Register kennt keine Auswahl-Felder — Test waere leer"
    for key in selects:
        options = SCHEMA[key]["options"]
        labels = SCHEMA[key].get("optionLabels")
        assert labels, f"{key}: Auswahl ohne Anzeige-Texte"
        assert set(labels) == set(options), f"{key}: Labels decken die Optionen nicht ab"
        for value, pair in labels.items():
            de, en = pair
            assert de and en and de != en, f"{key}/{value}"
            assert entries[key]["optionLabels"], f"{key}: deep_view reicht keine Texte durch"
        assert key in HINTS, f"{key}: Auswahl ohne Erklaerung"
