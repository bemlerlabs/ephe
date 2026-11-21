"""The HTTP surface over the usage ledger: GET /api/usage/summary.

The status-bar cost popover reads this route, so the day window, the aggregated
totals and both pricing outcomes are pinned end to end: a maintained price table
in engine.json yields a USD cost, an absent or unusable one leaves pricing and
cost null. The device folder and the ledger are bent onto tmp_path first, so no
test touches the developer's ~/.ephe. Beyond the two table outcomes this also
pins the missing-attribute read (`getattr(choice, "pricing", None)` on a choice
that never carried a price) and the in-only one-sided table (the mirror of the
out-only case).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A private device folder and ledger; the real ~/.ephe is never read."""
    import core.engine_config as ec
    import core.usage_ledger as UL

    cfg = tmp_path / "ephe"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)
    ledger = tmp_path / "usage.jsonl"
    monkeypatch.setattr(UL, "default_store", lambda: ledger)
    return SimpleNamespace(cfg=cfg, ledger=ledger)


def _client():
    from fastapi.testclient import TestClient

    from server.main import create_app

    return TestClient(create_app())


def _row(ledger, *, in_tokens, out_tokens, cached=0, estimated=False, days_ago=0):
    from core import usage_ledger as UL

    UL.record_usage(
        in_tokens=in_tokens,
        out_tokens=out_tokens,
        cached_tokens=cached,
        estimated=estimated,
        now=datetime.now() - timedelta(days=days_ago),
        store=ledger,
    )


def _save_pricing(env, pricing):
    from core.engine_config import EngineChoice, save_engine_config

    save_engine_config(
        EngineChoice(provider="local_ollama", model="gemma4:12b", pricing=pricing),
        env.cfg / "engine.json",
    )


