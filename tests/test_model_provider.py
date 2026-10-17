from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


def _reload_provider(monkeypatch, **env):
    for key in [
        "EPHE_MODEL_PROVIDER",
        "EPHE_MODEL",
        "EPHE_CUSTOM_OLLAMA_BASE_URL",
        "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_API_KEY",
        "EPHE_LOCAL_OLLAMA_BASE_URL",
        "OLLAMA_HOST",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import core.model_provider as provider

    return importlib.reload(provider)


def test_given_fresh_environment_when_provider_loaded_then_local_ollama_has_no_tag(monkeypatch):
    """
    GIVEN no provider env configuration
    WHEN the model provider is loaded
    THEN the engine class is local Ollama and the model tag is empty: naming a model
    is the user's choice, not a default this module can supply
    (owner decision 2026-10-11).
    """
    provider = _reload_provider(monkeypatch)
    active = provider.get_active_provider()
    assert active.provider == "local_ollama"
    assert active.model == ""
    assert active.base_url == "http://localhost:11434"
    assert active.offline_capable is True
    assert active.requires_internet is False


def test_given_global_ollama_host_env_when_provider_loaded_then_local_provider_keeps_loopback(monkeypatch):
    """
    GIVEN the user's shell exports OLLAMA_HOST for another project or machine
    WHEN the local provider is loaded
    THEN the default offline-first provider still uses local loopback.
    """
    provider = _reload_provider(monkeypatch, OLLAMA_HOST="http://host.docker.internal:11434")
    active = provider.get_active_provider()
    assert active.provider == "local_ollama"
    assert active.base_url == "http://localhost:11434"


def test_given_explicit_local_ollama_url_when_provider_loaded_then_local_provider_uses_it(monkeypatch):
    """
    GIVEN a user explicitly configures Ephe's local Ollama URL
    WHEN the local provider is loaded
    THEN that Ephe-specific endpoint is used.
    """
    provider = _reload_provider(
        monkeypatch,
        OLLAMA_HOST="http://wrong.example:11434",
        EPHE_LOCAL_OLLAMA_BASE_URL="http://127.0.0.1:11434",
    )
    active = provider.get_active_provider()
    assert active.provider == "local_ollama"
    assert active.base_url == "http://127.0.0.1:11434"


def test_given_global_ollama_host_env_when_client_built_then_loopback_host_is_passed(monkeypatch):
    """
    GIVEN OLLAMA_HOST points somewhere else
    WHEN the default local client is built
    THEN Ephe passes its own loopback host explicitly.
    """
    provider = _reload_provider(monkeypatch, OLLAMA_HOST="http://wrong.example:11434")
    with patch("core.model_provider.ollama.AsyncClient") as client_cls:
        provider.build_provider_client(provider.get_active_provider())
    client_cls.assert_called_once_with(host="http://localhost:11434")


def test_given_provider_config_when_validated_then_only_supported_types_are_allowed(monkeypatch):
    """
    GIVEN provider configuration
    WHEN provider types are validated
    THEN only the first release provider set is accepted.
    """
    provider = _reload_provider(monkeypatch)
    assert provider.validate_provider_type("local_ollama") == "local_ollama"
    assert provider.validate_provider_type("custom_ollama") == "custom_ollama"
    assert provider.validate_provider_type("openai_compatible") == "openai_compatible"
    with pytest.raises(ValueError):
        provider.validate_provider_type("random_cloud")


def test_given_custom_ollama_when_client_built_then_custom_base_url_is_used(monkeypatch):
    """
    GIVEN a user-owned Ollama-compatible endpoint
    WHEN a provider client is created
    THEN the Ollama client receives that exact base URL.
    """
    provider = _reload_provider(
        monkeypatch,
        EPHE_MODEL_PROVIDER="custom_ollama",
        EPHE_CUSTOM_OLLAMA_BASE_URL="http://192.168.1.25:11434",
        EPHE_MODEL="custom-model-x",
    )
    active = provider.get_active_provider()
    with patch("core.model_provider.ollama.AsyncClient") as client_cls:
        provider.build_provider_client(active)
    client_cls.assert_called_once_with(host="http://192.168.1.25:11434")


def test_given_openai_compatible_without_key_when_checked_then_setup_error_is_clear(monkeypatch):
    """
    GIVEN an online provider without an API key
    WHEN runtime readiness is checked
    THEN the error is explicit and no network call is attempted.
    """
    provider = _reload_provider(
        monkeypatch,
        EPHE_MODEL_PROVIDER="openai_compatible",
        EPHE_OPENAI_COMPAT_BASE_URL="https://api.example.test/v1",
        EPHE_OPENAI_COMPAT_MODEL="gpt-test",
    )
    active = provider.get_active_provider()
    with pytest.raises(provider.ProviderSetupError, match="API key"):
        provider.ensure_provider_ready(active)


def test_given_openai_compatible_without_base_url_when_checked_then_setup_error_is_clear(monkeypatch):
    """
    GIVEN an online provider with a key but no endpoint
    WHEN runtime readiness is checked
    THEN the user gets a setup error before any network request.
    """
    provider = _reload_provider(
        monkeypatch,
        EPHE_MODEL_PROVIDER="openai_compatible",
        EPHE_OPENAI_COMPAT_API_KEY="test-key",
        EPHE_OPENAI_COMPAT_MODEL="gpt-test",
    )
    active = provider.get_active_provider()
    with pytest.raises(provider.ProviderSetupError, match="base URL"):
        provider.ensure_provider_ready(active)


@pytest.mark.asyncio
async def test_given_openai_compatible_when_client_built_then_configured_base_url_is_used(monkeypatch):
    """
    GIVEN a user-owned OpenAI-compatible API endpoint
    WHEN chat is called through the central provider client
    THEN the request is sent to that configured endpoint with the server-side key.
    """
    provider = _reload_provider(
        monkeypatch,
        EPHE_MODEL_PROVIDER="openai_compatible",
        EPHE_OPENAI_COMPAT_BASE_URL="https://api.example.test/v1",
        EPHE_OPENAI_COMPAT_API_KEY="test-key",
        EPHE_OPENAI_COMPAT_MODEL="custom-model",
    )
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "AsyncClient", FakeHttpClient)
    client = provider.build_provider_client(provider.get_active_provider())
    response = await client.chat(
        model="custom-model",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )

    assert captured["url"] == "https://api.example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "custom-model"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert response.message.content == "ok"


