"""The first run answers the egress switch with off, until a person answers it.

The tour's switch step reads GET /api/plugins. On a fresh device the "Live web
research (needs a key)" row came up ON — in a local-first product, with a key the
device does not have — because the store view presented the lifecycle's
no-record default as the switch position (tests/test_n22_first_start_no_fetch.py
is the same rule for the fetch itself). The curated catalogue declares each
plugin's default (plugin-catalog.json: web-research is opt-in); the store view
consults that declaration for a switch the device never recorded, and any
recorded answer wins over it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CATALOG = Path(__file__).resolve().parent.parent / "plugin-catalog.json"


@pytest.fixture()
def fresh_device(tmp_path, monkeypatch):
    """A device folder nothing has answered yet: no engine, no switch records."""
    import core.engine_config as ec

    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    # CONFIG_DIR is bound at import; the env alone would leave the constant on
    # the real device folder (the same seam tests/conftest.empty_ephe_home patches).
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg, raising=False)
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield cfg
    plugin_runtime.invalidate_ownership_cache()


def _entry(view: dict, name: str) -> dict:
    return next(e for e in view["public"] if e["id"] == name)


def test_a_fresh_device_reports_web_research_off(fresh_device) -> None:
    from core import plugin_store

    view = plugin_store.plugins_view()
    assert _entry(view, "web-research")["enabled"] is False
    # Only the declared egress default flips: a local plugin keeps its ON unless
    # the catalogue says otherwise, so nothing else changes its switch position.
    assert _entry(view, "documents")["enabled"] is True


def test_a_recorded_answer_beats_the_declared_default(fresh_device) -> None:
    from core import plugin_runtime, plugin_store

    plugin_runtime.lifecycle().set_enabled(
        "web-research", True, actor="test", reason="the person turned it on"
    )
    assert _entry(plugin_store.plugins_view(), "web-research")["enabled"] is True

    plugin_runtime.lifecycle().set_enabled(
        "web-research", False, actor="test", reason="and off again"
    )
    assert _entry(plugin_store.plugins_view(), "web-research")["enabled"] is False


def test_the_shipped_catalogue_declares_web_research_opt_in() -> None:
    """The entry's own sentence and its default must agree (defect 5's quote)."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    entry = next(e for e in catalog["public"] if e["name"] == "web-research")
    assert entry["enabled"] is False
    assert "opt-in" in entry["description"]