def test_empty_ledger_reports_zero_totals(env):
    """GIVEN no ledger WHEN the summary is read THEN 30 empty days and no cost."""
    with _client() as c:
        r = c.get("/api/usage/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["days"] == 30
    assert body["totals"] == {"in": 0, "out": 0, "cached": 0, "est_turns": 0, "turns": 0}
    assert len(body["by_day"]) == 30
    assert body["pricing"] is None
    assert body["cost"] is None


def test_summary_aggregates_the_ledger(env):
    """GIVEN two turns today WHEN read THEN totals and the est share come through."""
    _row(env.ledger, in_tokens=1000, out_tokens=200, cached=300)
    _row(env.ledger, in_tokens=500, out_tokens=100, estimated=True)
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["totals"] == {"in": 1500, "out": 300, "cached": 300, "est_turns": 1, "turns": 2}
    assert body["by_day"][0]["turns"] == 2
    assert body["by_day"][-1]["turns"] == 0


def test_days_query_bounds_the_window(env):
    """GIVEN a turn ten days back WHEN a 7-day window is asked THEN it is excluded."""
    _row(env.ledger, in_tokens=11, out_tokens=1)
    _row(env.ledger, in_tokens=99, out_tokens=0, days_ago=10)
    with _client() as c:
        seven = c.get("/api/usage/summary", params={"days": 7}).json()
        thirty = c.get("/api/usage/summary", params={"days": 30}).json()
    assert seven["days"] == 7 and len(seven["by_day"]) == 7
    assert seven["totals"]["in"] == 11
    assert thirty["days"] == 30 and len(thirty["by_day"]) == 30
    assert thirty["totals"]["in"] == 110


@pytest.mark.parametrize("days,status", [(0, 422), (366, 422), (1, 200), (365, 200)])
def test_days_is_validated(env, days, status):
    with _client() as c:
        r = c.get("/api/usage/summary", params={"days": days})
    assert r.status_code == status, r.text
    if status == 200:
        assert r.json()["days"] == days


def test_pricing_table_yields_usd_cost(env):
    """GIVEN a maintained price table WHEN read THEN in/out/total USD are computed."""
    _row(env.ledger, in_tokens=1_500, out_tokens=300)
    _save_pricing(env, {"in_per_m": 3.0, "out_per_m": 15.0})
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["pricing"] == {"in_per_m": 3.0, "out_per_m": 15.0}
    assert body["cost"] == {"in_usd": 0.0045, "out_usd": 0.0045, "total_usd": 0.009}


def test_one_sided_price_table_zeroes_the_missing_side(env):
    """GIVEN only out_per_m WHEN read THEN in_per_m reads 0.0 and the cost stays finite."""
    _row(env.ledger, in_tokens=1_000_000, out_tokens=2_000_000)
    _save_pricing(env, {"out_per_m": 10.0})
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["pricing"] == {"in_per_m": 0.0, "out_per_m": 10.0}
    assert body["cost"] == {"in_usd": 0.0, "out_usd": 20.0, "total_usd": 20.0}


def test_zeroed_price_table_reads_as_no_pricing(env):
    """GIVEN a table with 0.0 on both sides WHEN read THEN pricing and cost stay null."""
    _row(env.ledger, in_tokens=500, out_tokens=500)
    _save_pricing(env, {"in_per_m": 0.0, "out_per_m": 0.0})
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["pricing"] is None
    assert body["cost"] is None
    assert body["totals"]["in"] == 500


def test_non_dict_price_table_is_ignored(env):
    """GIVEN a scalar where a price table belongs WHEN read THEN no cost is claimed."""
    _save_pricing(env, "cheap")
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["pricing"] is None
    assert body["cost"] is None


def test_damaged_engine_json_degrades_to_no_pricing(env):
    """GIVEN a corrupt engine.json WHEN read THEN the summary still answers 200."""
    (env.cfg / "engine.json").write_text("{not json", encoding="utf-8")
    with _client() as c:
        r = c.get("/api/usage/summary")
    assert r.status_code == 200, r.text
    assert r.json()["pricing"] is None


def test_config_reader_raising_degrades_to_no_pricing(env, monkeypatch):
    """GIVEN the config reader raises WHEN read THEN the route answers without a cost."""
    import core.engine_config as ec

    def boom(*_args, **_kwargs):
        raise RuntimeError("engine.json unreadable")

    monkeypatch.setattr(ec, "load_engine_config", boom)
    with _client() as c:
        r = c.get("/api/usage/summary")
    assert r.status_code == 200, r.text
    assert r.json()["pricing"] is None
    assert r.json()["cost"] is None


def test_choice_without_a_price_table_is_no_pricing(env, monkeypatch):
    """GIVEN a real choice that carries no `pricing` field WHEN read THEN no cost is claimed.

    `_pricing` reads the field with `getattr(choice, "pricing", None)`. The empty
    config exercises `choice is None`, which short-circuits past that getattr; a
    configured choice that lacks the attribute is the other side and is reached
    by nothing else, so an engine choice that predates pricing must read as "no
    price" rather than raise.
    """
    import core.engine_config as ec

    monkeypatch.setattr(ec, "load_engine_config", lambda: object())
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["pricing"] is None
    assert body["cost"] is None


def test_only_in_price_zeroes_the_out_side(env):
    """GIVEN only in_per_m WHEN read THEN out_per_m reads 0.0 and the cost stays finite.

    Mirror of `test_one_sided_price_table_zeroes_the_missing_side`: that one
    supplies out_per_m only (the `or 0` on the in side), this one supplies
    in_per_m only, so the missing out side is the one that must read 0.0.
    """
    _row(env.ledger, in_tokens=2_000_000, out_tokens=1_000_000)
    _save_pricing(env, {"in_per_m": 10.0})
    with _client() as c:
        body = c.get("/api/usage/summary").json()
    assert body["pricing"] == {"in_per_m": 10.0, "out_per_m": 0.0}
    assert body["cost"] == {"in_usd": 20.0, "out_usd": 0.0, "total_usd": 20.0}
