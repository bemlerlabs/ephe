"""An engine choice either names its endpoint or is not written at all.

On 2026-10-31 a model switch persisted `openai_compatible` with `api_url: null`
into the user's engine.json. The product's start rule treats that as no choice,
so every surface opened its setup although a key and a working endpoint were on
disk. The helper now keeps the URL a caller did not pass and refuses to create a
half config.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    from core import engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "cfg")
    engine_config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return engine_config.CONFIG_DIR


def _stored(config_dir):
    path = config_dir / "engine.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def test_a_model_switch_keeps_the_endpoint_it_was_reached_at(config_dir) -> None:
    from core.engine_config import EngineChoice, persist_engine_choice, save_engine_config

    save_engine_config(
        EngineChoice(
            provider="openai_compatible",
            model="first-model",
            api_url="https://engine.example/v1",
        )
    )
    assert persist_engine_choice("openai_compatible", "second-model", None) is True

    stored = _stored(config_dir)
    assert stored["model"] == "second-model"
    assert stored["api_url"] == "https://engine.example/v1"


def test_a_remote_choice_without_any_endpoint_is_not_written(config_dir) -> None:
    from core.engine_config import persist_engine_choice

    assert persist_engine_choice("openai_compatible", "model", None) is False
    assert _stored(config_dir) is None


def test_a_local_choice_carries_no_endpoint(config_dir) -> None:
    from core.engine_config import persist_engine_choice

    assert persist_engine_choice("local_ollama", "tag", None) is True
    assert _stored(config_dir)["api_url"] is None
