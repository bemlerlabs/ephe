"""Switch invariant (owner requirement, measured 2026-10-09).

A switch to an OpenAI-compatible engine changes the model AND the endpoint
together, or does not happen at all. The regression shape: `PUT /model/provider`
with a different model and no `base_url` inherited the PREVIOUS endpoint
(core.model_provider F4) — the composer's generic 'OpenAI-compatible' preset
switched the model to 'custom-model' while the live base_url stayed the Spark
address, so the next request left for the engine the user was already on.

Tests hit the route function directly. The persisted engine.json and the setup
skip marker are redirected to a temp dir so the owner's real config is never
touched.
"""
import asyncio
import json

import pytest
from fastapi import HTTPException

from core.model_provider import ModelProviderConfig

SPARK = "http://spark.example:8888/v1"
CLOUD = "http://cloud.example/v1"


def _cfg(provider, model, base_url):
    return ModelProviderConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        label="x",
        offline_capable=provider != "openai_compatible",
        requires_internet=provider == "openai_compatible",
        advanced_opt_in=True,
    )


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    import core.engine_config as ec
    import core.model_provider as mp
    import server.routes.settings as st

    cfg = tmp_path / "engine.json"
    monkeypatch.setattr(ec, "default_config_path", lambda: cfg)
    monkeypatch.setattr(st, "_clear_setup_skip", lambda: None)
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None)
    return cfg


def _switch(**req):
    import server.routes.model_provider as route

    return asyncio.run(route.update_model_provider(route.ProviderUpdateRequest(**req)))


def test_cross_model_switch_without_endpoint_does_not_half_apply(isolated, monkeypatch):
    """The invariant: a new model must never keep the endpoint it is leaving."""
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", _cfg("openai_compatible", "qwen3.8-flash-next", SPARK))
    with pytest.raises(HTTPException) as exc:
        _switch(provider="openai_compatible", model="other-model", confirm_online=True)
    assert exc.value.status_code == 409
    active = mp.get_active_provider()
    assert active.model == "qwen3.8-flash-next" and active.base_url == SPARK


def test_switch_into_openai_compatible_from_ollama_requires_endpoint(isolated, monkeypatch):
    """Leaving local Ollama for a cloud engine with no endpoint fails closed — there
    is no OpenAI-compatible URL to inherit, so the switch must not apply."""
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", _cfg("local_ollama", "gemma4:12b", "http://localhost:11434"))
    with pytest.raises(HTTPException) as exc:
        _switch(provider="openai_compatible", model="cloud-model", confirm_online=True)
    assert exc.value.status_code == 409


def test_cross_engine_switch_with_endpoint_moves_both(isolated, monkeypatch):
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", _cfg("openai_compatible", "qwen3.8-flash-next", SPARK))
    res = _switch(provider="openai_compatible", model="cloud-model", base_url=CLOUD, confirm_online=True)
    assert res["active"]["model"] == "cloud-model" and res["active"]["base_url"] == CLOUD


def test_switch_back_to_spark_persists_the_spark_url(isolated, monkeypatch):
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", _cfg("openai_compatible", "cloud-model", CLOUD))
    res = _switch(provider="openai_compatible", model="qwen3.8-flash-next", base_url=SPARK, confirm_online=True)
    assert res["active"]["base_url"] == SPARK
    assert json.loads(isolated.read_text())["api_url"] == SPARK


def test_same_model_reconfirm_keeps_the_endpoint(isolated, monkeypatch):
    """The legitimate F4 case stays: same model, already on an OpenAI-compatible
    endpoint, no new URL — the endpoint is kept, nothing is rejected."""
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", _cfg("openai_compatible", "qwen3.8-flash-next", SPARK))
    res = _switch(provider="openai_compatible", model="qwen3.8-flash-next", confirm_online=True)
    assert res["active"]["base_url"] == SPARK


def test_switch_preserves_brand_and_pricing(tmp_path, monkeypatch):
    """Second half of the invariant: a switch changes provider/model/api_url only.
    brand and pricing are read-modify-write inherited — not dropped — so the price
    table and brand kit survive an engine change (engine_config's own note)."""
    import core.engine_config as ec

    cfg = tmp_path / "engine.json"
    monkeypatch.setattr(ec, "default_config_path", lambda: cfg)
    brand = {"name": "Acme", "primary": "#111111"}
    pricing = {"in_per_m": 0.05, "out_per_m": 0.4}
    seed = ec.EngineChoice(
        provider="openai_compatible", model="qwen3.8-flash-next", api_url=SPARK,
        brand=brand, pricing=pricing,
    )
    assert ec.save_engine_config(seed, path=cfg)

    assert ec.persist_engine_choice("openai_compatible", "cloud-model", CLOUD)
    saved = json.loads(cfg.read_text())
    assert saved["model"] == "cloud-model" and saved["api_url"] == CLOUD
    assert saved["brand"] == brand and saved["pricing"] == pricing

