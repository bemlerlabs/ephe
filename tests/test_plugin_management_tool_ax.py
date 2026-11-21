"""The model-facing contract of `plugin_manager`: the sentence and the refusals.

The tool is read-only on purpose, and the description has to say so before a model tries
`action="install"`. Its three refusals are the three ways a read misses; each has to name
the code, the reason and the read that answers instead. The description and the parameter
sentences are pinned: a reworded sentence is a contract a model has to re-learn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools.plugin_manager import PLUGIN_MANAGER_SCHEMA, plugin_manager

DESCRIPTION = (
    "Read-only view of the installed plugins: the catalog and each bundle's capabilities, "
    "switch state and health. Actions: 'list' (whole portfolio and counts), 'search' "
    "(query matches name and description), 'inspect' (one plugin, its commands and its "
    "tools), 'health' (quarantine, missing dependencies, failed switches). Omit the action "
    "and it answers with 'list'. Use it to answer what is installed or why a plugin is off. "
    "Not for building or changing anything: it never installs, enables, disables, updates "
    'or removes, and refuses those with read_only. Example: plugin_manager(action="inspect",'
    ' name="documents")'
)

PARAMETERS = {
    "action": "Read action to run; defaults to 'list'.",
    "query": "Search text for action='search'; matches name and description.",
    "name": "Plugin id for action='inspect', from action='list'.",
}

NEXT_STEPS = {
    "read_only": (
        "Ask the user to change the plugin on Extensions, or run `ephe plugin enable <id>` "
        "from a shell."
    ),
    "invalid_request": "Pass name, one of the ids action='list' answers.",
    "unknown_plugin": "Run action='list' and use one of the names it answers.",
}


def _call(**kwargs) -> dict:
    return json.loads(plugin_manager(**kwargs))


@pytest.fixture()
def device(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_the_description_is_the_pinned_one() -> None:
    assert PLUGIN_MANAGER_SCHEMA["function"]["description"] == DESCRIPTION


def test_the_description_names_the_read_actions_and_the_refusal() -> None:
    """GIVEN the plugin_manager description
    WHEN a model reads it before calling
    THEN every action is named, and so is the fact that a mutation is refused."""
    description = PLUGIN_MANAGER_SCHEMA["function"]["description"]
    for action in ("list", "search", "inspect", "health"):
        assert f"'{action}'" in description, action
    for verb in ("installs", "enables", "disables", "updates", "removes"):
        assert verb in description, verb


def test_every_parameter_carries_the_pinned_description() -> None:
    properties = PLUGIN_MANAGER_SCHEMA["function"]["parameters"]["properties"]
    assert {key: properties[key]["description"] for key in properties} == PARAMETERS


def test_action_is_optional_with_a_declared_default() -> None:
    parameters = PLUGIN_MANAGER_SCHEMA["function"]["parameters"]
    assert "action" not in (parameters.get("required") or [])
    assert parameters["properties"]["action"]["default"] == "list"
    assert parameters["properties"]["action"]["enum"] == ["list", "search", "inspect", "health"]


@pytest.mark.parametrize("action", ["install", "enable", "disable", "update", "remove"])
def test_a_mutation_is_refused_with_the_move_left(device, action: str) -> None:
    """GIVEN a model that asks this tool to change a switch
    WHEN it answers
    THEN the answer is the read_only refusal, with the code and the step beside it."""
    answer = _call(action=action)

    assert answer["error"] == "read_only"
    assert str(answer["detail"]).strip()
    assert answer["next"] == NEXT_STEPS["read_only"]
    assert answer["allowed"] == ["list", "search", "inspect", "health"]


def test_inspect_without_a_name_names_the_read_that_has_one(device) -> None:
    answer = _call(action="inspect")

    assert answer["error"] == "invalid_request"
    assert answer["next"] == NEXT_STEPS["invalid_request"]


def test_an_unknown_plugin_names_the_read_that_lists_the_ids(device) -> None:
    answer = _call(action="inspect", name="not-installed")

    assert answer["error"] == "unknown_plugin"
    assert answer["next"] == NEXT_STEPS["unknown_plugin"]
    assert answer["name"] == "not-installed"
