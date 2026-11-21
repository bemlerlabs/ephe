"""PERF-BE-REST: the engine probe is single-flight, cached and bounded.

The health poll runs on a timer. Before this, every poll whose 15 s entry had
expired started its own two-second probe, so a dead engine cost the poll the full
timeout again and again (and concurrent pollers each paid one). These tests pin
the new contract: one probe per endpoint, a stale answer goes out while that probe
refreshes it, a cold answer is bounded and reports ``busy``, and a failed refresh
replaces the stale success instead of leaving it standing.

The probe thread parks on an event instead of sleeping, so "did the caller wait
for it" is an observable fact and not a wall-clock guess.
"""
from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import patch

import httpx
import pytest

from server.routes import health

_URL = "http://engine.test/v1"
_STALE = (True, "engine reachable", ["m"], "ok", False)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(health, "_ENGINE_CACHE", {})
    monkeypatch.setattr(health, "_ENGINE_INFLIGHT", {})
    yield


def _dead(*_args, **_kwargs):
    raise httpx.ConnectError("connection refused")


def _slowed(seconds: float):
    def _probe(*_args, **_kwargs):
        time.sleep(seconds)
        raise httpx.ConnectError("connection refused")

    return _probe


def test_a_dead_endpoint_is_probed_once_within_the_ttl():
    calls: list[int] = []

    def _counted(*args, **kwargs):
        calls.append(1)
        return _dead(*args, **kwargs)

    async def _run():
        with patch.object(health.httpx, "get", _counted):
            first = await health._quick_engine_status(_URL, "m")
            second = await health._quick_engine_status(_URL, "m")
        return first, second

    first, second = asyncio.run(_run())
    assert first[3] == "unreachable"
    assert "connection refused" in first[1]
    assert second == first
    assert len(calls) == 1, "the second poll paid for another probe"


def test_concurrent_cold_calls_share_one_probe():
    calls: list[int] = []

    def _counted(*args, **kwargs):
        calls.append(1)
        return _slowed(0.15)(*args, **kwargs)

    async def _run():
        with patch.object(health.httpx, "get", _counted):
            return await asyncio.gather(
                *(health._quick_engine_status(_URL, "m") for _ in range(5))
            )

    answers = asyncio.run(_run())
    assert len(calls) == 1, "five pollers started five probes"
    assert all(answer == answers[0] for answer in answers)


def test_a_stale_answer_goes_out_while_the_refresh_probe_is_still_running():
    release = threading.Event()

    def _parked(*_args, **_kwargs):
        release.wait(5)
        raise httpx.ConnectError("connection refused")

    async def _run():
        health._ENGINE_CACHE[_URL] = (time.monotonic() - health._ENGINE_TTL_S - 1, _STALE)
        with patch.object(health.httpx, "get", _parked):
            answer = await health._quick_engine_status(_URL, "m")
            # No clock: a caller that awaited the refresh would have returned the
            # probe's answer, and the probe cannot answer until `release` is set.
            assert answer == _STALE
            task = health._ENGINE_INFLIGHT[_URL]
            assert not task.done(), "the stale answer waited for the refresh"
            release.set()
            await task
            await asyncio.sleep(0.02)
        return health._ENGINE_CACHE[_URL][1]

    refreshed = asyncio.run(_run())
    assert refreshed[3] == "unreachable", "a failed refresh kept the stale success"


def test_a_cold_probe_that_does_not_answer_reads_as_busy(monkeypatch):
    monkeypatch.setattr(health, "_PROBE_WAIT_S", 0.05)
    release = threading.Event()

    def _parked(*_args, **_kwargs):
        release.wait(5)
        raise httpx.ConnectError("connection refused")

    async def _run():
        with patch.object(health.httpx, "get", _parked):
            answer = await health._quick_engine_status(_URL, "m")
            assert answer[3] == "busy", "an unanswered cold probe blocked the caller"
            task = health._ENGINE_INFLIGHT[_URL]
            release.set()
            await task
            await asyncio.sleep(0.02)

    asyncio.run(_run())


def test_shutdown_drops_inflight_probes():
    async def _run():
        with patch.object(health.httpx, "get", _slowed(0.2)):
            health._start_engine_probe(_URL, "m")
            assert health._ENGINE_INFLIGHT
            await health.aclose_engine_probes()
            assert health._ENGINE_INFLIGHT == {}

    asyncio.run(_run())
