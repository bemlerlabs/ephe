"""R24: the readiness gate's contract — endpoint prerequisites, never a model tag.

Owner decision (W4-13, 2026-10-12). ``ensure_provider_ready`` and
``build_provider_client`` gate the ENDPOINT a client is built for: an API key where the
endpoint demands one, and a base URL. The model tag is a per-REQUEST parameter
(``client.chat(model=...)``), so the readiness layer never consumes one, and no tag
check is added there.

The reason is the unconfigured-state catalog. Nothing set resolves to a tag-free local
Ollama config, and ``core/chat_providers.py::list_local_models`` /
``list_local_model_options`` / ``check_ollama_connection`` build a client from exactly
that config to enumerate the models the user already installed — each answers ``[]`` or
offline when the build raises. A tag check at readiness would hide those models during
onboarding. The refusal that matters belongs to the request path, where a tag is
consumed: ``chosen_model`` raises ``EngineNotConfigured``.

Written half: the R24 section of ``docs/FAIL_CLOSED_PROVIDER_AUDIT.md``.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import engine_config as ec
from core import model_provider as mp

ROOT = Path(__file__).resolve().parents[1]

#: The autouse ``_isolate_provider_state`` fixture clears the provider env and the
#: module override, so each test below starts in the unconfigured state on purpose.


def _config(**overrides) -> mp.ModelProviderConfig:
    """A provider config carrying an empty model unless a test says otherwise."""
    base = {
        "provider": "local_ollama",
        "model": "",
        "base_url": "http://localhost:11434",
        "label": "Local Ollama",
        "offline_capable": True,
        "requires_internet": False,
    }
    base.update(overrides)
    return mp.ModelProviderConfig(**base)


def test_unconfigured_state_is_a_tag_free_local_config():
    active = mp.get_active_provider()
    assert active.provider == "local_ollama"
    assert active.model == ""


def test_readiness_gate_accepts_the_tag_free_config():
    active = mp.get_active_provider()
    assert mp.ensure_provider_ready(active) is None
    # The no-argument form reads the same active config.
    assert mp.ensure_provider_ready() is None


def test_readiness_gate_invents_no_model_tag():
    active = _config(model="")
    mp.ensure_provider_ready(active)
    assert active.model == ""


def test_catalog_probe_builds_a_client_from_the_tag_free_config(monkeypatch):
    """The onboarding catalog depends on the tag-free build path staying open.

    This drives the real ``build_provider_client`` (only the Ollama client class is
    faked); a model check in ``ensure_provider_ready`` would make the build raise and
    ``list_local_models`` answer ``[]``, hiding the installed models.
    """
    installed = ["gemma4:12b", "qwen3:8b"]

    class _FakeOllama:
        def __init__(self, *args, **kwargs):
            pass

        async def list(self):
            return SimpleNamespace(
                models=[SimpleNamespace(model=name) for name in installed]
            )

    import ollama

    monkeypatch.setattr(ollama, "AsyncClient", _FakeOllama)
    from core import chat_providers

    assert asyncio.run(chat_providers.list_local_models()) == installed


def test_the_tag_guard_lives_on_the_request_path(monkeypatch):
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    active = mp.get_active_provider()
    # Readiness accepts the tag-free config ...
    mp.ensure_provider_ready(active)
    # ... and the request path is where an unnamed tag is refused.
    with pytest.raises(ec.EngineNotConfigured):
        mp.chosen_model("the readiness pin")


def test_readiness_gate_refuses_a_missing_key():
    cfg = _config(
        provider="openai_compatible",
        base_url="https://api.example.test/v1",
        requires_internet=True,
        api_key_configured=False,
        requires_api_key=True,
    )
    with pytest.raises(mp.ProviderSetupError, match="API key"):
        mp.ensure_provider_ready(cfg)


def test_readiness_gate_refuses_a_missing_base_url():
    # Empty model AND empty base URL: the refusal names the URL, so the tag never
    # enters the readiness decision.
    cfg = _config(
        provider="openai_compatible",
        base_url="",
        requires_internet=True,
        api_key_configured=True,
        requires_api_key=True,
    )
    with pytest.raises(mp.ProviderSetupError, match="base URL"):
        mp.ensure_provider_ready(cfg)


def test_audit_records_the_readiness_decision():
    report = ROOT / "docs" / "FAIL_CLOSED_PROVIDER_AUDIT.md"
    if not report.is_file():
        # The written audit is a workshop document; the published tree carries the behaviour
        # pins around it, not the audit prose they quote.
        pytest.skip("the written audit is not carried by this tree")
    text = report.read_text(encoding="utf-8")
    assert "R24 readiness decision" in text, "the decision must be written down"
    assert "endpoint-only" in text, "the decision states what the gate covers"
    assert "test_provider_readiness.py" in text, "the written half names its pins"
    # The layer that DOES refuse an unnamed tag, and the residual left open.
    assert "chosen_model" in text
    assert "server/routes/chat.py" in text