def test_given_model_provider_api_when_health_and_provider_loaded_then_offline_flags_match(monkeypatch, tmp_path):
    """
    GIVEN local Ollama is the active provider
    WHEN /api/health and /api/model/providers are called
    THEN both expose offline-capable local provider state.
    """
    _reload_provider(monkeypatch)
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))

    from server.main import create_app

    with patch(
        "server.routes.health.check_ollama_connection",
        new=AsyncMock(return_value=(True, "ok", ["gemma4:12b"])),
    ), patch(
        "server.routes.health.ConnectivityProbe.check_remote",
        new=AsyncMock(return_value=False),
    ), patch(
        "server.routes.health.get_router"
    ) as router_getter:
        router_getter.return_value.invalidate_cache.return_value = None
        router_getter.return_value.resolve = AsyncMock()
        from core.model_config import ModelConfig, ModelTier

        router_getter.return_value.resolve.return_value = ModelConfig(
            name="gemma4:12b",
            tier=ModelTier.FAST,
        )
        client = TestClient(create_app())
        provider_res = client.get("/api/model/providers")
        health_res = client.get("/api/health")

    assert provider_res.status_code == 200
    provider_data = provider_res.json()
    assert provider_data["active"]["provider"] == "local_ollama"
    assert provider_data["active"]["offline_capable"] is True
    assert provider_data["active"]["requires_internet"] is False

    assert health_res.status_code == 200
    health_data = health_res.json()
    assert health_data["active_provider"] == "local_ollama"
    assert health_data["offline_capable"] is True
    assert health_data["requires_internet"] is False


def test_given_local_ollama_models_when_provider_api_called_then_chat_options_are_returned(monkeypatch, tmp_path):
    """
    GIVEN local Ollama has chat models
    WHEN /api/model/providers is called
    THEN the response contains structured local_model_options for the picker.
    """
    _reload_provider(monkeypatch)
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))

    from server.main import create_app

    model_options = [
        {
            "name": "gemma4:12b",
            "model": "gemma4:12b",
            "label": "gemma4:12b · 12.0B · Q4_K_M · 16GB RAM",
            "family": "gemma4",
            "parameter_size": "12.0B",
            "quantization": "Q4_K_M",
            "size_bytes": 9608350718,
            "size_label": "16GB RAM",
            "chat_capable": True,
        }
    ]

    with patch("server.routes.model_provider.list_local_models", new=AsyncMock(return_value=["gemma4:12b"])), patch(
        "server.routes.model_provider.list_local_model_options",
        new=AsyncMock(return_value=model_options),
    ):
        client = TestClient(create_app())
        response = client.get("/api/model/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["local_models"] == ["gemma4:12b"]
    assert data["local_model_options"][0]["name"] == "gemma4:12b"
    assert data["local_model_options"][0]["chat_capable"] is True


def test_given_unknown_local_model_when_provider_saved_then_request_is_rejected(monkeypatch, tmp_path):
    """
    GIVEN the user selects Local Ollama
    WHEN the requested model is not in detected chat models
    THEN Ephe rejects it instead of saving a broken provider state.
    """
    _reload_provider(monkeypatch)
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))

    from server.main import create_app

    with patch(
        "server.routes.model_provider.list_local_model_options",
        new=AsyncMock(return_value=[{"name": "gemma4:12b", "model": "gemma4:12b"}]),
    ):
        client = TestClient(create_app())
        response = client.put(
            "/api/model/provider",
            json={"provider": "local_ollama", "model": "gemma3:12b"},
        )

    assert response.status_code == 422
    assert "not installed" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_given_ollama_list_contains_embeddings_when_local_options_loaded_then_only_chat_models_remain(monkeypatch):
    """
    GIVEN Ollama lists chat and embedding models
    WHEN Ephe builds local model options
    THEN embedding/reranker models are hidden from the chat model picker.
    """
    import core.chat as chat

    class FakeClient:
        async def list(self):
            return SimpleNamespace(
                models=[
                    SimpleNamespace(
                        model="gemma3:12b",
                        size=8147483648,
                        details={"family": "gemma3", "families": ["gemma3"], "parameter_size": "12.0B", "quantization_level": "Q4_K_M"},
                    ),
                    SimpleNamespace(
                        model="nomic-embed-text:latest",
                        size=274302450,
                        details={"family": "nomic-bert", "families": ["nomic-bert"], "parameter_size": "137M", "quantization_level": "F16"},
                    ),
                ]
            )

    monkeypatch.setattr(chat, "build_provider_client", lambda _provider: FakeClient())
    options = await chat.list_local_model_options()

    assert [item["name"] for item in options] == ["gemma3:12b"]
    assert options[0]["label"].startswith("gemma3:12b · 12.0B")


