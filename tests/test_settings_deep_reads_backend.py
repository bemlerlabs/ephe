"""The backend readers of the deep line (wave I3-5).

`advanced.api_timeout` was a hard constant in the code (httpx timeout=120.0) while
the settings register offered the same value as a field nobody read. The test proves
the chain all the way into the httpx call — a field that sits in the register but is
never read is a false claim about controllability.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.settings_schema import save_deep_settings, settings_path


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Move settings.json (reads EPHE_CONFIG_DIR on every call) and engine.json (module
    constant CONFIG_DIR, frozen at import) out into the test directory."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    for key in (
        "EPHE_MODEL", "EPHE_MODEL_PROVIDER", "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_API_KEY", "EPHE_LOCAL_OLLAMA_BASE_URL",
        "EPHE_CUSTOM_OLLAMA_BASE_URL", "OLLAMA_HOST", "EPHE_TIMEZONE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield isolated


def _write_setting(section: str, field: str, value) -> None:
    assert save_deep_settings({section: {field: value}}) is True
    assert settings_path().is_file(), "settings.json landete nicht im isolierten Ordner"


class _CapturingHttp:
    """A stand-in for httpx.AsyncClient that records the constructor arguments."""

    last_timeout: object = "nie-gebaut"

    def __init__(self, **kwargs):
        _CapturingHttp.last_timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    async def post(self, _url, *, json=None, headers=None):
        class _R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        return _R()


@pytest.fixture()
def openai_engine(monkeypatch, tmp_path: Path):
    (tmp_path / "engine.json").write_text(
        json.dumps(
            {
                "provider": "openai_compatible",
                "model": "qwen-test",
                "api_url": "http://127.0.0.1:8000/v1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:8000/v1")
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _CapturingHttp)
    return httpx


@pytest.mark.asyncio
async def test_api_timeout_ohne_eintrag_bleibt_bei_dem_bisherigen_wert(
    openai_engine,
) -> None:
    """The register default of 120 equals the previously hardcoded value: with no
    setting, nothing changes."""
    from core.model_provider import OpenAICompatibleAsyncClient

    client = OpenAICompatibleAsyncClient(base_url="http://127.0.0.1:8000/v1", api_key="")
    await client.chat(model="qwen-test", messages=[{"role": "user", "content": "hi"}])
    assert _CapturingHttp.last_timeout == 120.0


@pytest.mark.asyncio
async def test_api_timeout_aus_dem_register_reicht_bis_in_den_httpx_call(
    openai_engine,
) -> None:
    from core.model_provider import OpenAICompatibleAsyncClient

    _write_setting("advanced", "advanced.api_timeout", 37)
    client = OpenAICompatibleAsyncClient(base_url="http://127.0.0.1:8000/v1", api_key="")
    await client.chat(model="qwen-test", messages=[{"role": "user", "content": "hi"}])
    assert _CapturingHttp.last_timeout == 37.0


@pytest.mark.asyncio
async def test_api_timeout_wird_geklemt_nicht_durchgereicht(openai_engine) -> None:
    """The register holds all the way into the request: 4000 lies outside 10..1800.

    The clamp sits in the pipeline; a value above the bound would honour a request
    the user can never order.
    """
    from core.model_provider import OpenAICompatibleAsyncClient

    (Path(__import__("os").environ["EPHE_CONFIG_DIR"]) / "settings.json").write_text(
        json.dumps({"version": 1, "sections": {"advanced": {"advanced.api_timeout": 4000}}}),
        encoding="utf-8",
    )
    client = OpenAICompatibleAsyncClient(base_url="http://127.0.0.1:8000/v1", api_key="")
    await client.chat(model="qwen-test", messages=[{"role": "user", "content": "hi"}])
    assert _CapturingHttp.last_timeout == 1800.0
