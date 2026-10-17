"""
◑ Ephe – the hybrid engine routing validator

E2E validation of the hybrid architecture (phase 5).
Three scenarios — all fully mocked (no real network needed).

Run:
    pytest tests/validate_hybrid_architecture.py -v

Given / When / Then — three levels of depth coverage:
  scenario 1: fully offline (OFFLINE tier)
  scenario 2: only the local Ollama (FAST tier)
  scenario 3: DGX available (POWER tier)
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Helpers

def make_probe(local: bool, remote: bool):
    from core.connectivity_probe import ConnectivityProbe
    probe = ConnectivityProbe.__new__(ConnectivityProbe)
    probe._dgx_host = "dgx.local:11434"
    probe._local_cache_result = None
    probe._local_cache_time = 0.0
    probe._remote_cache_result = None
    probe._remote_cache_time = 0.0
    probe.check_local = AsyncMock(return_value=local)
    probe.check_remote = AsyncMock(return_value=remote)
    return probe


# Scenario 1: fully offline

class TestScenario1FullOffline:
    """
    GIVEN no local Ollama, no DGX
    → the system has to choose the OFFLINE tier
    """

    async def test_s1_router_selects_offline_tier(self):
        """WHEN router.resolve() is called
        THEN it returns ModelTier.OFFLINE"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_probe(local=False, remote=False))
        config = await router.resolve()
        assert config.tier == ModelTier.OFFLINE

    async def test_s1_offline_model_is_e2b(self):
        """WHEN the OFFLINE tier is active
        THEN gemma4:e2b is used as the model"""
        from core.model_router import ModelRouter
        router = ModelRouter(probe=make_probe(local=False, remote=False))
        config = await router.resolve()
        assert "e2b" in config.name

    async def test_s1_offline_uses_local_client(self):
        """WHEN the OFFLINE tier is active
        THEN a local Ollama client is created (no remote)"""
        from core.model_router import ModelRouter
        from core.client_factory import OllamaClientFactory
        router = ModelRouter(probe=make_probe(local=False, remote=False))
        config = await router.resolve()
        assert config.is_local is True
        # the factory builds a local client
        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            OllamaClientFactory.build(config)
            kwargs = mock_cls.call_args.kwargs if mock_cls.call_args else {}
            assert "host" not in kwargs

    async def test_s1_force_tier_offline_works(self):
        """WHEN force_tier='offline' is set explicitly
        THEN the OFFLINE tier is used (even when local is available)"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_probe(local=True, remote=True))
        config = await router.resolve(force_tier="offline")
        assert config.tier == ModelTier.OFFLINE


# Scenario 2: local Ollama only

class TestScenario2LocalOnly:
    """
    GIVEN the local Ollama runs, no DGX
    → the system has to choose the FAST tier
    """

    async def test_s2_router_selects_fast_tier(self):
        """WHEN router.resolve() is called
        THEN it returns ModelTier.FAST"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_probe(local=True, remote=False))
        config = await router.resolve()
        assert config.tier == ModelTier.FAST

    async def test_s2_fast_model_is_12b(self):
        """WHEN the FAST tier is active
        THEN gemma4:12b is used as the model"""
        from core.model_router import ModelRouter
        router = ModelRouter(probe=make_probe(local=True, remote=False))
        config = await router.resolve()
        assert "12b" in config.name

    async def test_s2_fast_is_local(self):
        """WHEN the FAST tier is active
        THEN the model runs locally (not on the DGX)"""
        from core.model_router import ModelRouter
        router = ModelRouter(probe=make_probe(local=True, remote=False))
        config = await router.resolve()
        assert config.is_local is True

    async def test_s2_dgx_not_online(self):
        """WHEN only the local Ollama is available
        THEN dgx_online=False (the probe returns False)"""
        probe = make_probe(local=True, remote=False)
        dgx_status = await probe.check_remote()
        assert dgx_status is False


# Scenario 3: DGX available

class TestScenario3DGXAvailable:
    """
    GIVEN local Ollama + DGX both available
    → the system has to choose the POWER tier
    """

    async def test_s3_router_selects_power_tier(self):
        """WHEN router.resolve() is called
        THEN it returns ModelTier.POWER"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_probe(local=True, remote=True))
        config = await router.resolve()
        assert config.tier == ModelTier.POWER

    async def test_s3_power_model_is_large(self):
        """WHEN the POWER tier is active
        THEN a large model (26b/27b/31b) is used"""
        from core.model_router import ModelRouter
        router = ModelRouter(probe=make_probe(local=True, remote=True))
        config = await router.resolve()
        assert any(s in config.name for s in ("26b", "27b", "31b"))

    async def test_s3_power_uses_dgx_host_when_configured(self):
        """WHEN EPHE_DGX_HOST='dgx.local:11434' is configured
        THEN the POWER config carries this host"""
        import importlib
        with patch.dict(os.environ, {"EPHE_DGX_HOST": "dgx.local:11434"}):
            import core.model_config as m
            importlib.reload(m)
            config = m.get_model_config(m.ModelTier.POWER)
            assert config.host == "dgx.local:11434"
            assert config.is_remote is True
            importlib.reload(m)

    async def test_s3_power_client_uses_remote(self):
        """WHEN the POWER config is remote
        THEN ClientFactory creates a remote client with that host"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(
            name="gemma4:26b",
            tier=ModelTier.POWER,
            host="dgx.local:11434",
        )
        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            OllamaClientFactory.build(cfg)
            mock_cls.assert_called_once_with(host="http://dgx.local:11434")

    async def test_s3_cache_upgrade_from_fast_to_power(self):
        """GIVEN the router started with FAST (no DGX)
        WHEN the DGX becomes available + the cache is invalidated
        THEN router.resolve() returns POWER"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        probe = make_probe(local=True, remote=False)
        router = ModelRouter(probe=probe)

        cfg1 = await router.resolve()
        assert cfg1.tier == ModelTier.FAST

        # the DGX comes online
        probe.check_remote = AsyncMock(return_value=True)
        router.invalidate_cache()

        cfg2 = await router.resolve()
        assert cfg2.tier == ModelTier.POWER
