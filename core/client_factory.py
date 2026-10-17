"""
◑ Ephe – OllamaClientFactory
core/client_factory.py

Builds the right ollama.AsyncClient for a ModelConfig:
  - local config (localhost)  → ollama.AsyncClient()
  - remote config (DGX host)  → ollama.AsyncClient(host="http://...")

Separates client creation cleanly from the business logic.
All other modules (chat.py, swarm_v2.py, etc.) use this factory
instead of calling ollama.AsyncClient() directly.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import ollama

from core.model_config import ModelConfig, ModelTier, get_model_config


class OllamaClientFactory:
    """
    Static factory for ollama.AsyncClient instances.

    Example:
        config = get_model_config(ModelTier.POWER)
        client = OllamaClientFactory.build(config)
        # → AsyncClient(host="http://dgx.local:11434")
    """

    @staticmethod
    def build(config: ModelConfig) -> ollama.AsyncClient:
        """
        Creates an AsyncClient fitted to the ModelConfig.

        Args:
            config: ModelConfig with host and is_remote

        Returns:
            ollama.AsyncClient (configured for local or remote use)
        """
        if config.is_remote:
            return ollama.AsyncClient(host=config.base_url)
        return ollama.AsyncClient()

    @staticmethod
    def build_for_tier(tier: ModelTier) -> tuple[ollama.AsyncClient, ModelConfig]:
        """
        Shortcut: returns (client, config) for a tier.

        Args:
            tier: ModelTier.OFFLINE | FAST | POWER

        Returns:
            Tuple of (ollama.AsyncClient, ModelConfig)
        """
        config = get_model_config(tier)
        client = OllamaClientFactory.build(config)
        return client, config
