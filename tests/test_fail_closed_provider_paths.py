"""WH-51 fail-closed audit: no provider path invents a model.

Owner decision 2026-10-11 (D2, ``test_no_default_local_model.py``): the product
names no model on the user's behalf. The one accepted exception is the neutral
placeholder ``"custom-model"`` — it names no model of ours and lives only on the
two TEMPLATE surfaces (the engine-picker listing and the onboarding seed shown
when an engine stays silent), both pinned by their own tests.

Every path that fixes an ACTIVE choice must therefore either carry the tag the
user gave or refuse:

  env resolution   core/engine_config.engine_choice_from_env
                   core/model_provider._provider_from_env
  persisted file   core/engine_config.load_engine_config (damaged/empty -> None)
  session override core/model_provider.set_active_provider
  persistence      core/engine_config.persist_engine_choice
  call sites       core/model_provider.chosen_model

These pins are the audit's executable half; ``docs/FAIL_CLOSED_PROVIDER_AUDIT.md``
is the written half. The scan reads the shipped sources.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core import engine_config as ec
from core import model_provider as mp

ROOT = Path(__file__).resolve().parents[1]

#: A real, installable tag as the shipped-default scans define it. The neutral
#: placeholder must not match; a vendor tag must.
MODEL_TAG = re.compile(
    r"\b(?:gemma|qwen|llama|mistral|minicpm|phi|deepseek|codellama|ds)[a-z0-9._-]*:[a-z0-9._-]+",
    re.IGNORECASE,
)


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirect engine.json (and its dir) into a temp tree — never the owner's."""
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path / "config")
    return tmp_path / "config" / "engine.json"


# Env resolution: the same refusal for the same missing variable.

@pytest.mark.parametrize(
    ("provider", "base_env", "missing_var"),
    [
        ("local_ollama", {}, "EPHE_MODEL"),
        ("custom_ollama", {"EPHE_CUSTOM_OLLAMA_BASE_URL": "http://10.0.0.9:11434"}, "EPHE_MODEL"),
        (
            "openai_compatible",
            {"EPHE_OPENAI_COMPAT_BASE_URL": "https://api.example.test/v1"},
            "EPHE_OPENAI_COMPAT_MODEL",
        ),
    ],
)
def test_engine_config_env_refuses_without_a_model(monkeypatch, provider, base_env, missing_var):
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", provider)
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL", raising=False)
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ec.EngineNotConfigured) as exc:
        ec.engine_choice_from_env()
    assert missing_var in str(exc.value)


@pytest.mark.parametrize(
    ("provider", "base_env", "missing_var"),
    [
        ("custom_ollama", {"EPHE_CUSTOM_OLLAMA_BASE_URL": "http://10.0.0.9:11434"}, "EPHE_MODEL"),
        (
            "openai_compatible",
            {"EPHE_OPENAI_COMPAT_BASE_URL": "https://api.example.test/v1"},
            "EPHE_OPENAI_COMPAT_MODEL",
        ),
    ],
)
def test_model_provider_env_refuses_without_a_model(monkeypatch, provider, base_env, missing_var):
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", provider)
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL", raising=False)
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(mp.EngineNotConfigured) as exc:
        mp.get_active_provider()
    assert missing_var in str(exc.value)


def test_fully_unconfigured_local_reports_empty_not_a_default(monkeypatch):
    """Nothing chosen at all stays the honest empty state."""
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)

    active = mp.get_active_provider()
    assert active.provider == "local_ollama"
    assert active.model == ""


# Persisted file: a damaged or model-less engine.json is no choice at all.

def test_persisted_config_without_a_model_loads_as_none(isolated_config):
    isolated_config.parent.mkdir(parents=True, exist_ok=True)
    isolated_config.write_text(
        json.dumps({"provider": "openai_compatible", "api_url": "https://api.example.test/v1"}),
        encoding="utf-8",
    )
    assert ec.load_engine_config() is None


