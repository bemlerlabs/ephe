"""The setup surface's port hints are keyed, the way the reader's refusals are.

`docs/SERVER_SURFACE_LANGUAGE_DECISION_2026-10-09.md` §6, second slice: six
`_ENGINE_PORTS` sentences reached two surfaces that worked around their language
instead of translating them. The code is the contract, the sentence stays what an
old client and the log read.

Checked against the shipped bundles here, because a composed key
(`setup.portHint.${code}`) is outside the static `t()` lint in
`app/src/lib/i18n-keys.test.ts` — nothing else would notice an entry missing on one
side, or a German copy that stopped matching the server's line.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from server.routes.settings import _ENGINE_PORTS, _VLLM_STD_PORTS, _port_hint

LOCALE_DIR = Path(__file__).resolve().parents[1] / "app" / "src" / "locales"
BUNDLES = {
    lng: json.loads((LOCALE_DIR / f"{lng}.json").read_text(encoding="utf-8"))["setup"]["portHint"]
    for lng in ("de", "en")
}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

#: code -> the sentence the server sends beside it, for the ports that say something.
TABLE = {code: hint for _port, code, hint in _ENGINE_PORTS if code}


def test_every_statement_carries_a_code_and_a_sentence():
    assert TABLE, "an empty port table would make this gate vacuous"
    for port, code, hint in _ENGINE_PORTS:
        assert bool(code) == bool(hint), f"{port} carries half a contract"
        assert code == code.strip().lower(), f"{port}: {code!r} is not a key-shaped code"
        assert not PLACEHOLDER.search(hint), f"{port}: {hint!r} interpolates, none of these do"


def test_both_bundles_hold_an_entry_for_every_code():
    for lng, bundle in BUNDLES.items():
        assert set(bundle) == set(TABLE), f"{lng}.json/setup.portHint has drifted"


def test_the_english_copy_is_a_translation_and_not_the_servers_line():
    for code, hint in TABLE.items():
        english = BUNDLES["en"][code]
        assert english and english != hint, code
        assert english == english.strip(), f"{code}: the line is interpolated mid-sentence"


def test_the_german_entry_is_the_servers_sentence():
    for code, hint in TABLE.items():
        assert BUNDLES["de"][code] == hint, code


def test_a_port_that_says_nothing_emits_neither_code_nor_hint():
    silent = [port for port, code, hint in _ENGINE_PORTS if not code]
    assert silent, "the table lost its no-statement port, so this case is no longer reachable"
    for port in silent:
        assert _port_hint(port) == ("", "")
    assert _port_hint(None) == ("", "")
    assert _port_hint("65535") == ("", "")


def test_the_sibling_fallback_and_the_sweep_read_the_same_table():
    """One list for both paths — 8888 living in only one of them was the original bug."""
    for port, code, hint in _ENGINE_PORTS:
        assert _port_hint(port) == (code, hint)
        assert _port_hint(str(port)) == (code, hint)
    assert {str(port) for port, _code, _hint in _ENGINE_PORTS} == set(_VLLM_STD_PORTS)
