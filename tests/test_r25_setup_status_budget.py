"""R25: the setup gate's answer must not buy a fresh engine round trip per call.

The gate is the first thing the PWA asks (`GET /api/setup/status`, App.tsx) and it used to
pay a synchronous upstream probe — `GET {engine}/v1/models`, a new TLS handshake each time —
on *every* call. Measured 2026-10-14 against the real engine behind the product server:

    _setup_provider_dict()   316-533 ms   (3 runs, one process)
    _setup_candidates()        0.1 ms    (the local half, beside it)
    GET /api/health              3-14 ms  (the live engine truth, polled every 10 s)
    GET /api/setup/status      320-375 ms (5 curl runs against 127.0.0.1:8765)

So the same fact was bought twice per cold load (the gate and the composer each had a call)
at ~320 ms each, while the one live reading of the engine was already 20-100x cheaper.

What is asserted here is the shape of the fix, and neither assertion reads a clock: a repeat
call inside the TTL does not probe again, and the handler is a plain function so a cold
probe can never run on the event loop. A wall-clock ceiling would have to live in the serial
segment (`tests/test_timing_assertion_guard.py`), and these two properties are what make the
number hold in the first place.
"""
from __future__ import annotations

import inspect
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolated engine.json — never the owner's ~/.ephe."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    import server.routes.settings as st

    monkeypatch.setattr(st, "_setup_probe_cache", {})
    yield
    import core.model_provider as mp

    mp._ACTIVE_OVERRIDE = None


def _persist_remote_engine() -> None:
    from core.engine_config import EngineChoice, OPENAI_COMPAT, save_engine_config

    save_engine_config(
        EngineChoice(
            provider=OPENAI_COMPAT,
            model="qwen38-27b",
            api_url="https://engine.example/v1",
        )
    )


def _counting_probe(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replaces the upstream probe: counts the round trips that would have been made."""
    import server.routes.settings as st

    seen: list[str] = []

    def fake_probe(url: str):
        seen.append(url)
        return True, ["qwen38-27b"]

    monkeypatch.setattr(st, "_probe_remote", fake_probe)
    return seen


def test_repeat_call_inside_the_ttl_probes_the_engine_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """GIVEN a configured remote engine
    WHEN  GET /api/setup/status is answered twice inside the TTL
    THEN  the engine was probed once and both answers carry the same reachability."""
    import server.routes.settings as st

    _persist_remote_engine()
    seen = _counting_probe(monkeypatch)

    first = st._setup_provider_dict()
    second = st._setup_provider_dict()

    assert seen == ["https://engine.example/v1"], "the probe ran once for two calls"
    assert first["reachable"] is True
    assert second["reachable"] == first["reachable"]
    assert second["available_models"] == first["available_models"]


def test_the_probe_runs_again_once_the_ttl_has_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    """GIVEN a probe answer inside its TTL
    WHEN  the clock moves past `_SETUP_PROBE_TTL_S`
    THEN  the next call probes again — the memo collapses repeats, it does not hide a change.

    The clock is moved, never slept through: the assertion stays independent of the run queue.
    """
    import server.routes.settings as st

    _persist_remote_engine()
    seen = _counting_probe(monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    st._setup_provider_dict()
    st._setup_provider_dict()
    assert len(seen) == 1

    clock[0] += st._SETUP_PROBE_TTL_S + 0.5
    st._setup_provider_dict()

    assert len(seen) == 2


def test_the_gate_route_does_not_run_the_probe_on_the_event_loop() -> None:
    """The handler stays a plain function, never a coroutine function.

    `_probe_remote` is a synchronous urllib call with a 4 s timeout. As an `async def`
    handler that call ran on the event loop, so one app load froze every other in-flight
    request for the probe's duration — a streamed answer included. FastAPI runs a `def`
    handler in the threadpool, which is where a blocking probe belongs. This test names the
    property so a later "make it async" edit has to argue with it.
    """
    import server.routes.settings as st

    assert not inspect.iscoroutinefunction(st.get_setup_status)
