"""
W18-DoD (replaces the P0-2-DoD that made a DGX-served Qwen the default engine).

There is no silent engine default any more. The engine choice belongs to the
user (engine.json through `ephe configure` or an explicit engine env). DGX Spark /
vLLM stay first-class - as a **preset/template**, not as a hardcoded
default (no private hostname, no key literal in the code).

Test rules:
- Deterministic (no AI requests, no network).
- Evidence: default constants removed, preset present, persistence unchanged.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.engine_config import (
    ENGINE_PRESETS,
    CUSTOM_OLLAMA,
    LOCAL_OLLAMA,
    OPENAI_COMPAT,
    EngineChoice,
    engine_preset,
    load_engine_config,
    resolve_engine_choice,
    save_engine_config,
)


# No hardcoded default left (W18/A3)

def test_no_hardcoded_dgx_constants_exist():
    """The private hostname and the key default have vanished from the module."""
    import core.engine_config as ec

    for gone in (
        "DEFAULT_DGX_SPARK_URL",
        "DEFAULT_DGX_SPARK_MODEL",
        "DEFAULT_DGX_SPARK_API_KEY",
        "DEFAULT_DGX_MODEL",
        "default_engine_choice",
        "is_default_dgx_spark",
    ):
        assert not hasattr(ec, gone), f"{gone} must be gone (no silent default)"


def test_no_tailnet_host_or_key_literal_in_source():
    """Source gate: the engine module holds no tailnet host and no key literal.

    The forbidden host is not spelled out. A test that names the host it forbids
    is how the host reaches the repository in the first place, and the property
    is the same either way: a host of the owner's never sits in engine defaults.
    """
    src = Path(__file__).resolve().parents[1] / "core" / "engine_config.py"
    text = src.read_text(encoding="utf-8")
    assert ".ts.net" not in text, "a tailnet host sits in the engine module"
    assert not re.search(
        r"(?i)\b(api[_-]?key|secret|token)\b\s*[:=]\s*[\"'][A-Za-z0-9+/_\-]{20,}[\"']", text
    ), "a key literal sits in the engine module"


# A preset instead of a default: DGX Spark / vLLM is selectable and named

def test_engine_presets_include_dgx_spark_vllm_openai_compat():
    preset = engine_preset("dgx_spark_vllm")
    assert preset is not None, "the onboarding preset for a DGX Spark / vLLM endpoint is missing"
    assert preset.provider == OPENAI_COMPAT
    assert "DGX Spark / vLLM" in preset.label
    assert "OpenAI-compatible" in preset.label
    # The example URL is a neutral placeholder, never a real host.
    assert "host" in preset.example_url or "example" in preset.example_url
    assert "ts.net" not in preset.example_url


def test_engine_presets_cover_all_providers():
    providers = {p.provider for p in ENGINE_PRESETS}
    assert providers == {LOCAL_OLLAMA, CUSTOM_OLLAMA, OPENAI_COMPAT}


def test_engine_preset_labels_are_english():
    """The labels were the `[1]`/`[2]`/`[3]` menu text of the onboarding before it was
    translated; onboarding now prints its own English options and reads only the preset's
    example_url/seed, so the values sat unreferenced and hid a German source."""
    labels = {p.id: p.label for p in ENGINE_PRESETS}
    assert labels[LOCAL_OLLAMA] == "Local Ollama (this machine)"
    assert labels[CUSTOM_OLLAMA] == "Your own Ollama / vLLM (remote URL)"
    assert labels["dgx_spark_vllm"] == "Your own OpenAI-compatible endpoint (DGX Spark / vLLM)"


def test_preset_seed_comes_from_env_not_code(monkeypatch):
    """The preset suggestion may arrive through the env (the user's machine) —
    the code itself knows no host."""
    preset = engine_preset("dgx_spark_vllm")
    assert preset is not None
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://10.1.2.3:8000/v1")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", "my-served-model")
    assert preset.seed_url() == "http://10.1.2.3:8000/v1"
    assert preset.seed_model() == "my-served-model"
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_BASE_URL")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL")
    assert preset.seed_url() == ""
    assert preset.seed_model() == ""


# Persistence: unchanged (a user WITH an engine.json notices no difference)

def test_no_config_load_returns_none(tmp_path):
    cfg = tmp_path / "engine.json"
    assert load_engine_config(cfg) is None


def test_save_and_load_roundtrip(tmp_path):
    cfg = tmp_path / "engine.json"
    choice = EngineChoice(
        provider=OPENAI_COMPAT,
        model="my-served-model",
        api_url="http://10.1.2.3:8000/v1",
    )
    assert save_engine_config(choice, cfg) is True
    loaded = load_engine_config(cfg)
    assert loaded is not None
    assert loaded.provider == OPENAI_COMPAT
    assert loaded.model == "my-served-model"
    assert loaded.api_url == "http://10.1.2.3:8000/v1"


def test_persisted_config_never_contains_secret(tmp_path):
    """AGENTS.md: no secret persistence. engine.json must never hold an API key."""
    cfg = tmp_path / "engine.json"
    choice = EngineChoice(
        provider=OPENAI_COMPAT,
        model="my-served-model",
        api_url="http://10.1.2.3:8000/v1",
    )
    save_engine_config(choice, cfg)
    raw = json.loads(cfg.read_text())
    assert "api_key" not in raw
    assert "secret" not in raw
    assert "token" not in raw


def test_resolver_prefers_persisted_config(tmp_path):
    """Users holding a valid engine.json: behaviour stays the same (config wins)."""
    cfg = tmp_path / "engine.json"
    save_engine_config(EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b"), cfg)
    resolved = resolve_engine_choice(cfg)
    assert resolved.provider == LOCAL_OLLAMA
    assert resolved.model == "gemma4:12b"


# Provider onboarding: the END-USER may change provider (unchanged)

def test_user_custom_endpoint_persisted(tmp_path):
    """The END-USER picks their own OpenAI-compatible endpoint (e.g. an API gateway)."""
    cfg = tmp_path / "engine.json"
    choice = EngineChoice(
        provider=OPENAI_COMPAT,
        model="gpt-4o",
        api_url="https://api.example-gateway.test/v1",
    )
    assert save_engine_config(choice, cfg) is True
    loaded = load_engine_config(cfg)
    assert loaded is not None
    assert loaded.api_url == "https://api.example-gateway.test/v1"
    assert loaded.model == "gpt-4o"


def test_user_ollama_provider_persisted(tmp_path):
    """The END-USER picks Ollama as the provider."""
    cfg = tmp_path / "engine.json"
    choice = EngineChoice(provider=LOCAL_OLLAMA, model="llama3:8b")
    assert save_engine_config(choice, cfg) is True
    loaded = load_engine_config(cfg)
    assert loaded is not None
    assert loaded.provider == LOCAL_OLLAMA
    assert loaded.model == "llama3:8b"
    assert loaded.api_url is None


# Template: engine.example.json (DGX Spark / vLLM as a template)

def test_engine_example_template_is_present_and_neutral():
    example = Path(__file__).resolve().parents[1] / "engine.example.json"
    assert example.exists(), "the preset template engine.example.json is missing"
    raw = json.loads(example.read_text(encoding="utf-8"))
    assert raw["provider"] in ("local_ollama", "custom_ollama", "openai_compatible")
    # Neutral placeholders — no real host, no key.
    assert "api_key" not in raw
    assert "ts.net" not in json.dumps(raw)
    assert "your-" in raw["api_url"], "expected a placeholder host"
