"""Ephe – usage billing API (wave 3): 7/30-day consumption + cost.

Working backwards: the cost monitor in the status bar shows the turn/session —
this endpoint delivers the day-aggregated view (today/7/30)
for the status popover. Cost only when engine.json has `pricing` maintained
(USD per 1M tokens); otherwise cost=null and the UI shows plain quantities.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from core.usage_ledger import summarize

router = APIRouter(tags=["Usage"])


def _pricing() -> dict | None:
    try:
        from core.engine_config import load_engine_config

        choice = load_engine_config()
        pricing = getattr(choice, "pricing", None) if choice else None
        if isinstance(pricing, dict) and (pricing.get("in_per_m") or pricing.get("out_per_m")):
            return {
                "in_per_m": float(pricing.get("in_per_m") or 0),
                "out_per_m": float(pricing.get("out_per_m") or 0),
            }
    except Exception:
        pass
    return None


@router.get("/usage/summary")
async def usage_summary(days: int = Query(30, ge=1, le=365)) -> dict:
    """Day aggregate for the last N days, from the content-free usage ledger."""
    report = summarize(days)
    pricing = _pricing()
    cost = None
    if pricing:
        t = report["totals"]
        cost = {
            "in_usd": round(t["in"] / 1_000_000 * pricing["in_per_m"], 6),
            "out_usd": round(t["out"] / 1_000_000 * pricing["out_per_m"], 6),
            "total_usd": round(
                t["in"] / 1_000_000 * pricing["in_per_m"]
                + t["out"] / 1_000_000 * pricing["out_per_m"],
                6,
            ),
        }
    return {"days": report["days"], "totals": report["totals"], "by_day": report["by_day"], "pricing": pricing, "cost": cost}
