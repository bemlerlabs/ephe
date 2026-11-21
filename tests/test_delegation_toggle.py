"""◑ Ephe · TDD — delegation is a control the user can switch in Settings.

The main agent's spawn_agent tool was always offered. The owner wants the agent
team activatable like a plugin: a deep-settings boolean gates whether the tool
is offered to the model. The default stays on, so an installation that sets
nothing keeps the behaviour it had; switching it off withdraws the tool.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))


def _names() -> list[str]:
    from core.tools.registry import get_tool_schemas

    return [s["function"]["name"] for s in get_tool_schemas()]


def _set(monkeypatch, value: bool) -> None:
    import core.settings_schema as ss

    monkeypatch.setattr(
        ss, "load_deep_settings", lambda: {"advanced": {"advanced.agent_team_enabled": value}}
    )


def test_the_default_still_offers_delegation():
    """GIVEN no setting WHEN the schemas are built THEN spawn_agent is offered."""
    assert "spawn_agent" in _names()


def test_switching_it_off_withdraws_the_delegation_tool(monkeypatch):
    """GIVEN the control off WHEN the schemas are built THEN spawn_agent is gone."""
    _set(monkeypatch, False)
    assert "spawn_agent" not in _names()


def test_switching_it_on_offers_delegation(monkeypatch):
    """GIVEN the control on WHEN the schemas are built THEN spawn_agent is offered."""
    _set(monkeypatch, True)
    assert "spawn_agent" in _names()