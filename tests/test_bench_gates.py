"""CI performance regression gates (Phase 4 item 17 + Phase 1 item 5).

Principle (brief): TOLERANCE GATES, not absolute times — flaky-free through
  1. a warmup round before every measurement (interpreter/imports/server boot),
  2. budget = baseline + generous tolerance for slow CI runners,
  3. skip option via EPHE_BENCH_GATE=0 (debugging).

Measured values:
  - startup (CLI `--version`): baseline p50 = 60ms locally (Phase 1 DoD,
    2026-08-13, /usr/bin/time, 7 runs). Budget 150ms (100ms + 50% tolerance).
  - TTFB (time-to-first-token, SSE stream): fake provider with 50ms/token
    latency + a real uvicorn server (pattern from test_serve_openai.py /
    test_jcode_e2e.py). Expectation ~50-55ms. Budget 500ms (3x tolerance).
  - long-session memory: the 1000-message campaign (docs/STRESS_1000_2026-09-06.md
    section 4) measured server RSS 528.2 -> 663.1 MB over 1000 real messages, a net
    +0.14 MB/message (oscillating 560-660, no runaway). The 1000-turn in-process profile
    (docs/RSS_PROFILE_1000_2026-10-11.md, scripts/rss_profile_1000.py) held retained RSS at
    ~126 MB, +0.0014 MB/turn. Budget 0.5 MB/turn (~3.6x the campaign, ~357x the profile).

Determinism: fake latency via asyncio.sleep (no real LLM), a WARMUP round before
the measurement. TTFB runs through pytest-benchmark; the serial step writes that
JSON report into .benchmarks/ (gitignored) and uploads it, so the report the two
TTFB gates name is a step that exists.

Instrument decision (2026-10-11, docs/PLAN_GAP_2026-10-11.md P4-17). The startup
gate is a local-only instrument that stands down under load:
  - Local-only: the budget is one machine's p50; no percentile absorbs a shared
    runner, and the macOS leg's own median (162.7 ms) already sat past the 150 ms
    budget. `_LOCAL_BASELINE_ONLY` skips it under `GITHUB_ACTIONS`, and
    tests/test_cli_dx.py::test_cli_keeps_heavy_imports_lazy is the CI-enforceable form.
  - Stand-down: tests/timing_segment.py hands the serial-segment items a skip under an
    xdist worker or >= 2.0 runnable tasks per CPU, wired in tests/conftest.py.
  - Re-run rule: a red on a loaded box is not a finding; confirm it on an idle box
    (115.7 ms median alone, 287 ms p90 under two concurrent lanes).
  - Recording: with `EPHE_STARTUP_RECEIPT=<path>` the gate writes the window it read, but
    only under the load bar — the absolute p50 is one machine's constant, so a loaded window
    would record the queue (docs/STARTUP_GATE_LOAD_ROBUST_2026-10-11.md, "Re-baseline rule").

CI runs this file in its own serial step and excludes it from the `-n auto` leg:
measured 2026-10-09 on the owner's 10-CPU Mac, p90 startup exceeded the 150 ms budget
under `-n auto` (load ~20) and passed in 5.6 s run alone. Do not fold it back into the
parallel leg and do not raise the budgets to make it fit — the budget is the measurement.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.request import urlopen

import httpx
import pytest
import uvicorn

from server.openai import create_openai_app

# ---------------------------------------------------------------------------
# Constants (tolerance gates, evidence in the module docstring above)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

# baseline p50=60ms locally (2026-08-13) → budget 150ms (100ms + 50% CI tolerance)
STARTUP_BUDGET_S = 0.150
# TTFB with fake latency 50ms/token → expectation ~55ms → budget 500ms (3x tolerance)
TTFB_BUDGET_S = 0.500
# fake latency per token (asyncio.sleep, no real LLM)
TOKEN_LATENCY_S = 0.05
N_CHUNKS = 3
# 10 runs, not 5: with 5 samples the "p90" index resolved to runs[4] — the WORST run —
# so the gate was a maximum while its docstring promised tolerance for outliers.
N_MEASURE_RUNS = 10
# long-session memory: server RSS across the 1000-message campaign was 528.2 -> 663.1 MB
# over 1000 messages = net +0.14 MB/message (oscillating 560-660, no runaway) —
# docs/STRESS_1000_2026-09-06.md section 4. Budget 0.5 MB/turn = ~3.6x that ceiling:
# allocator noise is absorbed, an unbounded per-turn leak is not.
RSS_GROWTH_BUDGET_MB_PER_TURN = 0.5
# retained per-turn growth of the full 1000-turn in-process profile (two passes: +0.0013 and
# +0.0014 MB/turn — docs/RSS_PROFILE_1000_2026-10-11.md, scripts/rss_profile_1000.py). The gate
# below asserts it stays under the budget, so a future leak that lifts the profile and the
# budget's 357x headroom (0.5 / 0.0014) cannot drift apart unnoticed.
RSS_PROFILE_1000_MB_PER_TURN = 0.0014
# turns the memory gate drives (warmup not measured); kept small so the serial step's own
# budget still holds — measured ~22 ms/turn through the app with the engine stubbed.
N_MEMORY_TURNS = 60
N_MEMORY_WARMUP_TURNS = 10
# Startup is decided as a RATIO against a bare interpreter boot measured in the same
# window, because the wall clock carries one machine's speed: on 2026-10-11 this box at
# load1 8.6-27.5 gave boot p50 12-24ms and startup p50 81-141ms, so the ratio held at
# 4.7-7.2 while either absolute number swung by 2x. Budget 10 is that band plus about
# 40%; a heavier top-level import lifts the startup alone, which is the regression the
# gate exists for (the deterministic form of the same guarantee runs in CI regardless:
# tests/test_cli_dx.py::test_cli_keeps_heavy_imports_lazy).
STARTUP_RATIO_BUDGET = 10.0
# Beyond this many runnable tasks per CPU the ratio itself drifts, because the startup's
# imports contend harder than a bare boot (2026-10-11: ratio 18 at 6.9/CPU with no
# product change), so the verdict turns advisory there. Same bar the serial timing
# segment stands down on (tests/timing_segment.py LOAD_BAR_PER_CPU).
STARTUP_LOAD_BAR_PER_CPU = 2.0
# Set to a path and `test_startup_budget` writes the window it just read there; unset, the
# gate writes nothing and stays a pure assertion. The write happens only under the load bar,
# because the absolute p50 is one machine's constant (2026-08-13) and a loaded window would
# record the queue (docs/STARTUP_GATE_LOAD_ROBUST_2026-10-11.md, "Re-baseline rule").
STARTUP_RECEIPT_ENV = "EPHE_STARTUP_RECEIPT"
ENGINE_JSON = Path.home() / ".ephe" / "engine.json"

# skip switch (brief: EPHE_BENCH_GATE=0 for debugging)
# Read ONCE. The doubled form returned the raw string "0" from its first operand — and
# "0" is truthy — so the documented debugging switch skipped nothing (measured before
# the fix: EPHE_BENCH_GATE=0 gave "3 passed"). The comparison itself is unchanged: only
# exactly "0" turns the gates off, and an unset variable keeps them on.
# The pin lives in tests/test_bench_gate_switch.py, not here: a test inside this file
# would be skipped by the very marker it has to prove.
BENCH_GATE_ENABLED = os.environ.get("EPHE_BENCH_GATE", "1") != "0"
pytestmark = pytest.mark.skipif(
    not BENCH_GATE_ENABLED,
    reason="EPHE_BENCH_GATE=0 → Bench-Gates deaktiviert (Debugging)",
)


# ---------------------------------------------------------------------------
# Startup measurement (CLI `--version` via subprocess — the real end-to-end startup)
# ---------------------------------------------------------------------------
def _run_cli_version() -> float:
    """Measures the wall time for `ephe_cli.py --version` (interpreter+imports+parse).

    Returns seconds. `--version` prints the version and exits 0 — it needs no
    Ollama/provider, which is why it is offline-safe (CI: EPHE_MODEL=mock).
    """
    t0 = time.perf_counter()
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "ephe_cli.py"), "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
        env={**os.environ, "EPHE_OFFLINE": "1", "EPHE_MODEL": "mock"},
    )
    return time.perf_counter() - t0


def _run_interpreter_boot() -> float:
    """Wall time for a bare `python -c pass`, the spawn cost every startup run pays too.

    Measured in the same window as the startup runs, so CPU contention inflates both and
    the ratio between them stays near this machine's idle value (2026-10-11: 4.7-7.2
    across load1 8.6-27.5). Same interpreter and env as `_run_cli_version`, so only the
    import weight differs between the two child processes.
    """
    t0 = time.perf_counter()
    subprocess.run(
        [sys.executable, "-c", "pass"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
        env={**os.environ, "EPHE_OFFLINE": "1", "EPHE_MODEL": "mock"},
    )
    return time.perf_counter() - t0


# ---------------------------------------------------------------------------
# TTFB measurement (SSE stream with configurable token latency, real uvicorn)
# ---------------------------------------------------------------------------
class LatencyFakeClient:
    """Fake provider: N chunks with configurable latency (asyncio.sleep).

    No real LLM — deterministic. `chat(..., stream=True)` returns an
    AsyncIterator (pattern from tests/test_serve_openai.py).
    """

    def chat(self, model, messages, stream):  # noqa: ARG002
        async def _gen():
            for i in range(N_CHUNKS):
                await asyncio.sleep(TOKEN_LATENCY_S)
                yield {"message": {"content": f"tok{i}"}}

        return _gen()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    raise AssertionError(f"Engine nicht bereit auf Port {port}")


@pytest.fixture
def engine_base_url():
    """Starts the serve engine as a real uvicorn server with the latency fake.

    Started ONLY ONCE per test; the measured function (TTFB) instead runs
    repeatedly against the same instance. Teardown stops the server.
    """
    port = _free_port()
    patcher = patch(
        "server.openai.build_provider_client",
        lambda *a, **k: LatencyFakeClient(),
    )
    patcher.start()
    app = create_openai_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_ready(port)
    base = f"http://127.0.0.1:{port}"
    try:
        yield base
    finally:
        patcher.stop()
        server.should_exit = True
        thread.join(timeout=5)


async def _ttfb_once(base: str) -> float:
    """Measures time-to-first-token: the time until the first SSE data event (seconds)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        t0 = time.perf_counter()
        async with client.stream(
            "POST",
            f"{base}/v1/chat/completions",
            json={
                "model": "gemma4:12b",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as resp:
            assert resp.status_code == 200, f"Stream-Status {resp.status_code}"
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    ttfb = time.perf_counter() - t0
                    # validation: the first event is a real delta
                    payload = json.loads(line[len("data: "):])
                    payload["choices"][0]["delta"]
                    return ttfb
    raise AssertionError("Kein First-Data-Event empfangen")


def _ttfb_sync(base: str) -> float:
    return asyncio.run(_ttfb_once(base))


def _percentile(sorted_runs: list[float], q: float) -> float:
    """Nearest-rank percentile (p90 of 10 = the 9th run, not the worst)."""
    return sorted_runs[max(0, math.ceil(q * len(sorted_runs)) - 1)]


def startup_gate_verdict(
    startup_s: float,
    calibration_s: float,
    load_per_cpu: float,
    ratio_budget: float = STARTUP_RATIO_BUDGET,
    absolute_budget: float = STARTUP_BUDGET_S,
    load_bar: float = STARTUP_LOAD_BAR_PER_CPU,
) -> tuple[str, str]:
    """One measured window to a (verdict, reason) pair, the load-tolerant startup gate.

    The ratio decides first: startup and the interpreter boot are two subprocess spawns
    on this box, so CPU contention moves both and leaves the ratio near its idle value
    (2026-10-11: 4.7-7.2 across load1 8.6-27.5), while the startup side alone carries the
    import weight a regression adds. Above `load_bar` tasks per CPU the ratio drifts too
    and the window turns advisory at any width, which is the regime the serial timing
    segment stands the whole segment down in. A calm box over budget with the ratio in
    band asks for a re-baseline, since the whole box (boot included) is then slower than
    the 2026-08-13 reference.
    """
    ratio = startup_s / calibration_s
    if startup_s <= absolute_budget and ratio <= ratio_budget:
        return "pass", f"ratio {ratio:.2f}; absolute {startup_s * 1000:.0f}ms within budget"
    if load_per_cpu >= load_bar:
        return "advisory", (
            f"startup {startup_s * 1000:.0f}ms against a {calibration_s * 1000:.0f}ms boot "
            f"(ratio {ratio:.2f}) at {load_per_cpu:.1f} tasks/CPU, above {load_bar:.1f}: the "
            "startup's imports contend harder than a bare boot here, so both numbers describe "
            "the queue"
        )
    if ratio > ratio_budget:
        return "fail", (
            f"startup/calibration ratio {ratio:.2f} above {ratio_budget:.2f}: startup "
            f"{startup_s * 1000:.0f}ms against a {calibration_s * 1000:.0f}ms interpreter boot, "
            "so the width is import weight the boot does not carry"
        )
    return "rebaseline", (
        f"absolute {startup_s * 1000:.0f}ms over {absolute_budget * 1000:.0f}ms at "
        f"{load_per_cpu:.1f} tasks/CPU, ratio {ratio:.2f} in band: the whole box "
        f"(boot {calibration_s * 1000:.0f}ms) is slower than the reference"
    )


def startup_number_is_recordable(
    load_per_cpu: float, *, load_bar: float = STARTUP_LOAD_BAR_PER_CPU
) -> bool:
    """Only a calm box produces the absolute number the re-baseline rule re-records."""
    return load_per_cpu < load_bar


def _named_engine(path: Path = ENGINE_JSON) -> dict:
    """The persisted engine, read so a recorded number carries which box config it came from.

    The wall time does not vary with it: `_run_cli_version` boots with `EPHE_MODEL=mock` and
    the `--version` path imports no provider, so the engine is recorded as provenance only.
    """
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"source": str(path), "named": False}
    return {
        "source": str(path),
        "named": True,
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "api_url": cfg.get("api_url"),
    }


def record_startup_number(
    receipt_path: Path,
    *,
    startup_p50_s: float,
    startup_p90_s: float,
    startup_mean_s: float,
    boot_p50_s: float,
    load1: float,
    load_per_cpu: float,
    verdict: str,
    reason: str,
    n_runs: int,
    engine_path: Path = ENGINE_JSON,
) -> tuple[bool, str]:
    """Write the startup window to `receipt_path`, or refuse on a busy box.

    A loaded box writes nothing: the absolute p50 there is the queue running through the
    machine rather than the product's startup, so writing it would launder load into a baseline
    (docs/STARTUP_GATE_LOAD_ROBUST_2026-10-11.md, "Re-baseline rule"). The ratio rides along
    because it is the load-tolerant half of the same window, and the gate's own verdict is
    recorded so the number and its decision stay together.
    """
    if not startup_number_is_recordable(load_per_cpu):
        return False, (
            f"load {load_per_cpu:.2f}/CPU >= {STARTUP_LOAD_BAR_PER_CPU:.1f}: the absolute p50 "
            "describes the queue, not the product — record on a calm box"
        )
    receipt = {
        "kind": "startup-gate-number",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_runs": n_runs,
        "startup_p50_s": round(startup_p50_s, 6),
        "startup_p90_s": round(startup_p90_s, 6),
        "startup_mean_s": round(startup_mean_s, 6),
        "boot_p50_s": round(boot_p50_s, 6),
        "ratio": round(startup_p50_s / boot_p50_s, 4),
        "startup_budget_s": STARTUP_BUDGET_S,
        "ratio_budget": STARTUP_RATIO_BUDGET,
        "load1": round(load1, 3),
        "load_per_cpu": round(load_per_cpu, 4),
        "load_bar_per_cpu": STARTUP_LOAD_BAR_PER_CPU,
        "verdict": verdict,
        "reason": reason,
        "engine": _named_engine(engine_path),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return True, f"p50={startup_p50_s * 1000:.1f}ms ratio={receipt['ratio']} -> {receipt_path}"


# The startup gate is wall-clock and its baseline is ONE machine (p50=60ms, 2026-08-13).
# On shared runners the whole distribution shifts — the macOS leg measured p50=162.7ms,
# i.e. the median itself above the 150ms budget — so no percentile can absorb that and
# the gate would report a regression the product does not have. The deterministic form
# of the same guarantee runs in CI regardless:
# tests/test_cli_dx.py::test_cli_keeps_heavy_imports_lazy.
_LOCAL_BASELINE_ONLY = pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") == "true",
    reason="wall-clock budget against a single-machine baseline; the lazy-import gate "
    "in test_cli_dx.py is the version CI can enforce",
)


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------
@_LOCAL_BASELINE_ONLY
def test_startup_budget(benchmark):
    """Gate: CLI startup (`--version`) p90 < 150ms (baseline p50=60ms, 2026-08-13).

    Design (flaky-free, issue #15):
      1. the warmup round is NOT measured (interpreter/imports are warm),
      2. ``benchmark()`` serves ONLY the JSON report (.benchmarks/, gitignored) —
         with ``--benchmark-disable`` the function just keeps running once,
         the gate itself is decoupled from that,
      3. the GATE checks the **p90** of N measurements instead of the mean — a
         mean has no load defence: under parallel system load (bench/server in
         the background) a single slow run pushed past the budget (#15). With
         N=10 the nearest-rank p90 is the 9th run: one slow run is absorbed, a
         systematic regression is not. (Until 2026-10-09 N was 5, where the same
         formula returned runs[4] — the maximum — while this text promised 10%
         tolerance.)
      4. the DECISION is the ratio p50(startup)/p50(interpreter boot) read with the load
         per CPU of the moment (startup_gate_verdict): CPU contention moves both spawns,
         the startup side alone carries the import weight, so a busy box cannot flag the
         product (2026-10-09: p90 347ms at load1 8.6 with no product change). Above
         STARTUP_LOAD_BAR_PER_CPU tasks per CPU the ratio drifts too and the window turns
         advisory, which is the regime the serial timing segment stands down in; a calm
         box over budget with the ratio in band asks for a re-baseline against a slower
         machine.
      5. with `EPHE_STARTUP_RECEIPT=<path>` the window is recorded to that path, but only on a
         calm box (load/CPU < STARTUP_LOAD_BAR_PER_CPU): that is when the absolute p50 is a
         number the re-baseline rule may re-record, and a loaded window would record the queue.
    """
    _run_cli_version()  # warmup (not measured)
    _run_interpreter_boot()  # warmup for the calibration probe, same reason

    # JSON report (decoupled from the gate — runs even with --benchmark-disable)
    benchmark(_run_cli_version)

    # GATE: manual measurement; the decision is the ratio of the two medians (see
    # startup_gate_verdict), so a loaded box moves both sides and stays green (#15, P4-17)
    runs = sorted(_run_cli_version() for _ in range(N_MEASURE_RUNS))
    boots = sorted(_run_interpreter_boot() for _ in range(N_MEASURE_RUNS))
    p50 = _percentile(runs, 0.50)
    p90 = _percentile(runs, 0.90)
    mean = sum(runs) / len(runs)
    boot_p50 = _percentile(boots, 0.50)
    load1 = os.getloadavg()[0]
    load_per_cpu = load1 / max(1, os.cpu_count() or 1)
    verdict, reason = startup_gate_verdict(p50, boot_p50, load_per_cpu)
    print(f"\n  [startup] p50={p50 * 1000:.1f}ms p90={p90 * 1000:.1f}ms mean={mean * 1000:.1f}ms  "
          f"(Budget {STARTUP_BUDGET_S * 1000:.0f}ms)")
    print(f"  [startup] boot p50={boot_p50 * 1000:.1f}ms ratio={p50 / boot_p50:.2f} "
          f"load={load_per_cpu:.2f}/CPU -> {verdict}")

    # The recording boundary, pinned inline: the write below and anything that reads a
    # recorded number share this rule, and a fifth function would change the four-gate skip
    # count test_bench_gate_switch.py holds (the memory gate pins its profile here the same way).
    assert startup_number_is_recordable(STARTUP_LOAD_BAR_PER_CPU - 1e-9)
    assert not startup_number_is_recordable(STARTUP_LOAD_BAR_PER_CPU)
    receipt_path = os.environ.get(STARTUP_RECEIPT_ENV)
    if receipt_path:
        recorded, note = record_startup_number(
            Path(receipt_path),
            startup_p50_s=p50, startup_p90_s=p90, startup_mean_s=mean, boot_p50_s=boot_p50,
            load1=load1, load_per_cpu=load_per_cpu, verdict=verdict, reason=reason,
            n_runs=N_MEASURE_RUNS,
        )
        print(f"  [startup] receipt {'written' if recorded else 'refused'}: {note}")

    assert verdict != "fail", f"Startup-Regression: {reason}"


def test_ttfb_budget(benchmark, engine_base_url):
    """Gate: TTFB (time-to-first-token) mean < 500ms (fake latency 50ms/token).

    The uvicorn server is already running (engine_base_url fixture). As in
    test_startup_budget: ``benchmark()`` only as a JSON report, the GATE is a
    manual measurement (N_MEASURE_RUNS runs, warmup before) → deterministic in
    every mode.
    """
    base = engine_base_url
    _ttfb_sync(base)  # warmup: first request (handshake, not measured)

    # JSON report (decoupled from the gate)
    benchmark(lambda: _ttfb_sync(base))

    # GATE: manual, deterministic measurement
    runs = [_ttfb_sync(base) for _ in range(N_MEASURE_RUNS)]
    runs.sort()
    p50 = runs[len(runs) // 2]
    mean = sum(runs) / len(runs)
    print(f"\n  [ttfb] p50={p50 * 1000:.1f}ms mean={mean * 1000:.1f}ms  "
          f"(Budget {TTFB_BUDGET_S * 1000:.0f}ms)")
    assert mean < TTFB_BUDGET_S, (
        f"TTFB-Regression: mean {mean * 1000:.1f}ms > Budget "
        f"{TTFB_BUDGET_S * 1000:.0f}ms (Fake-Latenz {TOKEN_LATENCY_S * 1000:.0f}ms/Token)"
    )


def test_ttfb_deterministic_within_tolerance(engine_base_url):
    """Sanity: the TTFB stays stable (spread < budget) — no flakiness signal.

    N_MEASURE_RUNS runs, max < budget. Catches systematic latency jumps without
    insisting on exact times.
    """
    base = engine_base_url
    _ttfb_sync(base)  # warmup
    runs = sorted(_ttfb_sync(base) for _ in range(N_MEASURE_RUNS))
    p50 = runs[len(runs) // 2]
    worst = runs[-1]
    print(f"\n  [ttfb-spread] p50={p50 * 1000:.1f}ms worst={worst * 1000:.1f}ms")
    assert worst < TTFB_BUDGET_S, f"TTFB-Spread zu groß: worst {worst * 1000:.1f}ms"


# Long-session memory gate (docs/PLAN_GAP_2026-10-11.md P1-5)
def test_long_session_memory_budget(tmp_path, monkeypatch):
    """GATE: per-turn RSS growth of a long session < RSS_GROWTH_BUDGET_MB_PER_TURN.

    Deterministic proxy for the 1000-message campaign: one session_id is driven through
    POST /api/chat with the engine stubbed, so the route persists every turn into the
    `rest-<id>` mirror and feeds the growing history back on the next turn — the same
    path the campaign hammered. Warmup first, then the process RSS is sampled before and
    after N_MEMORY_TURNS turns. BUDGET is the campaign ceiling + tolerance rather than the
    loop's own noise floor: the loop holds no engine state, so its own measured growth is
    ~0 and the budget catches a per-turn leak while absorbing allocator swing.
    """
    psutil = pytest.importorskip("psutil", reason="psutil is a main dependency")

    # The documented 1000-turn profile (docs/RSS_PROFILE_1000_2026-10-11.md, measured by
    # scripts/rss_profile_1000.py) must sit under the budget this gate enforces. Pinned here
    # rather than in a test of its own: a second function would change the four-gate skip
    # count tests/test_bench_gate_switch.py asserts.
    assert RSS_PROFILE_1000_MB_PER_TURN < RSS_GROWTH_BUDGET_MB_PER_TURN, (
        f"1000-turn profile {RSS_PROFILE_1000_MB_PER_TURN}MB/turn is not under the "
        f"{RSS_GROWTH_BUDGET_MB_PER_TURN}MB/turn budget (scripts/rss_profile_1000.py)"
    )

    # Isolated memory/session state — the env the REST-history tests pin.
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))

    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    from fastapi.testclient import TestClient

    from core import multi_session as ms
    from server.main import create_app

    process = psutil.Process(os.getpid())
    session_turn = {"model": "gemma4:12b", "session_id": "bench-memory"}

    with (
        TestClient(create_app()) as client,
        patch("server.routes.chat.react_loop", new=AsyncMock(return_value="ok")),
    ):
        for i in range(N_MEMORY_WARMUP_TURNS):
            response = client.post("/api/chat", json={**session_turn, "message": f"warmup {i}"})
            assert response.status_code == 200, response.text
        before_mb = process.memory_info().rss / 1048576.0
        for i in range(N_MEMORY_TURNS):
            response = client.post("/api/chat", json={**session_turn, "message": f"turn {i}"})
            assert response.status_code == 200, response.text
        after_mb = process.memory_info().rss / 1048576.0

    # Not vacuous: the route really persisted this long session (2 messages per turn).
    stored = ms.load_messages("rest-bench-memory")
    assert len(stored) >= 2 * (N_MEMORY_WARMUP_TURNS + N_MEMORY_TURNS)

    growth_per_turn = (after_mb - before_mb) / N_MEMORY_TURNS
    print(f"\n  [memory] {before_mb:.1f}MB -> {after_mb:.1f}MB over {N_MEMORY_TURNS} "
          f"turns = {growth_per_turn:+.3f}MB/turn "
          f"(Budget {RSS_GROWTH_BUDGET_MB_PER_TURN:.2f}MB/turn)")
    assert growth_per_turn < RSS_GROWTH_BUDGET_MB_PER_TURN, (
        f"Long-session memory regression: {growth_per_turn:+.3f}MB/turn > budget "
        f"{RSS_GROWTH_BUDGET_MB_PER_TURN:.2f}MB/turn (campaign +0.14MB/message, "
        f"profile +{RSS_PROFILE_1000_MB_PER_TURN}MB/turn)"
    )
