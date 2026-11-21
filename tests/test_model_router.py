"""
◑ Ephe – test_model_router.py

TDD tests for core/model_router.py

Given / When / Then — threefold depth coverage:
  Depth 1: resolve() — tier decision via probe
  Depth 2: force_tier + EPHE_FORCE_TIER env override
  Depth 3: cache invalidation + singleton
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest


# Helper: fake probe

def make_fake_probe(local: bool, remote: bool):
    """Builds a fake probe that makes no network calls."""
    from core.connectivity_probe import ConnectivityProbe
    probe = ConnectivityProbe.__new__(ConnectivityProbe)
    probe._dgx_host = "dgx.local:11434" if remote else None
    probe._local_cache_result = None
    probe._local_cache_time = 0.0
    probe._remote_cache_result = None
    probe._remote_cache_time = 0.0
    probe.check_local = AsyncMock(return_value=local)
    probe.check_remote = AsyncMock(return_value=remote)
    return probe


# Depth 1: resolve() — automatic tier choice

def _unnamed_tiers(monkeypatch) -> None:
    """Seed a tier table with no tags.

    `core.model_config.get_model_config` reads the module global built at import, and
    `test_hybrid_loop_router`'s fixture reloads that module with EPHE_FAST_MODEL set and
    undoes the env only afterwards — so in suite order the table these tests see carries a
    tag. The router's contract is unchanged by that; the assertion has to state its own
    input instead of inheriting whoever imported last."""
    import core.model_config as m

    monkeypatch.setattr(m, "TIER_MAP", {
        tier: m.ModelConfig(name="", tier=tier) for tier in m.ModelTier
    })


class TestResolveAutomatic:
    """GIVEN no force_tier — the probe decides"""

    async def test_resolve_offline_when_nothing_available(self, monkeypatch):
        """GIVEN local Ollama and DGX unreachable
        WHEN router.resolve() is called
        THEN it returns a ModelConfig with tier=OFFLINE"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        _unnamed_tiers(monkeypatch)
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve()
        assert cfg.tier == ModelTier.OFFLINE
        assert cfg.name == ""  # the tier is a class; the tag stays the user's

    async def test_resolve_fast_when_only_local(self, monkeypatch):
        """GIVEN only local Ollama reachable
        WHEN router.resolve() is called
        THEN it returns a ModelConfig with tier=FAST"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        _unnamed_tiers(monkeypatch)
        router = ModelRouter(probe=make_fake_probe(local=True, remote=False))
        cfg = await router.resolve()
        assert cfg.tier == ModelTier.FAST
        assert cfg.name == ""  # the tier is a class; the tag stays the user's

    async def test_resolve_power_when_dgx_available(self):
        """GIVEN local Ollama + DGX both reachable
        WHEN router.resolve() is called
        THEN it returns a ModelConfig with tier=POWER"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=True, remote=True))
        cfg = await router.resolve()
        assert cfg.tier == ModelTier.POWER

    async def test_resolve_returns_model_config_object(self):
        """WHEN router.resolve() is called
        THEN it always returns a ModelConfig object"""
        from core.model_router import ModelRouter
        from core.model_config import ModelConfig
        router = ModelRouter(probe=make_fake_probe(local=True, remote=False))
        cfg = await router.resolve()
        assert isinstance(cfg, ModelConfig)


# Depth 2: force_tier parameter + env override

