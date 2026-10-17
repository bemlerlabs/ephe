"""The generation registry's coherence contract.

Four registers describe the generation block: GENERATION_BOUNDS with
GENERATION_ENV_KEYS hold the numeric keys; GENERATION_OPTION_NORMALIZERS with
GENERATION_OPTION_ENV_KEYS hold the non-numeric options (thinking,
reasoning_effort). Every reader indexes one register by a key of the other — the
env name is looked up from the same key that names the bounds or the normalizer —
and validate_generation walks both registers into one persisted block. So a key
added to one register alone turns a read into a KeyError, a key placed in both is
written twice, and a repeated env name makes two keys read one variable.

core/engine_config.generation_registry_inconsistencies() is the check and raises at
import on any drift. These tests pin the shipped registers AND prove the check still
reports each drift class when one is injected, so an always-empty function cannot
pass as a guard.
"""
from __future__ import annotations

import pytest

from core import engine_config as ec


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """engine.json is read from a temp folder, so the shipped config never leaks in."""
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    yield tmp_path


# The shipped registers line up

def test_the_shipped_registry_is_coherent() -> None:
    assert ec.generation_registry_inconsistencies() == []
    assert ec._coherence_problems == []


def test_numeric_keys_and_env_names_pair_up() -> None:
    assert set(ec.GENERATION_BOUNDS) == set(ec.GENERATION_ENV_KEYS)


def test_option_keys_and_env_names_pair_up() -> None:
    assert set(ec.GENERATION_OPTION_NORMALIZERS) == set(ec.GENERATION_OPTION_ENV_KEYS)


def test_the_two_registers_share_no_key() -> None:
    assert set(ec.GENERATION_BOUNDS).isdisjoint(ec.GENERATION_OPTION_NORMALIZERS)


def test_env_names_follow_the_key_and_are_unique() -> None:
    pairs = list(ec.GENERATION_ENV_KEYS.items()) + list(ec.GENERATION_OPTION_ENV_KEYS.items())
    for key, env_name in pairs:
        assert env_name == f"EPHE_{key.upper()}", key
    names = [env_name for _key, env_name in pairs]
    assert len(names) == len(set(names))


# The readers agree with the registers

def test_each_reader_covers_exactly_its_register() -> None:
    assert set(ec.read_generation_values()) == set(ec.GENERATION_BOUNDS)
    assert set(ec.read_generation_options()) == set(ec.GENERATION_OPTION_NORMALIZERS)
    assert set(ec.read_generation_explicit()) <= set(ec.GENERATION_BOUNDS)


def test_the_writer_carries_every_register_key() -> None:
    raw: dict[str, object] = {
        key: low for key, (_default, low, _high) in ec.GENERATION_BOUNDS.items()
    }
    raw["thinking"] = {"type": "disabled"}
    raw["reasoning_effort"] = "low"
    expected = set(ec.GENERATION_BOUNDS) | set(ec.GENERATION_OPTION_NORMALIZERS)
    assert set(ec.validate_generation(raw)) == expected


def test_every_option_key_reaches_the_request_builder() -> None:
    """The request path (core/model_provider) speaks the option register's keys."""
    from core import model_provider as mp

    sample = {"thinking": {"type": "disabled"}, "reasoning_effort": "high"}
    for key in ec.GENERATION_OPTION_NORMALIZERS:
        assert mp.thinking_request_fields({key: sample[key]}, "http://host:8000/v1"), key


# The check still fires when a register drifts

def test_check_reports_a_key_without_its_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ec, "GENERATION_ENV_KEYS", {k: v for k, v in ec.GENERATION_ENV_KEYS.items() if k != "temperature"})
    assert any("temperature" in problem for problem in ec.generation_registry_inconsistencies())


def test_check_reports_an_env_name_without_its_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ec, "GENERATION_ENV_KEYS", {**ec.GENERATION_ENV_KEYS, "ghost": "EPHE_GHOST"})
    assert any("ghost" in problem for problem in ec.generation_registry_inconsistencies())


def test_check_reports_a_key_in_both_registers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ec, "GENERATION_OPTION_NORMALIZERS",
        {**ec.GENERATION_OPTION_NORMALIZERS, "temperature": ec.normalize_reasoning_effort},
    )
    assert any("both registers" in problem for problem in ec.generation_registry_inconsistencies())


def test_check_reports_a_repeated_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ec, "GENERATION_OPTION_ENV_KEYS",
        {**ec.GENERATION_OPTION_ENV_KEYS, "reasoning_effort": "EPHE_THINKING"},
    )
    assert any("EPHE_THINKING" in problem for problem in ec.generation_registry_inconsistencies())
