"""
◑ Ephe – test_model_config.py

TDD tests for core/model_config.py (hybrid-architecture tier system).

Strategy: Given / When / Then
  - every test is pure unit level (no network, no Ollama)
  - threefold depth coverage: data model → env config → tier logic
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch


# Depth 1: data model

class TestModelTier:
    """GIVEN the ModelTier enum exists"""

    def test_offline_tier_value(self):
        """WHEN ModelTier.OFFLINE is accessed
        THEN it has the string value 'offline'"""
        from core.model_config import ModelTier
        assert ModelTier.OFFLINE.value == "offline"

    def test_fast_tier_value(self):
        """WHEN ModelTier.FAST is accessed
        THEN it has the string value 'fast'"""
        from core.model_config import ModelTier
        assert ModelTier.FAST.value == "fast"

    def test_power_tier_value(self):
        """WHEN ModelTier.POWER is accessed
        THEN it has the string value 'power'"""
        from core.model_config import ModelTier
        assert ModelTier.POWER.value == "power"

    def test_tier_from_string(self):
        """WHEN ModelTier('fast') is called
        THEN it returns ModelTier.FAST"""
        from core.model_config import ModelTier
        assert ModelTier("fast") == ModelTier.FAST


class TestModelConfig:
    """GIVEN a ModelConfig object"""

    def test_local_config_is_local(self):
        """WHEN host='localhost:11434'
        THEN .is_local returns True"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)
        assert cfg.is_local is True

    def test_local_config_is_not_remote(self):
        """WHEN host='localhost:11434'
        THEN .is_remote returns False"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)
        assert cfg.is_remote is False

    def test_remote_config_is_remote(self):
        """WHEN host='192.168.1.50:11434'
        THEN .is_remote returns True"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(
            name="gemma4:26b",
            tier=ModelTier.POWER,
            host="192.168.1.50:11434",
        )
        assert cfg.is_remote is True

    def test_remote_config_is_not_local(self):
        """WHEN host='dgx.local:11434'
        THEN .is_local returns False"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(
            name="gemma4:26b",
            tier=ModelTier.POWER,
            host="dgx.local:11434",
        )
        assert cfg.is_local is False

    def test_base_url_local(self):
        """WHEN host='localhost:11434'
        THEN .base_url returns 'http://localhost:11434'"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)
        assert cfg.base_url == "http://localhost:11434"

    def test_base_url_remote(self):
        """WHEN host='dgx.local:11434'
        THEN .base_url returns 'http://dgx.local:11434'"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(
            name="gemma4:26b",
            tier=ModelTier.POWER,
            host="dgx.local:11434",
        )
        assert cfg.base_url == "http://dgx.local:11434"

    def test_config_is_immutable(self):
        """WHEN an attempt is made to change name
        THEN it raises a FrozenInstanceError"""
        from core.model_config import ModelConfig, ModelTier
        cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)
        with pytest.raises(Exception):
            cfg.name = "changed"  # type: ignore[misc]


# Depth 2: TIER_MAP and get_model_config

class TestTierMap:
    """GIVEN the TIER_MAP is configured"""

    def test_no_tier_carries_a_tag_of_its_own(self):
        """WHEN no EPHE_*_MODEL env is set
        THEN every tier stays unnamed — the product names no model for the user
        (owner decision 2026-10-11)"""
        from core.model_config import _build_tier_map

        with patch.dict(os.environ, {}, clear=True):
            built = _build_tier_map()
        assert [cfg.name for cfg in built.values()] == ["", "", ""]

    def test_unnamed_tiers_match_no_context_window(self):
        """WHEN a tier has no tag
        THEN the prefix lookup does not hand its window to every unnamed model"""
        import core.model_config as m
        from core.model_config import ModelConfig, ModelTier

        unnamed = {tier: ModelConfig(name="", tier=tier) for tier in ModelTier}
        with patch.object(m, "TIER_MAP", unnamed):
            assert m.context_window_for_model("anything:7b") is None
            assert m.context_window_for_model("") is None

    def test_offline_tier_is_local(self):
        """WHEN get_model_config(OFFLINE) is called
        THEN the host is localhost"""
        from core.model_config import ModelTier, get_model_config
        cfg = get_model_config(ModelTier.OFFLINE)
        assert cfg.is_local is True

    def test_all_tiers_have_correct_tier_field(self):
        """WHEN every tier is fetched
        THEN the .tier field matches the requested tier"""
        from core.model_config import ModelTier, get_model_config
        for tier in ModelTier:
            cfg = get_model_config(tier)
            assert cfg.tier == tier


# Depth 3: env variable override

class TestEnvOverride:
    """GIVEN the tier table is built from the environment.

    Every case calls `_build_tier_map()` under a patched env instead of
    `importlib.reload(core.model_config)`: a reload mints a second `ModelTier` class,
    and a later module that compares tiers by identity (`test_hybrid_loop_router`,
    `core.model_router.LOOP_TIER`) then fails an `is` test between two objects whose
    reprs are identical. Measured: selecting model_config + model_router +
    hybrid_loop_router in that order failed 2 tests until the reloads went away, while
    the alphabetical suite order never met it."""

    def test_offline_model_env_override(self):
        """WHEN EPHE_OFFLINE_MODEL='gemma4:2b' is set
        THEN the OFFLINE tier carries that tag"""
        from core.model_config import ModelTier, _build_tier_map

        with patch.dict(os.environ, {"EPHE_OFFLINE_MODEL": "gemma4:2b"}):
            assert _build_tier_map()[ModelTier.OFFLINE].name == "gemma4:2b"

    def test_fast_model_env_override(self):
        """WHEN EPHE_FAST_MODEL is set
        THEN the FAST tier carries that tag"""
        from core.model_config import ModelTier, _build_tier_map

        with patch.dict(os.environ, {"EPHE_FAST_MODEL": "gemma4:12b"}):
            assert _build_tier_map()[ModelTier.FAST].name == "gemma4:12b"

    def test_power_model_env_override(self):
        """WHEN EPHE_POWER_MODEL='gemma4:31b' is set
        THEN the POWER tier carries that tag"""
        from core.model_config import ModelTier, _build_tier_map

        with patch.dict(os.environ, {"EPHE_POWER_MODEL": "gemma4:31b"}):
            assert _build_tier_map()[ModelTier.POWER].name == "gemma4:31b"

    def test_dgx_host_env_override(self):
        """WHEN EPHE_DGX_HOST='dgx.local:11434' is set
        THEN the POWER tier runs there and counts as remote"""
        from core.model_config import ModelTier, _build_tier_map

        with patch.dict(os.environ, {"EPHE_DGX_HOST": "dgx.local:11434"}):
            cfg = _build_tier_map()[ModelTier.POWER]
            assert cfg.host == "dgx.local:11434"
            assert cfg.is_remote is True

    def test_no_env_names_no_model(self):
        """WHEN no env variables are set
        THEN no tier resolves to a tag — the fallback that used to answer e2b/12b/26b
        was the product choosing a model for the user (owner decision 2026-10-11)"""
        clean_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("EPHE_")
        }
        from core.model_config import _build_tier_map

        with patch.dict(os.environ, clean_env, clear=True):
            assert [cfg.name for cfg in _build_tier_map().values()] == ["", "", ""]