class TestForceTier:
    """GIVEN force_tier overrides the automatic decision"""

    async def test_force_offline_ignores_probe(self):
        """GIVEN force_tier='offline' even though DGX would be reachable
        WHEN router.resolve(force_tier='offline') is called
        THEN it ALWAYS returns ModelTier.OFFLINE"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=True, remote=True))
        cfg = await router.resolve(force_tier="offline")
        assert cfg.tier == ModelTier.OFFLINE

    async def test_force_power_ignores_probe(self):
        """GIVEN force_tier='power' even though nothing would be reachable
        WHEN router.resolve(force_tier='power') is called
        THEN it ALWAYS returns ModelTier.POWER"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve(force_tier="power")
        assert cfg.tier == ModelTier.POWER

    async def test_force_fast_ignores_probe(self):
        """GIVEN force_tier='fast'
        WHEN router.resolve(force_tier='fast') is called
        THEN it returns ModelTier.FAST"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve(force_tier="fast")
        assert cfg.tier == ModelTier.FAST

    async def test_env_force_tier_overrides_automatically(self):
        """GIVEN the EPHE_FORCE_TIER='power' env var is set
        WHEN router.resolve() is called without an argument
        THEN it returns POWER (no matter what the probe says)"""
        from core.model_config import ModelTier
        with patch.dict(os.environ, {"EPHE_FORCE_TIER": "power"}):
            from core.model_router import ModelRouter
            import importlib, core.model_router as m
            importlib.reload(m)
            router = m.ModelRouter(probe=make_fake_probe(local=False, remote=False))
            cfg = await router.resolve()
            assert cfg.tier == ModelTier.POWER
            importlib.reload(m)


# Depth 4: G7 per-task routing (resolve_for_task)

class TestPerTaskRouting:
    """G7: resolve_for_task picks the tier deterministically by task category."""

    async def test_light_task_maps_to_offline(self):
        """GIVEN task_kind='light'
        WHEN router.resolve_for_task('light') is called
        THEN the tier is OFFLINE"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("light")
        assert cfg.tier == ModelTier.OFFLINE

    async def test_medium_task_maps_to_fast(self):
        """GIVEN task_kind='medium'
        WHEN router.resolve_for_task('medium') is called
        THEN the tier is FAST"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("medium")
        assert cfg.tier == ModelTier.FAST

    async def test_heavy_task_maps_to_power(self):
        """GIVEN task_kind='heavy'
        WHEN router.resolve_for_task('heavy') is called
        THEN the tier is POWER"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("heavy")
        assert cfg.tier == ModelTier.POWER

    async def test_unknown_task_kind_falls_back_to_fast(self):
        """GIVEN unknown task_kind='banana'
        WHEN router.resolve_for_task('banana') is called
        THEN the tier is FAST (safe middle path, no crash)"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("banana")
        assert cfg.tier == ModelTier.FAST

    async def test_empty_task_kind_falls_back_to_fast(self):
        """GIVEN empty task_kind=''
        WHEN router.resolve_for_task('') is called
        THEN the tier is FAST"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("")
        assert cfg.tier == ModelTier.FAST

    async def test_task_kind_is_case_insensitive_and_trimmed(self):
        """GIVEN task_kind='  HEAVY  ' (upper case + whitespace)
        WHEN router.resolve_for_task is called
        THEN the tier is POWER (normalised: strip + lower)"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("  HEAVY  ")
        assert cfg.tier == ModelTier.POWER

    async def test_force_tier_wins_over_task_kind(self):
        """GIVEN task_kind='heavy' but force_tier='offline'
        WHEN router.resolve_for_task('heavy', force_tier='offline') is called
        THEN the tier is OFFLINE (a hard override always wins)"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        cfg = await router.resolve_for_task("heavy", force_tier="offline")
        assert cfg.tier == ModelTier.OFFLINE

    def test_task_tier_map_covers_all_three_tiers(self):
        """GIVEN TASK_TIER_MAP
        WHEN the three categories are looked at
        THEN they cover exactly OFFLINE/FAST/POWER (complete matrix)"""
        from core.model_router import TASK_TIER_MAP
        from core.model_config import ModelTier
        assert set(TASK_TIER_MAP.keys()) == {"light", "medium", "heavy"}
        assert set(TASK_TIER_MAP.values()) == {ModelTier.OFFLINE, ModelTier.FAST, ModelTier.POWER}


# Depth 3: cache + invalidation + singleton

class TestRouterCache:
    """GIVEN the router caches its result for fast subsequent calls"""

    async def test_resolve_caches_result(self):
        """GIVEN resolve() was called once
        WHEN resolve() is called again
        THEN the probe is NOT called again (cache hit)"""
        from core.model_router import ModelRouter
        probe = make_fake_probe(local=True, remote=False)
        router = ModelRouter(probe=probe)
        await router.resolve()
        await router.resolve()
        # the probe should have been called only once
        assert probe.check_local.call_count == 1

    async def test_invalidate_cache_triggers_new_probe(self):
        """GIVEN the cache was invalidated
        WHEN resolve() is called again
        THEN the probe is called again"""
        from core.model_router import ModelRouter
        probe = make_fake_probe(local=True, remote=False)
        router = ModelRouter(probe=probe)
        await router.resolve()
        router.invalidate_cache()
        await router.resolve()
        assert probe.check_local.call_count == 2

    async def test_tier_upgrade_after_cache_invalidation(self):
        """GIVEN the first resolve() returns FAST
        WHEN DGX becomes available + invalidate_cache() + another resolve()
        THEN it returns POWER"""
        from core.model_router import ModelRouter
        from core.model_config import ModelTier
        probe = make_fake_probe(local=True, remote=False)
        router = ModelRouter(probe=probe)

        cfg1 = await router.resolve()
        assert cfg1.tier == ModelTier.FAST

        # DGX becomes available
        probe.check_remote = AsyncMock(return_value=True)
        router.invalidate_cache()

        cfg2 = await router.resolve()
        assert cfg2.tier == ModelTier.POWER

    def test_get_router_returns_singleton(self):
        """GIVEN get_router() is called twice
        WHEN the module has not been reloaded
        THEN it is the same object (singleton)"""
        import importlib, core.model_router as m
        importlib.reload(m)  # start from a fresh singleton
        router1 = m.get_router()
        router2 = m.get_router()
        assert router1 is router2
        importlib.reload(m)


