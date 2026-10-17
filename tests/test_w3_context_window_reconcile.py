"""W3-44 — the tier-table context window against a live engine probe, reconciled.

Two sources can name the window of the active engine: the static tier table in
``core.model_config`` (OFFLINE / FAST / POWER) and a probe of the running engine
(``max_model_len`` in ``/v1/models``; the health surface's ``context_length``
where the model list carries no window field). ``resolve_context_window``
reconciles them in one order — env override > probed value > tier table >
documented legacy 8192 — so the numbers the meter shows can never come from two
sources at once.

The shipped POWER row was reconciled against a live probe of the DGX engine on
2026-10-11: it answered ``context_length=262144`` on ``/health`` while its
``/v1/models`` entry carried no window field, so the static 131072 was stale.
The hermetic cases pin the shipped row and the precedence rule; the live case
runs only when a real endpoint is configured (``EPHE_DGX_BASE`` / ``EPHE_DGX_MODEL``)
and skips otherwise — no fake green, the same rule as
``tests/test_channel_injection_guard_live.py``.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

from core.model_config import (
    LEGACY_CONTEXT_WINDOW,
    TIER_CONTEXT_WINDOWS,
    ModelTier,
    resolve_context_window,
)

#: What the shipped POWER engine reported to a live probe on 2026-10-11
#: (DGX /health: context_length=262144; /v1/models carried no window field).
LIVE_PROBED_POWER_WINDOW = 262144

#: Live endpoint — env only. The repo holds neither a private hostname nor a token.
_LIVE_BASE = (os.environ.get("EPHE_DGX_BASE") or "").strip().rstrip("/")
_LIVE_MODEL = (os.environ.get("EPHE_DGX_MODEL") or "").strip()
_KEY = os.environ.get("EPHE_DGX_KEY") or os.environ.get("EPHE_OPENAI_COMPAT_API_KEY") or ""
_HEADERS = {"Authorization": f"Bearer {_KEY}"} if _KEY else {}

_WINDOW_FIELDS = ("max_model_len", "context_length", "max_context_length")


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    """The probe cache is module state — leave it exactly as it was found."""
    from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

    saved = dict(_CONTEXT_WINDOW_CACHE)
    _CONTEXT_WINDOW_CACHE.clear()
    yield
    _CONTEXT_WINDOW_CACHE.clear()
    _CONTEXT_WINDOW_CACHE.update(saved)


def _configure_power(monkeypatch, tag: str) -> None:
    """Seed a POWER tier that carries a tag — a tier is only named by the user."""
    import core.model_config as m

    monkeypatch.setattr(
        m,
        "TIER_MAP",
        {ModelTier.POWER: m.ModelConfig(name=tag, tier=ModelTier.POWER)},
    )


def _seed_probe(monkeypatch, model: str, base_url: str, window: int) -> None:
    """Put a probed window into the cache under the active engine's key."""
    from core import model_provider as mp
    from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", mp.ModelProviderConfig(
        provider="openai_compatible",
        model=model,
        base_url=base_url,
        label="DGX",
        offline_capable=False,
        requires_internet=True,
    ))
    _CONTEXT_WINDOW_CACHE[(base_url, model)] = window


def test_shipped_power_row_is_reconciled_with_the_live_probe():
    """GIVEN the tier table
    WHEN the rows are read
    THEN POWER carries the window the live engine probe reported (262144), the
    local rows keep their Modelfile defaults, and no row equals the legacy 8192."""
    assert TIER_CONTEXT_WINDOWS[ModelTier.POWER] == LIVE_PROBED_POWER_WINDOW
    assert TIER_CONTEXT_WINDOWS[ModelTier.OFFLINE] == 32768
    assert TIER_CONTEXT_WINDOWS[ModelTier.FAST] == 16384
    assert LEGACY_CONTEXT_WINDOW == 8192
    assert LEGACY_CONTEXT_WINDOW not in TIER_CONTEXT_WINDOWS.values()


def test_probe_reconciles_over_the_tier_row(monkeypatch):
    """GIVEN the active engine's probe reports a window other than the tier row
    WHEN the window is resolved
    THEN the probe wins (source 'engine') and the tier row is only the fallback."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    _configure_power(monkeypatch, "gemma4:26b")
    _seed_probe(monkeypatch, "gemma4:26b", "http://127.0.0.1:8000", 32768)

    assert resolve_context_window("gemma4:26b") == (32768, "engine")

    from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

    _CONTEXT_WINDOW_CACHE.clear()
    assert resolve_context_window("gemma4:26b") == (LIVE_PROBED_POWER_WINDOW, "tier")


def test_env_override_still_beats_probe_and_row(monkeypatch):
    """GIVEN EPHE_CONTEXT_WINDOW is set while a probe is also cached
    WHEN the window is resolved
    THEN the manual override wins — the top of the reconciliation order."""
    monkeypatch.setenv("EPHE_CONTEXT_WINDOW", "999999")
    _configure_power(monkeypatch, "gemma4:26b")
    _seed_probe(monkeypatch, "gemma4:26b", "http://127.0.0.1:8000", 32768)

    assert resolve_context_window("gemma4:26b") == (999999, "env")


def _probe_live_window(base: str, model: str) -> int | None:
    """The window the live engine reports: /v1/models first, then /health.

    A model list without a window field is the shipped tensorfold engine's shape;
    vLLM names the value ``max_model_len`` there, its health surface
    ``context_length``.
    """
    root = base[:-3].rstrip("/") if base.endswith("/v1") else base
    try:
        req = urllib.request.Request(f"{base}/models", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for entry in data.get("data", []):
            if isinstance(entry, dict) and entry.get("id") == model:
                for field in _WINDOW_FIELDS:
                    value = entry.get(field)
                    if isinstance(value, int) and value > 0:
                        return value
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        pass
    try:
        req = urllib.request.Request(f"{root}/health", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            value = json.loads(resp.read().decode("utf-8")).get("context_length")
        return value if isinstance(value, int) and value > 0 else None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


_LIVE_WINDOW = _probe_live_window(_LIVE_BASE, _LIVE_MODEL) if (_LIVE_BASE and _LIVE_MODEL) else None

_live_only = pytest.mark.skipif(
    _LIVE_WINDOW is None,
    reason=(
        "No live endpoint configured/reachable — set EPHE_DGX_BASE + "
        "EPHE_DGX_MODEL (optional EPHE_DGX_KEY): SKIP, no fake green."
    ),
)


@_live_only
def test_live_engine_window_reconciles_with_the_tier_table(monkeypatch):
    """GIVEN a reachable engine whose probe names its window
    WHEN the window is resolved
    THEN the resolver returns the probed number (the probe beats the table) and
    the POWER fallback never promises more than the engine actually serves."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    _seed_probe(monkeypatch, _LIVE_MODEL, _LIVE_BASE, _LIVE_WINDOW)

    assert resolve_context_window(_LIVE_MODEL) == (_LIVE_WINDOW, "engine")
    # The static row must not over-promise the live engine; a stale-low row is
    # conservative, a stale-high row would let the trim pass the real ceiling.
    assert TIER_CONTEXT_WINDOWS[ModelTier.POWER] <= _LIVE_WINDOW
