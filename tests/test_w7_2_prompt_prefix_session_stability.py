"""W7-2 - the assembled prompt prefix is byte-stable across a session.

The plugin filter used to run only on the cache-miss path of
``get_tool_schemas()``. From the second turn of a session onward the
tool-guidelines block therefore carried a disabled plugin's tool names, the
front of the system prompt changed between turns, and the engine's prefix cache
missed on every turn. The fix that landed for that leak moved the filter onto
both return paths.

The measurement here is the property the fix restored. A session is a loop of
turns whose inputs do not change; the counter is the length of the byte prefix
two turns share, compared against the full prompt length. The job is to prove
stability across the session, not to hunt for a new source of drift, so the
only variation in play is the one the fix addressed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_store import REGISTRY_FILENAME

# A session covers many turns, well past the two a spot check would pick.
SESSION_TURNS = 24


class _FrozenClock:
    """A clock pinned to one instant so the daily date block cannot rotate mid-test."""

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def _assemble() -> str:
    from core.chat_prompt import assemble_system_prompt

    return assemble_system_prompt(model="test-model")


def _session(turns: int) -> list[str]:
    """Assemble ``turns`` prompts back to back with every input left unchanged."""
    return [_assemble() for _ in range(turns)]


def _byte_len(text: str) -> int:
    """The prompt's size in bytes, the unit the engine's prefix cache counts."""
    return len(text.encode("utf-8"))


def _shared_prefix_len(a: str, b: str) -> int:
    """The counter: how many leading bytes ``a`` and ``b`` have in common."""
    left, right = a.encode("utf-8"), b.encode("utf-8")
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _guideline_tool_names(prompt: str, known: set[str]) -> set[str]:
    """Tool names the tool-guidelines block lists, taken from the prompt text.

    Only tokens that are also advertised schemas survive, so the wording of the
    surrounding guidance cannot masquerade as a tool name.
    """
    marker = "Tools & Capabilities:"
    assert marker in prompt, "the tool-guidelines block is missing from the prompt"
    block = prompt.split(marker, 1)[1].split("\n\n", 1)[0]
    names: set[str] = set()
    for line in block.splitlines():
        _head, sep, tail = line.rpartition(":")
        if not sep:
            continue
        names.update(name.strip().rstrip(".") for name in tail.split(",") if name.strip())
    return names & known


@pytest.fixture()
def gated_home(tmp_path, monkeypatch, request):
    """A hermetic home with one plugin family disabled and a cold schema cache.

    The disabled family is what lets the plugin filter bite. With the family on,
    both return paths of ``get_tool_schemas()`` produce the same list and a leak
    on the cache-hit path would be invisible, so the stability the tests prove
    would be empty. The family and its tools are read from the catalog, never
    pinned as literals.
    """
    from core.plugin_runtime import CATALOG_TOOL_FAMILIES
    from core.tools import registry
    from core.tools._schemas import BASE_TOOL_SCHEMAS

    advertised = {entry.get("function", {}).get("name", "") for entry in BASE_TOOL_SCHEMAS}
    catalog = [
        (plugin_id, sorted(family["tools"]))
        for plugin_id, family in CATALOG_TOOL_FAMILIES.items()
        if family.get("tools") and set(family["tools"]) & advertised
    ]
    assert catalog, "no catalog family gates a tool the registry advertises"
    plugin_id, gated_tools = catalog[0]

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(home / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setattr("core.persona._dt_now", _FrozenClock)
    (home / REGISTRY_FILENAME).write_text(
        json.dumps({"plugins": [{"name": plugin_id, "enabled": False}]}),
        encoding="utf-8",
    )

    registry.invalidate_tool_schema_cache()
    request.addfinalizer(registry.invalidate_tool_schema_cache)
    return {"plugin_id": plugin_id, "gated_tools": gated_tools, "advertised": advertised}


def test_the_prefix_is_byte_identical_across_a_session(gated_home):
    """Over a session of many turns the assembled prompt never changes its bytes.

    Turn one is the cold-cache call; every later turn is a cache hit. The
    counter has to reach the full prompt length on every turn, or two turns
    diverged and the engine's prefix cache would miss.
    """
    turns = _session(SESSION_TURNS)
    assert len(turns) == SESSION_TURNS  # the counter saw the whole session

    first = turns[0]
    width = _byte_len(first)
    for index, turn in enumerate(turns):
        shared = _shared_prefix_len(first, turn)
        assert shared == width, f"turn {index} shares only {shared} of {width} bytes"

    placed = sorted(set(gated_home["gated_tools"]) & gated_home["advertised"])
    assert placed, "the disabled family gates nothing the registry advertises"
    for turn in turns:
        listed = _guideline_tool_names(turn, gated_home["advertised"])
        assert set(placed) & listed == set(), "a disabled tool reached the prompt"


def test_the_session_crosses_the_cold_then_warm_path(gated_home, monkeypatch):
    """The session really walks both return paths of ``get_tool_schemas()``.

    If every call were a cache miss, the stability above would say nothing about
    the hit path the fix repaired. The proxy counts the cold calls: the first
    turn opens the window, every later turn reads it.
    """
    from core.tools import registry

    real = registry.get_tool_schemas
    cold: list[bool] = []

    def counting():
        cold.append(registry._TOOL_SCHEMA_CACHE is None)
        return real()

    monkeypatch.setattr(registry, "get_tool_schemas", counting)
    _session(SESSION_TURNS)

    assert len(cold) == SESSION_TURNS
    assert cold[0] is True, "the first turn was not a cache miss"
    assert not any(cold[1:]), "a later turn missed the cache, so the hit path was never read"


def test_the_counter_catches_a_hit_path_that_skips_the_filter(gated_home, monkeypatch):
    """The regression the fix removed reappears here as a broken prefix.

    The proxy restores the old cache-hit early return: the raw cached list
    without the plugin filter. The banned names come back in the tool
    guidelines from the second turn, so the same counter that reached the full
    length above stops short - the guard bites.
    """
    from core.tools import registry

    real = registry.get_tool_schemas
    calls = {"n": 0}
    placed = sorted(set(gated_home["gated_tools"]) & gated_home["advertised"])
    assert placed, "the disabled family gates nothing the registry advertises"

    def pre_fix():
        calls["n"] += 1
        filtered = real()
        if calls["n"] == 1:
            return filtered
        cached = registry._TOOL_SCHEMA_CACHE
        return list(cached[1]) if cached else filtered

    monkeypatch.setattr(registry, "get_tool_schemas", pre_fix)
    turns = _session(4)

    known = gated_home["advertised"]
    assert set(placed) & _guideline_tool_names(turns[0], known) == set()
    leaked = set(placed) & _guideline_tool_names(turns[1], known)
    assert leaked, "the unfiltered hit path did not surface the disabled tool"
    assert turns[0] != turns[1]
    assert _shared_prefix_len(turns[0], turns[1]) < _byte_len(turns[0])