# Depth 5: tier-tag validation (WS1-5)

def _tier_table(**names) -> dict:
    """A tier table whose entries carry the tags given as offline=/fast=/power=."""
    import core.model_config as mc
    return {
        mc.ModelTier.OFFLINE: mc.ModelConfig(name=names.get("offline", ""), tier=mc.ModelTier.OFFLINE),
        mc.ModelTier.FAST: mc.ModelConfig(name=names.get("fast", ""), tier=mc.ModelTier.FAST),
        mc.ModelTier.POWER: mc.ModelConfig(name=names.get("power", ""), tier=mc.ModelTier.POWER),
    }


class TestTierTagValidation:
    """GIVEN a tier tag comes from the user's environment
    WHEN it is validated
    THEN anything that is not a plain model id is refused by the variable that carried it"""

    def test_valid_tag_is_returned_unchanged(self):
        """GIVEN a plain Ollama tag
        WHEN normalize_tier_tag runs
        THEN the value comes back as written"""
        from core.model_router import normalize_tier_tag
        assert normalize_tier_tag("gemma4:12b", source="EPHE_FAST_MODEL") == "gemma4:12b"

    def test_surrounding_whitespace_is_stripped(self):
        """GIVEN the tag "  mine:work  "
        WHEN normalize_tier_tag runs
        THEN the value is trimmed and accepted"""
        from core.model_router import normalize_tier_tag
        assert normalize_tier_tag("  mine:work  ", source="EPHE_FAST_MODEL") == "mine:work"

    def test_missing_tag_is_the_unnamed_tier(self):
        """GIVEN an unset variable (None) or an empty value
        WHEN normalize_tier_tag runs
        THEN "" comes back and no error is raised"""
        from core.model_router import normalize_tier_tag
        assert normalize_tier_tag(None, source="EPHE_OFFLINE_MODEL") == ""
        assert normalize_tier_tag("   ", source="EPHE_OFFLINE_MODEL") == ""

    @pytest.mark.parametrize(
        "bad",
        ["gemma4 12b", "gemma4\n12b", "tag;rm -rf", "mine$(whoami)", "-lead", ":fresh"],
    )
    def test_tag_with_a_forbidden_character_is_refused(self, bad):
        """GIVEN a tag holding whitespace, a control character or a shell metacharacter
        WHEN normalize_tier_tag runs
        THEN TierTagError is raised"""
        from core.model_router import TierTagError, normalize_tier_tag
        with pytest.raises(TierTagError):
            normalize_tier_tag(bad, source="EPHE_FAST_MODEL")

    def test_tag_over_the_ceiling_is_refused(self):
        """GIVEN a 201-character tag
        WHEN normalize_tier_tag runs
        THEN TierTagError is raised"""
        from core.model_router import TIER_TAG_MAX_LEN, TierTagError, normalize_tier_tag
        with pytest.raises(TierTagError):
            normalize_tier_tag("a" * (TIER_TAG_MAX_LEN + 1), source="EPHE_POWER_MODEL")

    def test_refusal_names_the_source_variable(self):
        """GIVEN a malformed value read from EPHE_FAST_MODEL
        WHEN the refusal is built
        THEN its text names EPHE_FAST_MODEL"""
        from core.model_router import TierTagError, normalize_tier_tag
        with pytest.raises(TierTagError) as raised:
            normalize_tier_tag("bad tag", source="EPHE_FAST_MODEL")
        assert "EPHE_FAST_MODEL" in str(raised.value)

    def test_invalid_tier_tags_reports_only_the_broken_tier(self, monkeypatch):
        """GIVEN FAST carries "bad tag" and OFFLINE/POWER are clean
        WHEN invalid_tier_tags runs
        THEN only FAST appears, with its reason"""
        import core.model_config as mc
        from core.model_router import invalid_tier_tags
        monkeypatch.setattr(mc, "TIER_MAP", _tier_table(fast="bad tag", power="mine:big"))

        problems = invalid_tier_tags()

        assert set(problems) == {mc.ModelTier.FAST}
        assert "EPHE_FAST_MODEL" in problems[mc.ModelTier.FAST]

    def test_invalid_tier_tags_is_empty_when_the_table_is_clean(self, monkeypatch):
        """GIVEN every tier is unnamed or carries a model id
        WHEN invalid_tier_tags runs
        THEN the result is empty"""
        import core.model_config as mc
        from core.model_router import invalid_tier_tags
        monkeypatch.setattr(mc, "TIER_MAP", _tier_table(fast="mine:work", power="mine:big"))

        assert invalid_tier_tags() == {}

    def test_tier_selector_accepts_the_three_names(self):
        """GIVEN the selector values with mixed case and padding
        WHEN parse_tier_selector runs
        THEN each maps to its tier"""
        from core.model_config import ModelTier
        from core.model_router import parse_tier_selector
        assert parse_tier_selector(" FAST ", source="force_tier") == ModelTier.FAST
        assert parse_tier_selector("power", source="force_tier") == ModelTier.POWER
        assert parse_tier_selector("offline", source="force_tier") == ModelTier.OFFLINE

    def test_unknown_tier_selector_is_refused(self):
        """GIVEN the selector "banana"
        WHEN parse_tier_selector runs
        THEN TierTagError names the source and the allowed values"""
        from core.model_router import TierTagError, parse_tier_selector
        with pytest.raises(TierTagError) as raised:
            parse_tier_selector("banana", source="EPHE_FORCE_TIER")
        assert "EPHE_FORCE_TIER" in str(raised.value)
        assert "offline" in str(raised.value)


