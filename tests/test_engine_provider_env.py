"""Root-cause fix: engine.json → correct provider env on the server (pure, real).

Bug: EngineChoice.apply_env() NEVER set EPHE_MODEL_PROVIDER. The
server provider resolver (core.model_provider._provider_from_env) reads
EPHE_MODEL_PROVIDER and otherwise always falls back to "local_ollama" —
so the PWA never used the configured engine, only local Ollama, even when
engine.json pointed at a remote engine.

Fix: apply_env() sets EPHE_MODEL_PROVIDER according to choice.provider.

These tests are PURE and REAL: they check only which env variables
apply_env() sets and how the provider resolver reads them. No mock,
no fake, no network. The real process path (cmd_start → server →
/api/health) is proven in test_engine_e2e_qwen.py with a real
ephe-start process + real HTTP.
"""
from __future__ import annotations

import os
from unittest.mock import patch as mock_patch

import pytest

from core.engine_config import (
    LOCAL_OLLAMA,
    OPENAI_COMPAT,
    EngineChoice,
    EngineNotConfigured,
)

# W18: no default host/model in the repo — the test chooses its own (user decision).
PROVIDER_URL = "http://10.1.2.3:8000/v1"
PROVIDER_MODEL = "my-served-model"


# apply_env: sets EPHE_MODEL_PROVIDER per provider (pure)

def test_apply_env_sets_provider_env_openai_compat():
    """GIVEN a Qwen-DGX engine (openai_compatible)
    WHEN apply_env()
    THEN EPHE_MODEL_PROVIDER = openai_compatible + base URL + model."""
    choice = EngineChoice(provider=OPENAI_COMPAT, model=PROVIDER_MODEL, api_url=PROVIDER_URL)
    with mock_patch.dict(os.environ, {}, clear=True):
        choice.apply_env()
        assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"
        assert os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] == PROVIDER_URL
        assert os.environ["EPHE_MODEL"] == os.environ["EPHE_MODEL"] == PROVIDER_MODEL
        # The provider resolver reads the model from EPHE_OPENAI_COMPAT_MODEL.
        assert os.environ["EPHE_OPENAI_COMPAT_MODEL"] == PROVIDER_MODEL


def test_apply_env_sets_the_model_key_before_it_refuses_a_missing_endpoint():
    """GIVEN an openai_compatible choice without api_url
    WHEN apply_env()
    THEN the provider-specific model key is set, and the refusal names api_url
    and the fix. The model assignment may not depend on the endpoint branch."""
    choice = EngineChoice(provider=OPENAI_COMPAT, model=PROVIDER_MODEL, api_url=None)
    with mock_patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EngineNotConfigured) as excinfo:
            choice.apply_env()
        assert os.environ["EPHE_OPENAI_COMPAT_MODEL"] == PROVIDER_MODEL
        assert "api_url" in str(excinfo.value)
        assert "ephe configure" in excinfo.value.hint


def test_apply_env_refuses_openai_compat_without_api_url():
    """GIVEN a persisted openai_compatible choice with no endpoint
    WHEN apply_env()
    THEN it fails closed and names the missing field instead of leaving the
    provider resolver to report a missing model key."""
    choice = EngineChoice(provider=OPENAI_COMPAT, model=PROVIDER_MODEL, api_url=None)
    with mock_patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EngineNotConfigured) as excinfo:
            choice.apply_env()
        message = str(excinfo.value)
        assert "missing field" in message and "api_url" in message
        assert "EPHE_OPENAI_COMPAT_MODEL" not in message


def test_apply_env_sets_provider_env_local_ollama():
    """GIVEN local Ollama
    WHEN apply_env()
    THEN EPHE_MODEL_PROVIDER = local_ollama."""
    choice = EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b")
    with mock_patch.dict(os.environ, {}, clear=True):
        choice.apply_env()
        assert os.environ["EPHE_MODEL_PROVIDER"] == "local_ollama"


def test_server_resolver_picks_openai_compat_after_apply_env():
    """REGRESSION: after apply_env() the server resolver resolves the correct
    engine (instead of silently local_ollama). Pure (only reads env)."""
    choice = EngineChoice(provider=OPENAI_COMPAT, model=PROVIDER_MODEL, api_url=PROVIDER_URL)
    with mock_patch.dict(os.environ, {}, clear=True):
        choice.apply_env()
        import core.model_provider as mp
        cfg = mp._provider_from_env()
        assert cfg.provider == "openai_compatible"
        assert cfg.model == PROVIDER_MODEL
        assert cfg.base_url.rstrip("/") == PROVIDER_URL
