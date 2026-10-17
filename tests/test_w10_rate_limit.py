"""W10 pins: the rate limit for the shell pollers (429-free) and the inventory.

Measured actual state (2026-09-09): the frontend polls metrics (5s), health/tasks
(10s), git/schedule (30s) — with chat/stream the load sat close to the old budget of
60/60s and returned 429 in the dev tools (stale displays).
"""
from __future__ import annotations

from fastapi import FastAPI

from server import middleware as mw_mod
from server.middleware import RateLimitMiddleware

RATE_LIMIT_EXEMPT_PATHS = mw_mod._RATE_LIMIT_EXEMPT_PATHS


def test_poller_paths_sind_vollstaendig_exempt():
    """Every shell poller lives in the exempt inventory (no budget consumption)."""
    required = {
        "/api/health",
        "/api/system/metrics",
        "/api/tasks",
        "/api/schedule",
        "/api/settings",
        "/api/skills",
        "/api/git/info",
        "/api/context/budget",
        "/api/model/providers",
    }
    assert required <= set(RATE_LIMIT_EXEMPT_PATHS)


def test_budget_deckt_sekundentakt_der_shell():
    """240/60s covers the cadence even with panels open at the same time (PWA + tablet)."""
    app = FastAPI()
    mw = RateLimitMiddleware(app)
    assert mw.max_requests == 240
    assert mw.window == 60


def test_exempt_pfad_zehlt_nicht_gegen_das_budget():
    """An exempt path consumes no slots — the budget applies only to expensive routes."""
    app = FastAPI()
    mw = RateLimitMiddleware(app, max_requests=2, window=60)
    assert "/api/health" in RATE_LIMIT_EXEMPT_PATHS
    assert "/api/artifacts" not in RATE_LIMIT_EXEMPT_PATHS
