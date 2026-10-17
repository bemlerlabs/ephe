"""
◑ Ephe – Model Router
core/model_router.py

Automatically picks the best available model tier:
  OFFLINE → FAST → POWER

Decision logic:
  1. EPHE_FORCE_TIER env var or the force_tier parameter → always that tier
  2. ConnectivityProbe checks local Ollama + DGX remote
  3. The result is cached until invalidate_cache() is called

Tier tags and the validation they pass: docs/MODEL_ROUTER_TIER_TAGS.md

Example:
    router = get_router()
    config = await router.resolve()
    # → ModelConfig(name="<the tag the user configured>", tier=FAST, host="localhost:11434")

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import os
import re
import time
from collections.abc import Iterable
from typing import NamedTuple

from core.engine_config import EngineNotConfigured
from core.model_config import ModelConfig, ModelTier, get_model_config
from core.connectivity_probe import ConnectivityProbe


# E4: TTL for the connectivity-probe cache (seconds). After it expires the
# probe runs again (so a network change / Ollama restart is noticed without a
# manual invalidate_cache()). 30s = short enough for pairing, long enough to
# avoid probing every request.
PROBE_CACHE_TTL_SECONDS: float = 30.0


# G7: per-task model routing. Light tasks (classification, extraction,
# format conversion) run on the cheap OFFLINE/FAST tier, complex ones
# (analysis, code, multi-step plans) on POWER. Deterministic, without
# a model dialog. Unknown category -> FAST (safe middle path).
TASK_TIER_MAP: dict[str, ModelTier] = {
    "light": ModelTier.OFFLINE,   # classification, extraction, conversion
    "medium": ModelTier.FAST,     # summarization, simple Q&A
    "heavy": ModelTier.POWER,     # analysis, code, plan, multi-step research
}


# Tier tags arrive from the user's environment (EPHE_*_MODEL); nothing here supplies one, so what
# this section owns is the gate. A value that is not a plain model id never travels into an engine
# request, and the variable that carried it is named in the refusal.
TIER_ENV_VARS: dict[ModelTier, str] = {
    ModelTier.OFFLINE: "EPHE_OFFLINE_MODEL",
    ModelTier.FAST: "EPHE_FAST_MODEL",
    ModelTier.POWER: "EPHE_POWER_MODEL",
}

#: Ollama tags and OpenAI-compatible model ids share one shape: a letter or a digit first, then
#: letters, digits and . _ - / : — the ceiling stops a pasted blob from travelling as a tag.
TIER_TAG_MAX_LEN = 200
_TIER_TAG_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:-]*")


class TierTagError(ValueError):
    """A tier tag or a tier selector that cannot name a model."""


def normalize_tier_tag(tag: str | None, *, source: str) -> str:
    """Strip one configured tag; "" stays an unnamed tier.

    Raises TierTagError naming `source` when the value is not a model id.
    """
    value = (tag or "").strip()
    if not value:
        return ""
    if len(value) > TIER_TAG_MAX_LEN:
        raise TierTagError(
            f"{source} is {len(value)} characters long; the ceiling is {TIER_TAG_MAX_LEN}."
        )
    if not _TIER_TAG_SHAPE.fullmatch(value):
        raise TierTagError(
            f"{source}={value!r} is not a model id. Allowed: letters, digits and . _ - / :, "
            "with a letter or a digit first."
        )
    return value


def invalid_tier_tags() -> dict[ModelTier, str]:
    """Every configured tier whose tag is not a model id, as {tier: reason}.

    An unnamed tier is valid and stays out of the result. A startup check or a doctor
    command can report the whole table before the first turn is routed.
    """
    problems: dict[ModelTier, str] = {}
    for tier in ModelTier:
        source = TIER_ENV_VARS[tier]
        try:
            normalize_tier_tag(get_model_config(tier).name, source=source)
        except TierTagError as exc:
            problems[tier] = str(exc)
    return problems


def parse_tier_selector(value: str | None, *, source: str) -> ModelTier:
    """Turn "offline"/"fast"/"power" into a tier.

    Raises TierTagError naming `source` for any other value, so a bad override reports the
    variable it came from.
    """
    text = (value or "").strip().lower()
    try:
        return ModelTier(text)
    except ValueError:
        allowed = " | ".join(tier.value for tier in ModelTier)
        raise TierTagError(f"{source}={value!r} is not a tier. One of: {allowed}.") from None


def _checked_tier_config(tier: ModelTier) -> ModelConfig:
    """The tier's config, after its tag passed the gate."""
    config = get_model_config(tier)
    normalize_tier_tag(config.name, source=TIER_ENV_VARS[tier])
    return config


