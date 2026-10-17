"""
◑ Ephe – Model Configuration
core/model_config.py

Defines the three model tiers of the hybrid architecture. A tier is a routing class
(device-cheap, local workhorse, remote heavy hitter), not a model: the tag that fills
it comes from the user's environment and nothing here supplies one
(owner decision 2026-10-11).

  EPHE_OFFLINE_MODEL  tier "offline"
  EPHE_FAST_MODEL     tier "fast"
  EPHE_POWER_MODEL    tier "power"
  EPHE_DGX_HOST       (default: localhost:11434)
  EPHE_FORCE_TIER     (optional: offline | fast | power)

Ephe – Bad Liebenzell, Black Forest
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


# Tier Enum

class ModelTier(str, Enum):
    """The three stages of the EPHE hybrid architecture."""
    OFFLINE = "offline"   # runs on the device, no network needed
    FAST    = "fast"      # local, responsive
    POWER   = "power"     # remote backend, maximum strength


# ModelConfig Dataclass

@dataclass(frozen=True)
class ModelConfig:
    """
    Immutable configuration for one model.

    frozen=True: no accidental overwriting possible.
    All fields stay read-only after creation.
    """
    name: str           # Ollama model tag the user configured, "" when unnamed
    tier: ModelTier     # Which tier this config belongs to
    host: str = "localhost:11434"  # Ollama host (local or DGX)

    @property
    def is_local(self) -> bool:
        """True when the Ollama server runs locally."""
        return self.host == "localhost:11434"

    @property
    def is_remote(self) -> bool:
        """True when the Ollama server runs on a remote host (e.g. DGX)."""
        return not self.is_local

    @property
    def base_url(self) -> str:
        """HTTP base URL for the Ollama client."""
        return f"http://{self.host}"


# ── Tier → Config mapping (env-only, an unset tier stays unnamed) ──────────

def _build_tier_map() -> dict[ModelTier, ModelConfig]:
    """
    Builds TIER_MAP from the environment.
    Called on module import — and again on importlib.reload().

    A tier with no tag configured stays unnamed: the router that reaches it has to
    be told which model to use, and no RAM size of this machine decides that for the
    user.
    """
    dgx_host = os.environ.get("EPHE_DGX_HOST", "localhost:11434")

    return {
        ModelTier.OFFLINE: ModelConfig(
            name=os.environ.get("EPHE_OFFLINE_MODEL", "").strip(),
            tier=ModelTier.OFFLINE,
            host="localhost:11434",  # Offline runs ALWAYS locally
        ),
        ModelTier.FAST: ModelConfig(
            name=os.environ.get("EPHE_FAST_MODEL", "").strip(),
            tier=ModelTier.FAST,
            host="localhost:11434",  # Fast runs locally
        ),
        ModelTier.POWER: ModelConfig(
            name=os.environ.get("EPHE_POWER_MODEL", "").strip(),
            tier=ModelTier.POWER,
            host=dgx_host,           # Power runs on DGX (or locally as a fallback)
        ),
    }


# Built on import — stays stable for the rest of the runtime
TIER_MAP: dict[ModelTier, ModelConfig] = _build_tier_map()


def get_model_config(tier: ModelTier) -> ModelConfig:
    """
    Returns the ModelConfig for the given tier.

    Args:
        tier: ModelTier.OFFLINE | FAST | POWER

    Returns:
        ModelConfig with name, tier, host, is_local, base_url
    """
    return TIER_MAP[tier]


# Context window per tier (P0-1)

#: Documented legacy case without any probe (the window the pre-2026-10-11 shipped
#: default carried; a 12B local Modelfile with num_ctx left at its build default).
LEGACY_CONTEXT_WINDOW = 8192

#: Windows of the shipped model classes, the POWER row reconciled with a live
#: probe of the running engine on 2026-10-11: the DGX engine reports
#: context_length=262144 (its /v1/models entry carried no window field, the health
#: surface did; engines that send it name `max_model_len` there). Ollama delivers
#: no window in /api/tags, so OFFLINE/FAST stay at their documented Modelfile
#: defaults. This table is the fallback next to the engine probe, never a
#: substitute: a probed value overrides the row (see `resolve_context_window`).
TIER_CONTEXT_WINDOWS: dict[ModelTier, int] = {
    ModelTier.OFFLINE: 32768,    # device tier — Modelfile default num_ctx
    ModelTier.FAST: 16384,       # local workhorse tier
    ModelTier.POWER: 262144,     # remote tier (DGX/vLLM), live-probed
}


def context_window_for_model(model: str) -> int | None:
    """Window from the tier table (exact name, otherwise prefix check).

    An unnamed tier matches nothing: "" is every model's prefix.
    """
    name = (model or "").strip()
    if not name:
        return None
    for tier, cfg in TIER_MAP.items():
        if not cfg.name:
            continue
        if cfg.name == name:
            return TIER_CONTEXT_WINDOWS[tier]
    for tier, cfg in TIER_MAP.items():
        if not cfg.name:
            continue
        if cfg.name.split(":")[0] == name.split(":")[0]:
            return TIER_CONTEXT_WINDOWS[tier]
    return None


def resolve_context_window(model: str = "") -> tuple[int, str]:
    """Context window for inference — precedence: env > engine probe > tier > legacy.

    The same order as `GET /api/context/budget` (server/routes/context.py),
    but without a network round trip: on the inference path only the already
    filled probe cache counts, so the turn stays deterministic and non-blocking.

    Returns:
        (window_tokens, source) with source in {"env","engine","tier","legacy"}.
    """
    raw = (os.environ.get("EPHE_CONTEXT_WINDOW") or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value, "env"

    active_model = model
    try:
        from core.model_provider import get_active_provider
        from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

        active = get_active_provider()
        if active is not None:
            active_model = active_model or active.model or ""
            cached = _CONTEXT_WINDOW_CACHE.get((active.base_url, active.model))
            if cached and int(cached) > 0:
                return int(cached), "engine"
    except Exception:
        pass

    tier_window = context_window_for_model(active_model)
    if tier_window:
        return tier_window, "tier"
    return LEGACY_CONTEXT_WINDOW, "legacy"