# Engine abstraction (DGX-Spark ds4 / OpenAI-compatible)

def test_given_engine_url_when_provider_built_then_openai_compatible_config_returns(monkeypatch):
    """
    GIVEN a remote OpenAI-compatible engine URL (e.g. DGX-Spark ds4)
    WHEN build_engine_provider is called
    THEN an openai_compatible config with that base_url and advanced opt-in is returned.
    """
    import core.model_provider as provider

    cfg = provider.build_engine_provider(
        "http://spark-ds4.example.test:8000/v1", "deepseek-v4-flash"
    )

    assert cfg.provider == "openai_compatible"
    assert cfg.model == "deepseek-v4-flash"
    assert cfg.base_url == "http://spark-ds4.example.test:8000/v1"
    assert cfg.offline_capable is False
    assert cfg.advanced_opt_in is True


# Engine connection tests
# The check_engine_connection() tests (real, /v1/models, no fakes) live
# in tests/test_engine_connection_real.py — there they run against real
# local HTTP servers and the real DGX. There used to be fake-client tests here
# (FakeResponse/FakeHttpClient) that simulated the old chat POST path...[truncated]


def test_stream_client_has_read_timeout_not_none():
    """W19 bench finding: the engine stream client must NOT have timeout=None —
    otherwise the agent loop hangs endlessly when a connection dies without a FIN
    (Tailscale), while the SSE keepalives mask the silence.
    Generous read timeout (300s, long model thinking), but bounded."""
    import httpx

    from core.model_provider import OpenAICompatibleAsyncClient

    timeout = OpenAICompatibleAsyncClient.STREAM_TIMEOUT
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read is not None and timeout.read >= 30.0
    assert timeout.connect is not None and timeout.connect <= 30.0


def test_given_provider_without_model_when_resolved_then_it_names_the_variable(
    monkeypatch,
):
    """W18 ("no silent engine default") did not hold for this one reader routine:
    custom_ollama got the local model, openai_compatible got the
    placeholder 'custom-model' — the surface then reported a model that
    nobody had chosen. Now it breaks fail-closed, with the name of the
    missing variable."""
    provider = _reload_provider(
        monkeypatch,
        EPHE_MODEL_PROVIDER="openai_compatible",
        EPHE_OPENAI_COMPAT_BASE_URL="https://api.example.test/v1",
    )
    with pytest.raises(provider.EngineNotConfigured, match="EPHE_OPENAI_COMPAT_MODEL"):
        provider.get_active_provider()

    custom = _reload_provider(
        monkeypatch,
        EPHE_MODEL_PROVIDER="custom_ollama",
        EPHE_CUSTOM_OLLAMA_BASE_URL="http://192.168.1.25:11434",
    )
    with pytest.raises(provider.EngineNotConfigured, match="EPHE_MODEL"):
        custom.get_active_provider()


def test_given_local_ollama_env_without_model_when_resolved_then_it_names_the_variable(
    monkeypatch,
):
    """The local class stays first-class and fully offline — what it no longer gets is
    a tag of its own. An explicit EPHE_MODEL_PROVIDER=local_ollama without EPHE_MODEL
    used to resolve to the shipped default, a model nobody had chosen
    (owner decision 2026-10-11)."""
    provider = _reload_provider(monkeypatch, EPHE_MODEL_PROVIDER="local_ollama")
    with pytest.raises(provider.EngineNotConfigured, match="EPHE_MODEL"):
        provider.get_active_provider()