class ModelRouter:
    """
    Decides which model tier gets used.

    Priority:
      1. force_tier parameter (direct requirement)
      2. EPHE_FORCE_TIER env variable (developer override)
      3. ConnectivityProbe (automatic — best available option)
    """

    def __init__(self, probe: ConnectivityProbe | None = None) -> None:
        self._probe = probe or ConnectivityProbe(
            dgx_host=os.environ.get("EPHE_DGX_HOST")
        )
        self._cached_config: ModelConfig | None = None
        self._cached_at: float = 0.0

    async def resolve(self, force_tier: str | None = None) -> ModelConfig:
        """
        Returns the best available ModelConfig.

        Args:
            force_tier: optional tier override ("offline" | "fast" | "power").
                        Overrides the probe and the env variable.

        Returns:
            ModelConfig for the chosen tier.
        """
        # 1. direct parameter override
        if force_tier:
            return _checked_tier_config(parse_tier_selector(force_tier, source="force_tier"))

        # 2. env variable override
        env_tier = os.environ.get("EPHE_FORCE_TIER")
        if env_tier:
            return _checked_tier_config(parse_tier_selector(env_tier, source="EPHE_FORCE_TIER"))

        # 3. use the cache when present AND not expired (E4: TTL)
        if (
            self._cached_config is not None
            and (time.monotonic() - self._cached_at) < PROBE_CACHE_TTL_SECONDS
        ):
            return self._cached_config

        # 4. query the probe and cache it (with a timestamp for the TTL)
        tier = await self._probe.best_available_tier()
        config = _checked_tier_config(tier)
        self._cached_config = config
        self._cached_at = time.monotonic()
        return config

    async def resolve_for_task(
        self, task_kind: str, force_tier: str | None = None
    ) -> ModelConfig:
        """G7: per-task routing — picks the tier from the task category.

        Args:
            task_kind: "light" | "medium" | "heavy" (see TASK_TIER_MAP).
                       Unknown -> "medium" (FAST) as the safe default.
            force_tier: optional hard override, always wins.

        Returns:
            ModelConfig of the chosen tier.
        """
        if force_tier:
            return _checked_tier_config(parse_tier_selector(force_tier, source="force_tier"))
        tier = TASK_TIER_MAP.get((task_kind or "").strip().lower(), ModelTier.FAST)
        return await self.resolve(force_tier=tier.value)

    def invalidate_cache(self) -> None:
        """
        Clears the cache. The next resolve() call queries the probe again.
        Useful when the network situation has changed.
        """
        self._cached_config = None
        self._cached_at = 0.0


# Loop-step routing (F4). The contract is docs/HYBRID_ROUTER_DESIGN_2026-10-11.md: a turn's
# observable state decides which tier answers a step, the caller's chosen engine stays
# untouched otherwise, and no branch reads message text.

#: The switch is opt-in and off by default: until the user turns it on, every call is
#: answered by the engine they chose. Nothing here persists a tier into the next turn.
ROUTING_ENV_SWITCH = "EPHE_ENGINE_ROUTING"
_ROUTING_ON = {"1", "on", "true", "yes"}

#: Measured 2026-10-11 over the product audit log at 77b0ce78: of 1,092 keyed turns, 888
#: executed at least once and 415 of those (46.7%) never left the SAFE category. That
#: population runs median 4 calls, p80 10, mean 8.1. The count gate sits at the median, so
#: a turn leaves the small tier where its own distribution stops being typical.
LOOP_READONLY_CALL_LIMIT = 4

#: The skill-level predicate the design names selects the small tier on 0 of those 1,092
#: turns: no skill pack declares an all-SAFE set (across every declared set: 27 MUTATING,
#: 3 DANGEROUS, 9 SAFE, 2 NETWORK). The predicate is therefore per step, over the calls the
#: turn actually made and the one it is about to make.
LOOP_TIER = ModelTier.FAST

