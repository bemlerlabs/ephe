"""The stored key is bound to the engine identity it was entered for.

The binding is a SHA-256 of the key plus provider/model/api_url in an owner-only
sidecar next to the key. It is not the key and never becomes one.
"""
from __future__ import annotations

import json
import stat
from dataclasses import replace

import pytest

from core import engine_config as ec
from core.model_provider import ModelProviderConfig, ProviderSetupError, ensure_provider_ready


CHOICE = ec.EngineChoice(
    provider="openai_compatible",
    model="deepseek-chat",
    api_url="https://api.deepseek.com/v1",
)


def _key_path():
    return ec.key_file_path()


def _write_key(token: str, *, mode: int = 0o600) -> None:
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(mode)


def _write_binding(payload: dict) -> None:
    path = ec.key_binding_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, **payload}), encoding="utf-8")
    path.chmod(0o600)


def _binding_for(choice: ec.EngineChoice, token: str) -> dict:
    return {
        "provider": choice.provider,
        "model": choice.model,
        "api_url": choice.api_url,
        "key_fingerprint": ec.engine_key_fingerprint(token),
    }


def _cfg() -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="openai_compatible",
        model=CHOICE.model,
        base_url=CHOICE.api_url,
        label="test engine",
        offline_capable=False,
        requires_internet=True,
        requires_api_key=True,
        api_key_configured=True,
    )


def test_a_stored_key_without_a_binding_is_refused():
    _write_key("sk-or-v1-test")
    problem = ec.engine_key_binding_problem(CHOICE, "sk-or-v1-test", "file")
    assert "not bound" in problem
    with pytest.raises(ec.EngineKeyMismatch):
        ec.assert_engine_key_binding(CHOICE)


def test_a_binding_for_another_key_is_refused():
    _write_binding(_binding_for(CHOICE, "key-a"))
    problem = ec.engine_key_binding_problem(CHOICE, "key-b", "file")
    assert "does not match" in problem


def test_a_binding_for_another_engine_is_refused():
    _write_binding(_binding_for(CHOICE, "key-a"))
    other = replace(CHOICE, model="another-model")
    problem = ec.engine_key_binding_problem(other, "key-a", "file")
    assert "bound to" in problem and "another-model" in problem


def test_a_matching_binding_passes():
    _write_binding(_binding_for(CHOICE, "key-a"))
    assert ec.engine_key_binding_problem(CHOICE, "key-a", "file") is None
    assert ec.assert_engine_key_binding(CHOICE) is None


def test_an_explicit_shell_key_is_not_bound(monkeypatch):
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "env-key")
    monkeypatch.delenv("EPHE_ENGINE_KEY_SOURCE", raising=False)
    assert ec.engine_key_binding_problem(CHOICE, "env-key", "env") is None


def test_a_desktop_file_key_is_checked(monkeypatch):
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "key-b")
    monkeypatch.setenv("EPHE_ENGINE_KEY_SOURCE", "file")
    _write_binding(_binding_for(CHOICE, "key-a"))
    with pytest.raises(ProviderSetupError):
        ensure_provider_ready(_cfg())


def test_the_binding_file_is_owner_only_and_holds_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)
    ec.store_engine_api_key("tok-value", home=tmp_path, engine=CHOICE)
    path = ec.key_binding_path(home=tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text(encoding="utf-8")
    assert "tok-value" not in text
    payload = json.loads(text)
    assert payload["key_fingerprint"] == ec.engine_key_fingerprint("tok-value")
    assert payload["provider"] == CHOICE.provider
    assert payload["model"] == CHOICE.model


def test_delete_removes_the_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)
    ec.store_engine_api_key("tok", home=tmp_path, engine=CHOICE)
    ec.delete_engine_api_key(home=tmp_path)
    assert not ec.key_binding_path(home=tmp_path).exists()
    assert not ec.key_file_path(home=tmp_path).exists()


def test_the_readiness_gate_refuses_a_mismatched_key_before_a_request(monkeypatch):
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "")
    _write_key("key-b")
    _write_binding(_binding_for(CHOICE, "key-a"))
    with pytest.raises(ProviderSetupError, match="bound|match"):
        ensure_provider_ready(_cfg())


def test_the_readiness_gate_accepts_a_matching_key(monkeypatch):
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "")
    _write_key("key-a")
    _write_binding(_binding_for(CHOICE, "key-a"))
    assert ensure_provider_ready(_cfg()) is None
