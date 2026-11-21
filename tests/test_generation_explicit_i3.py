"""I3-8: "not set" is a state — the three sliders nobody used to read.

The generation block in engine.json displayed six values. Three of them reached
the engine (temperatur/top_p/max_tokens, I2-5), three were shop window:
tool_budget, context_window and memory_max_entries were read nowhere.

Pulling the first wire showed why nobody had read them: validate_generation filled
all six keys on save, and the register defaults contradict decided requirements —
tool_budget 10 against the 25 chat rounds since R46, an invented context window
against the model table, a memory cap against the env path. Hence: the write path
preserves absence, and consumers ask with read_generation_explicit(), which returns
only what somebody actually set.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from core import auto_memory
from core import engine_config as ec
from core.engine_config import GENERATION_BOUNDS, read_generation_explicit, validate_generation


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    for key in ec.GENERATION_ENV_KEYS.values():
        monkeypatch.delenv(key, raising=False)
    yield tmp_path


def _engine(tmp_path, generation: dict | None) -> None:
    """Write engine.json into the isolated folder (CONFIG_DIR is patched)."""
    body: dict = {"provider": "local_ollama", "model": "gemma4:12b",
                  "api_url": "http://127.0.0.1:11434"}
    if generation is not None:
        body["generation"] = generation
    pathlib.Path(tmp_path / "engine.json").write_text(json.dumps(body), encoding="utf-8")


# Write path: absence stays absence

def test_validate_no_longer_fills_missing_keys() -> None:
    assert validate_generation({"temperature": 0.4}) == {"temperature": 0.4}


def test_validate_empty_stays_empty() -> None:
    assert validate_generation({}) == {}
    assert validate_generation(None) == {}


def test_validate_rejects_values_outside_the_bounds() -> None:
    assert validate_generation({"tool_budget": 12}) == {"tool_budget": 12}
    with pytest.raises(ValueError):
        validate_generation({"tool_budget": 999})


# Read path: only what is set

def test_explicit_is_empty_without_any_setting(tmp_path) -> None:
    _engine(tmp_path, None)
    assert read_generation_explicit() == {}
    _engine(tmp_path, {})
    assert read_generation_explicit() == {}


def test_explicit_returns_only_the_key_that_was_set(tmp_path) -> None:
    _engine(tmp_path, {"tool_budget": 18})
    assert read_generation_explicit() == {"tool_budget": 18}


def test_env_wins_and_clamps_to_the_bound(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _engine(tmp_path, {"tool_budget": 18})
    monkeypatch.setenv("EPHE_TOOL_BUDGET", "4000")
    assert read_generation_explicit() == {"tool_budget": GENERATION_BOUNDS["tool_budget"][2]}


def test_junk_values_in_the_file_are_ignored(tmp_path) -> None:
    _engine(tmp_path, {"context_window": "breit", "max_tokens": float("nan")})
    assert read_generation_explicit() == {}


def test_read_generation_values_still_delivers_every_key(tmp_path) -> None:
    """read_generation_values still delivers the full active state — the
    card needs it. The only new part is that it no longer erases the absence."""
    _engine(tmp_path, {"tool_budget": 18})
    values = ec.read_generation_values()
    assert set(values) == set(GENERATION_BOUNDS)
    assert values["tool_budget"] == 18


# Consumer 1: task rounds

class _Skill:
    def __init__(self, trigger: str) -> None:
        self.trigger = trigger


def test_tool_round_budget_follows_the_precedence(tmp_path) -> None:
    from server.routes.chat import _max_tool_iterations

    _engine(tmp_path, {"tool_budget": 30})
    assert _max_tool_iterations(7, _Skill("/ephe")) == 7       # the request wins
    assert _max_tool_iterations(None, _Skill("/ephe")) == 40   # coding class at its cap
    assert _max_tool_iterations(None, _Skill("/xlsx")) == 30   # slider, because it is set
    _engine(tmp_path, None)
    assert _max_tool_iterations(None, None) is None            # -> core default 25


# Consumer 2: context window

def test_context_window_without_a_setting_uses_the_table(tmp_path) -> None:
    from core.chat import _active_context_window
    from core.model_config import resolve_context_window

    _engine(tmp_path, None)
    assert _active_context_window("gemma4:12b") == resolve_context_window("gemma4:12b")[0]


def test_context_window_with_a_setting_takes_the_slider(tmp_path) -> None:
    from core.chat import _active_context_window

    _engine(tmp_path, {"context_window": 200_000})
    assert _active_context_window("gemma4:12b") == 200_000


# Consumer 3: memory cap

def test_memory_cap_without_a_setting_keeps_the_old_value(tmp_path) -> None:
    _engine(tmp_path, None)
    assert auto_memory._max_entries() == auto_memory._DEFAULT_MAX_ENTRIES


def test_memory_cap_with_a_setting_listens_to_the_slider(tmp_path) -> None:
    _engine(tmp_path, {"memory_max_entries": 250})
    assert auto_memory._max_entries() == 250


def test_memory_cap_env_path_stays_untouched(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _engine(tmp_path, None)
    monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "77")
    assert auto_memory._max_entries() == 77
    monkeypatch.setenv("EPHE_MEMORY_MAX_ENTRIES", "quatsch")
    assert auto_memory._max_entries() == auto_memory._DEFAULT_MAX_ENTRIES
