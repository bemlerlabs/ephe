"""
◑ Ephe – test_client_factory.py

TDD tests for core/client_factory.py

Given / When / Then — three levels of depth:
  depth 1: build(config) — the right client for a local config
  depth 2: build(config) — the right client for a remote config
  depth 3: build_for_tier() + integration in chat_with_tools
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# Depth 1: local config → local client

class TestBuildLocal:
    """GIVEN a local ModelConfig (localhost:11434)"""

    def test_local_config_creates_default_client(self):
        """WHEN factory.build(local_config) is called
        THEN ollama.AsyncClient() is created WITHOUT a host argument"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)

        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            OllamaClientFactory.build(cfg)
            # Must have been called without the 'host' keyword argument
            call_kwargs = mock_cls.call_args
            assert call_kwargs is None or "host" not in (call_kwargs.kwargs or {})

    def test_local_config_returns_client_instance(self):
        """WHEN factory.build(local_config) is called
        THEN it returns an ollama.AsyncClient object"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)

        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            fake_client = MagicMock()
            mock_cls.return_value = fake_client
            result = OllamaClientFactory.build(cfg)
            assert result is fake_client

    def test_offline_tier_creates_local_client(self):
        """WHEN build() is called with an OFFLINE config
        THEN no remote client is created"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:e2b", tier=ModelTier.OFFLINE)

        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            OllamaClientFactory.build(cfg)
            kwargs = mock_cls.call_args.kwargs if mock_cls.call_args else {}
            assert "host" not in kwargs


# Depth 2: remote config → DGX client

class TestBuildRemote:
    """GIVEN a remote ModelConfig (DGX host)"""

    def test_remote_config_creates_client_with_host(self):
        """WHEN factory.build(remote_config) is called
        THEN ollama.AsyncClient(host=...) is called WITH a host"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(
            name="gemma4:26b",
            tier=ModelTier.POWER,
            host="192.168.1.50:11434",
        )
        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            OllamaClientFactory.build(cfg)
            mock_cls.assert_called_once_with(host="http://192.168.1.50:11434")

    def test_remote_host_uses_base_url(self):
        """WHEN host='dgx.local:11434'
        THEN 'http://dgx.local:11434' is passed as the host parameter"""
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
            call_host = mock_cls.call_args.kwargs.get("host", "")
            assert call_host == "http://dgx.local:11434"


# Depth 3: build_for_tier() convenience

class TestBuildForTier:
    """GIVEN build_for_tier() as a shortcut"""

    def test_build_for_tier_returns_tuple(self):
        """WHEN build_for_tier(FAST) is called
        THEN it returns a (client, config) tuple"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelTier
        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = OllamaClientFactory.build_for_tier(ModelTier.FAST)
            assert isinstance(result, tuple)
            assert len(result) == 2

    def test_build_for_tier_config_matches_tier(self):
        """WHEN build_for_tier(OFFLINE) is called
        THEN the returned config has tier=OFFLINE"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelTier
        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            _client, config = OllamaClientFactory.build_for_tier(ModelTier.OFFLINE)
            assert config.tier == ModelTier.OFFLINE
            # The tier is a routing class; the tag is the user's env or nothing
            # (owner decision 2026-10-11 — this used to read back as e2b).
            assert config.name == ""

    def test_build_for_power_tier_uses_power_config(self):
        """WHEN build_for_tier(POWER) is called
        THEN the returned config has tier=POWER"""
        from core.client_factory import OllamaClientFactory
        from core.model_config import ModelTier
        with patch("core.client_factory.ollama.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            _client, config = OllamaClientFactory.build_for_tier(ModelTier.POWER)
            assert config.tier == ModelTier.POWER