class TestTierTagValidationAtTheRouter:
    """GIVEN a bad tag or selector reaches the router
    WHEN a tier is resolved or a step is bound
    THEN the router refuses before an engine request is built"""

    async def test_resolve_refuses_an_unknown_force_tier(self):
        """GIVEN force_tier="banana"
        WHEN resolve() runs
        THEN TierTagError names force_tier"""
        from core.model_router import ModelRouter, TierTagError
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        with pytest.raises(TierTagError) as raised:
            await router.resolve(force_tier="banana")
        assert "force_tier" in str(raised.value)

    async def test_resolve_refuses_a_malformed_env_selector(self):
        """GIVEN EPHE_FORCE_TIER="banana"
        WHEN resolve() runs without an argument
        THEN TierTagError names EPHE_FORCE_TIER"""
        from core.model_router import ModelRouter, TierTagError
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))
        with patch.dict(os.environ, {"EPHE_FORCE_TIER": "banana"}), \
                pytest.raises(TierTagError) as raised:
            await router.resolve()
        assert "EPHE_FORCE_TIER" in str(raised.value)

    async def test_resolve_refuses_a_tier_whose_tag_is_malformed(self, monkeypatch):
        """GIVEN FAST carries "bad tag"
        WHEN resolve(force_tier="fast") runs
        THEN TierTagError names EPHE_FAST_MODEL"""
        import core.model_config as mc
        from core.model_router import ModelRouter, TierTagError
        monkeypatch.setattr(mc, "TIER_MAP", _tier_table(fast="bad tag"))
        router = ModelRouter(probe=make_fake_probe(local=True, remote=False))

        with pytest.raises(TierTagError) as raised:
            await router.resolve(force_tier="fast")

        assert "EPHE_FAST_MODEL" in str(raised.value)

    async def test_bind_call_refuses_a_malformed_bound_tier(self, monkeypatch):
        """GIVEN FAST carries "bad tag"
        WHEN a read-only step is bound to FAST
        THEN TierTagError is raised"""
        import core.model_config as mc
        from core.model_router import LOOP_TIER, LoopRoute, TierTagError, bind_call
        monkeypatch.setattr(mc, "TIER_MAP", _tier_table(fast="bad tag"))
        active = mc.ModelConfig(name="mine:big", tier=mc.ModelTier.POWER)

        with pytest.raises(TierTagError):
            bind_call(LoopRoute(LOOP_TIER, "router-loop-readonly"), active)

    async def test_a_clean_tier_resolves_normally(self, monkeypatch):
        """GIVEN FAST carries "mine:work"
        WHEN resolve(force_tier="fast") runs
        THEN the tag comes back unchanged"""
        import core.model_config as mc
        from core.model_router import ModelRouter
        monkeypatch.setattr(mc, "TIER_MAP", _tier_table(fast="mine:work"))
        router = ModelRouter(probe=make_fake_probe(local=False, remote=False))

        cfg = await router.resolve(force_tier="fast")

        assert (cfg.tier, cfg.name) == (mc.ModelTier.FAST, "mine:work")
