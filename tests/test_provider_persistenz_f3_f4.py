"""F3/F4 regression: provider persistence + the empty-endpoint guard."""
import json

from core.model_provider import ModelProviderConfig, _ACTIVE_OVERRIDE  # noqa: F401


def test_f4_leerer_base_url_loescht_aktive_url_nicht(monkeypatch):
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", ModelProviderConfig(
        provider="openai_compatible", model="m", base_url="http://dgx:8000/v1",
        label="x", offline_capable=False, requires_internet=True, advanced_opt_in=True,
    ))
    cfg = mp.set_active_provider(provider="openai_compatible", model="m2", base_url=None)
    assert cfg.base_url == "http://dgx:8000/v1"  # F4: the URL stays, it is not wiped


def test_f3_put_persistiert_engine_json(tmp_path, monkeypatch):
    import server.routes.model_provider as mp_route
    import core.engine_config as ec

    cfg_file = tmp_path / "engine.json"
    monkeypatch.setattr(ec, "default_config_path", lambda: cfg_file)

    import asyncio
    res = asyncio.run(mp_route.update_model_provider(mp_route.ProviderUpdateRequest(
        provider="openai_compatible", model="qwen-test",
        base_url="http://dgx:8000/v1", confirm_online=True,
    )))
    assert res["active"]["base_url"] == "http://dgx:8000/v1"
    saved = json.loads(cfg_file.read_text())
    assert saved["api_url"] == "http://dgx:8000/v1"  # F3: persisted, not only in the session