def test_persisted_config_with_an_empty_model_loads_as_none(isolated_config):
    isolated_config.parent.mkdir(parents=True, exist_ok=True)
    isolated_config.write_text(
        json.dumps({"provider": "local_ollama", "model": "   "}),
        encoding="utf-8",
    )
    assert ec.load_engine_config() is None


def test_engine_choice_rejects_an_empty_model_and_an_unknown_provider():
    with pytest.raises(ValueError):
        ec.EngineChoice(provider="local_ollama", model="  ")
    with pytest.raises(ValueError):
        ec.EngineChoice(provider="bogus_engine", model="mine:work")


# Resolver: no config, no env, no prompt aborts with the instruction.

def test_resolver_aborts_without_config_or_env(isolated_config, monkeypatch):
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)

    with pytest.raises(ec.EngineNotConfigured) as exc:
        ec.resolve_engine_choice(isolated_config, allow_prompt=False)
    assert "ephe configure" in exc.value.hint


# Session override: the active choice carries the tag it was given.

@pytest.mark.parametrize("model", [None, "", "   "])
def test_session_override_invents_no_placeholder_model(monkeypatch, model):
    """The leak this audit closed: a model-less openai_compatible switch used to
    report, and persist, the placeholder ``"custom-model"`` as the active model.
    """
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)

    config = mp.set_active_provider(
        provider="openai_compatible", model=model, base_url="http://engine.test:8000/v1"
    )
    assert config.model == ""
    assert mp.get_active_provider().model == ""


@pytest.mark.parametrize("provider", ["local_ollama", "custom_ollama", "openai_compatible"])
def test_session_override_keeps_the_tag_for_every_engine_class(monkeypatch, provider):
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)
    config = mp.set_active_provider(provider=provider, model="mine:chosen", base_url="http://h:1")
    assert config.model == "mine:chosen"


# Persistence boundary: a model-less choice never reaches disk.

def test_model_less_choice_is_not_persistable(isolated_config, monkeypatch):
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)

    with pytest.raises(ValueError):
        ec.persist_engine_choice("openai_compatible", "", "http://engine.test:8000/v1")
    assert not isolated_config.exists()


# Call sites: chosen_model refuses rather than send an empty tag.

def test_chosen_model_refuses_when_nothing_is_named(monkeypatch):
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)

    with pytest.raises(ec.EngineNotConfigured):
        mp.chosen_model("the vision call")


# Template surfaces: the placeholder is the only literal, and it names no model.

def test_listing_placeholder_names_no_real_model():
    options = {o["provider"]: o["model"] for o in mp.list_provider_options()}
    assert options["local_ollama"] == ""
    assert options["custom_ollama"] == ""
    # Owner-accepted neutral placeholder on the picker surface, carrying no model
    # of ours (else it becomes a shipped default the D2 scan hunts).
    assert not MODEL_TAG.search(options["openai_compatible"])


def test_build_engine_provider_invents_no_model():
    assert mp.build_engine_provider("http://engine.test:8000/v1", "").model == ""
    assert mp.build_engine_provider("http://engine.test:8000/v1", "mine:work").model == "mine:work"


# The written audit's path table stays honest: every ACTIVE path is listed.

def test_audit_report_covers_every_provider_surface():
    report = ROOT / "docs" / "FAIL_CLOSED_PROVIDER_AUDIT.md"
    if not report.is_file():
        # The audit is a workshop document; the published tree keeps the pins that hold the
        # behaviour, not the prose that writes the decision down.
        pytest.skip("the written audit is not carried by this tree")
    text = report.read_text(encoding="utf-8")
    for surface in (
        "engine_choice_from_env",
        "_provider_from_env",
        "load_engine_config",
        "resolve_engine_choice",
        "set_active_provider",
        "persist_engine_choice",
        "chosen_model",
        "ensure_provider_ready",
    ):
        assert surface in text, f"{surface} missing from the audit table"
