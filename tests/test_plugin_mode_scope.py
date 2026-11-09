"""The session scope of a plugin has one resolution point.

A mode names plugins only through the table in ``core.plugin_scope``. The
committed enabled bit stays what the lifecycle stored. Pause-all outranks a
global switch and a preset alike.
"""
from __future__ import annotations

import json

from core.plugin_scope import MODE_PLUGINS, MODES, describe, resolve


def test_the_shipped_table_names_no_plugin() -> None:
    assert set(MODE_PLUGINS) == set(MODES)
    assert all(len(names) == 0 for names in MODE_PLUGINS.values())


def test_a_globally_enabled_plugin_is_in_effect_for_that_reason() -> None:
    stored = {"enabled": True}
    decision = resolve(
        "web-research",
        enabled=stored["enabled"],
        pause_all=False,
        mode="operator",
    )
    assert decision.in_effect is True
    assert decision.reason == "global"
    assert decision.mode == "operator"
    assert stored == {"enabled": True}


def test_a_globally_off_plugin_a_mode_names_is_in_effect_via_preset() -> None:
    stored = {"enabled": False, "pause_all": False}
    blob = json.dumps(stored)
    mapping = {mode: frozenset() for mode in MODES}
    mapping["operator"] = frozenset({"web-research"})
    decision = resolve(
        "web-research",
        enabled=stored["enabled"],
        pause_all=stored["pause_all"],
        mode="operator",
        mapping=mapping,
    )
    assert decision.in_effect is True
    assert decision.reason == "preset"
    assert json.dumps(stored) == blob


def test_a_plugin_no_mode_names_stays_off_when_the_global_switch_is_off() -> None:
    decision = resolve(
        "web-research",
        enabled=False,
        pause_all=False,
        mode="operator",
        mapping={mode: frozenset() for mode in MODES},
    )
    assert decision.in_effect is False
    assert decision.reason == "off"


def test_pause_all_outranks_a_global_switch_and_a_preset() -> None:
    mapping = {mode: frozenset() for mode in MODES}
    mapping["operator"] = frozenset({"web-research"})
    decision = resolve(
        "web-research",
        enabled=True,
        pause_all=True,
        mode="operator",
        mapping=mapping,
    )
    assert decision.in_effect is False
    assert decision.reason == "paused"


def test_a_legacy_spelling_uses_the_renamed_mode_and_edit_auto_composes_nothing() -> None:
    mapping = {mode: frozenset() for mode in MODES}
    mapping["analyst"] = frozenset({"web-research"})
    asked = resolve(
        "web-research",
        enabled=False,
        pause_all=False,
        mode="ask",
        mapping=mapping,
    )
    assert asked.reason == "preset"
    assert asked.mode == "analyst"
    opened = resolve(
        "web-research",
        enabled=False,
        pause_all=False,
        mode="full-access",
        mapping={"operator": frozenset({"web-research"})},
    )
    assert opened.reason == "preset"
    assert opened.mode == "operator"
    retired = resolve(
        "web-research",
        enabled=False,
        pause_all=False,
        mode="edit-auto",
        mapping={"operator": frozenset({"web-research"})},
    )
    assert retired.in_effect is False
    assert retired.reason == "off"
    assert retired.mode == ""
    blank = resolve(
        "web-research",
        enabled=False,
        pause_all=False,
        mode="",
        mapping={"operator": frozenset({"web-research"})},
    )
    assert blank.reason == "off"
    assert blank.mode == ""


def test_the_read_fact_names_scope_without_rewriting_the_committed_bit() -> None:
    mapping = {mode: frozenset() for mode in MODES}
    mapping["creator"] = frozenset({"voice"})
    fact = describe(
        "voice",
        enabled=False,
        pause_all=False,
        mode="creator",
        mapping=mapping,
    )
    assert fact["enabled"] is False
    assert fact["scope"] == "session"
    assert fact["provided_by_modes"] == ["creator"]
    assert fact["reason"] == "preset"
    assert fact["in_effect"] is True
    quiet = describe(
        "documents",
        enabled=False,
        pause_all=False,
        mode="creator",
        mapping=mapping,
    )
    assert quiet["scope"] == "global"
    assert quiet["provided_by_modes"] == []
    assert quiet["reason"] == "off"