ROUTER_REFUSAL_CODE = "router_local_tier_unreachable"
ROUTER_REFUSAL_TEXT = (
    "The local model Ephe chose for this step did not return an answer, and Ephe did not run "
    "the step on another engine on its own. Your chosen engine is unchanged, and nothing was "
    "written to disk. Choose this model as your main engine, or turn engine routing off, in "
    "Settings - Engine."
)


class LoopRoute(NamedTuple):
    """One routing decision. `tier is None` means the caller's active engine answers it."""

    tier: ModelTier | None
    reason: str
    refuse: bool = False

    @property
    def to_small_tier(self) -> bool:
        return self.tier is LOOP_TIER and not self.refuse


def routing_enabled(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get(ROUTING_ENV_SWITCH) or "").strip().lower() in _ROUTING_ON


def _is_safe(name: str) -> bool:
    from core.tools.approval import classify_tool

    return classify_tool(name).category == "SAFE"


def _is_known(name: str) -> bool:
    from core.tools.registry import TOOL_MAP

    return name in TOOL_MAP


def decide_loop_step(
    *,
    tools_used_this_turn: Iterable[str],
    next_tool: str,
    calls_so_far: int,
    is_repair: bool = False,
    closes_file_state: bool = False,
    small_tier_ready: bool = False,
    fallback_to_active: bool = False,
) -> LoopRoute:
    """Decide one loop step from observables the audit line already carries.

    Unknown names are refused the small tier for the same reason the approval gate asks
    about them: a missing entry is not evidence of safety.
    """
    if not _is_known(next_tool):
        return LoopRoute(None, "router-loop-unknown-tool")
    used = list(tools_used_this_turn)
    if any(not _is_safe(name) for name in (*used, next_tool)):
        return LoopRoute(None, "router-loop-mutating")
    if is_repair:
        return LoopRoute(None, "router-loop-repair")
    if closes_file_state:
        return LoopRoute(None, "router-loop-synthesis")
    if calls_so_far >= LOOP_READONLY_CALL_LIMIT:
        return LoopRoute(None, "router-loop-call-limit")
    if not small_tier_ready:
        # A tier is ready when one real generation came back from it. Health is never
        # consulted here: it reports engine_state=ok for an endpoint that answers 401.
        if fallback_to_active:
            return LoopRoute(None, "router-loop-fallback")
        return LoopRoute(None, ROUTER_REFUSAL_CODE, refuse=True)
    return LoopRoute(LOOP_TIER, "router-loop-readonly")


def route_loop_call(
    *,
    active: ModelConfig | None,
    enabled: bool,
    tools_used_this_turn: Iterable[str],
    next_tool: str,
    calls_so_far: int,
    is_repair: bool = False,
    closes_file_state: bool = False,
    small_tier_ready: bool = False,
    fallback_to_active: bool = False,
) -> LoopRoute:
    """Routing on top of the engine the user chose, never instead of it.

    A routing switch is not an engine choice: with nothing persisted and no engine env the
    resolution stays fail-closed, so the small tier cannot become the silent default that
    W18 removed.
    """
    if not enabled:
        return LoopRoute(None, "router-off")
    if active is None:
        raise EngineNotConfigured(
            "Engine routing is switched on but no engine is chosen, and the local tier is "
            "not a substitute for choosing one."
        )
    return decide_loop_step(
        tools_used_this_turn=tools_used_this_turn,
        next_tool=next_tool,
        calls_so_far=calls_so_far,
        is_repair=is_repair,
        closes_file_state=closes_file_state,
        small_tier_ready=small_tier_ready,
        fallback_to_active=fallback_to_active,
    )


def bind_call(route: LoopRoute, active: ModelConfig) -> ModelConfig:
    """The tier's own endpoint travels with the tier's own model.

    Reopening the half-switch is the defect this guards: a routed call that picks a tier
    must not keep the host of the tier it stepped away from.
    """
    if route.tier is None:
        return active
    return _checked_tier_config(route.tier)


# Singleton

_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    """
    Returns the app-wide ModelRouter (singleton).
    On the first call it is initialized with the env variables.

    Returns:
        ModelRouter singleton
    """
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
