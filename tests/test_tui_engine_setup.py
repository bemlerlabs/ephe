"""The engine setup the terminal app offers when nothing is configured.

The screens themselves need a terminal; what they decide — validity, what lands
in engine.json, which route lists the models — is plain code and is pinned here.
"""

from __future__ import annotations

import json
import os

import pytest

import core.engine_config as ec
from ui.setup import (
    PROVIDERS,
    list_models,
    provider_by_key,
    save_engine_setup,
    validate_setup,
)

PROVIDER_ENV = (
    "EPHE_MODEL_PROVIDER",
    "EPHE_OPENAI_COMPAT_BASE_URL",
    "EPHE_OPENAI_COMPAT_MODEL",
    "EPHE_OPENAI_COMPAT_API_KEY",
    "EPHE_CUSTOM_OLLAMA_BASE_URL",
    "EPHE_LOCAL_OLLAMA_BASE_URL",
    "EPHE_MODEL",
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    for var in PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)
    yield tmp_path


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_the_list_offers_local_remote_and_named_providers() -> None:
    keys = [provider.key for provider in PROVIDERS]
    assert keys == ["local", "ollama", "openai", "openrouter"]


def test_a_local_engine_needs_only_a_model() -> None:
    local = provider_by_key("local")
    assert validate_setup(local, "", "", "") == "Pick a model this machine serves."
    assert validate_setup(local, "", "llama3", "") is None


def test_a_named_cloud_provider_asks_for_its_key() -> None:
    openrouter = provider_by_key("openrouter")
    problem = validate_setup(openrouter, openrouter.start_url, "vendor/model", "")
    assert "API key" in (problem or "")
    assert validate_setup(openrouter, openrouter.start_url, "vendor/model", "k") is None


def test_a_remote_engine_cannot_be_saved_without_its_endpoint() -> None:
    endpoint = provider_by_key("openai")
    assert "endpoint" in (validate_setup(endpoint, "", "tag", "k") or "")


def test_a_local_choice_drops_the_endpoint(isolated) -> None:
    choice = save_engine_setup(provider_by_key("local"), "", "llama3", "")
    stored = json.loads((isolated / "engine.json").read_text())
    assert stored["provider"] == "local_ollama"
    assert stored["model"] == "llama3"
    assert stored["api_url"] is None
    assert choice.api_url is None
    assert os.environ["EPHE_MODEL_PROVIDER"] == "local_ollama"


def test_a_cloud_choice_keeps_the_url_and_never_the_key(
    isolated, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_keys: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "ui.setup.store_engine_api_key",
        lambda key, engine=None: stored_keys.append((key, engine.api_url)),
    )
    openrouter = provider_by_key("openrouter")
    save_engine_setup(openrouter, openrouter.start_url, "vendor/model", "sk-or-test")

    written = (isolated / "engine.json").read_text()
    assert json.loads(written)["api_url"] == "https://openrouter.ai/api/v1"
    assert "sk-or-test" not in written
    assert stored_keys == [("sk-or-test", "https://openrouter.ai/api/v1")]
    assert os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] == "https://openrouter.ai/api/v1"


def test_a_new_engine_keeps_the_folder_and_generation_settings(isolated) -> None:
    ec.save_engine_config(
        ec.EngineChoice(
            provider="openai_compatible",
            model="old",
            api_url="http://host:8000/v1",
            workspace_dir="/work",
            generation={"temperature": 0.2},
        )
    )
    choice = save_engine_setup(
        provider_by_key("openai"), "http://host:9000/v1", "new-model", ""
    )
    assert choice.workspace_dir == "/work"
    assert choice.generation == {"temperature": 0.2}
    assert choice.api_url == "http://host:9000/v1"


def test_list_models_reads_the_openai_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _open(request, timeout=0):
        seen.append(request.full_url)
        return _Response({"data": [{"id": "a"}, {"id": "b"}]})

    monkeypatch.setattr("urllib.request.urlopen", _open)
    models = list_models(provider_by_key("openai"), "http://host:8000/v1")
    assert models == ["a", "b"]
    assert seen == ["http://host:8000/v1/models"]


def test_list_models_reads_the_ollama_tag_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _open(request, timeout=0):
        seen.append(request.full_url)
        return _Response({"models": [{"name": "llama3:8b"}]})

    monkeypatch.setattr("urllib.request.urlopen", _open)
    assert list_models(provider_by_key("local"), "") == ["llama3:8b"]
    assert seen == ["http://127.0.0.1:11434/api/tags"]


def test_an_engine_that_does_not_answer_lists_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _open(request, timeout=0):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _open)
    assert list_models(provider_by_key("openai"), "http://host:8000/v1") == []
