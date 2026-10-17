#!/usr/bin/env python3
"""Server RSS profile across a 1000-turn session (WE-36).

Measurement behind tests/test_bench_gates.py::test_long_session_memory_budget. That gate
drives 60 turns and reads one before/after delta; the campaign it stands in for ran 1000
messages. This script drives the full 1000-turn session and samples the server process RSS
the whole way, so the budget has a measured curve behind it rather than a single gap.

Deterministic and in-process: the engine is stubbed (`server.routes.chat.react_loop`), so
the curve describes server-side accumulation alone — the REST mirror write, the post-turn
worker and the growing history fed back each turn. No network, no real LLM. Every writable
Ephe path is redirected into a throwaway home before the server imports bind them.

Run:
    .venv/bin/python scripts/rss_profile_1000.py                    # 1000 turns, sample/25
    .venv/bin/python scripts/rss_profile_1000.py --turns 100 --sample-every 10

Writes .benchmarks/rss_profile_1000.json (gitignored) and prints the documented number.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # invoked by path, so core.* is not importable otherwise

#: The session length the 2026-09-06 campaign ran and the gate's budget is set against.
N_TURNS = 1000
N_WARMUP_TURNS = 50
SAMPLE_EVERY = 10
OUT_DEFAULT = REPO / ".benchmarks" / "rss_profile_1000.json"

REST_SESSION_ID = "rss-profile"


def isolate(home: Path) -> None:
    """Point every writable Ephe path at `home`, before the server imports bind them.

    A standalone run gets none of the pytest autouse isolation (tests/conftest.py), so a
    profile without this would read and write the developer's real ~/.ephe.
    """
    env = {
        "HOME": str(home),
        "EPHE_CONFIG_DIR": str(home / "ephe"),
        "EPHE_ARTIFACTS_DB": str(home / "artifacts.db"),
        "EPHE_MEMORY_DIR": str(home / "chroma_db"),
        "EPHE_SESSIONS_DIR": str(home / "sessions"),
        "EPHE_PROFILE_PATH": str(home / "user_profile.json"),
        "EPHE_CORRECTIONS_PATH": str(home / "corrections.md"),
        "EPHE_FEEDBACK_DIR": str(home / "feedback"),
        "EPHE_SKILLS_DIR": str(home / "skills"),
        "EPHE_PERSONA_DIR": str(home / "persona"),
        "EPHE_CELL_WORK_ROOT": str(home / "cell-work"),
        "EPHE_SCHEDULE_JOBS": str(home / "scheduled_jobs.json"),
        "EPHE_SCHEDULE_RESULTS": str(home / "schedule_results.json"),
        "EPHE_WORKSPACE": str(home / "ws"),
        "EPHE_MEMORY_PROVIDER": "chroma",
        "EPHE_MODEL_PROVIDER": "local_ollama",
        "EPHE_MODEL": "gemma4:12b",
        "EPHE_SETUP_MODE": "0",
    }
    for key, value in env.items():
        os.environ[key] = value


def summarize(samples: list[tuple[int, float]], turns: int, retained_mb: float) -> dict:
    """Turn a list of (turn, RSS MB) points into the documented numbers.

    `retained_mb` is the RSS after a final gc.collect() while the server is still running,
    so the profile separates memory the process keeps from allocator/transient swing the
    samples carry. `slope_mb_per_turn` is the least-squares trend across every sample: the
    number a per-turn leak would move, which the gate's budget bounds.
    """
    baseline = samples[0][1]
    final = samples[-1][1]
    mid = next((mb for turn, mb in samples if turn >= turns // 2), final)
    net = final - baseline
    xs = [turn for turn, _ in samples]
    ys = [mb for _, mb in samples]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = 0.0 if denom == 0 else sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return {
        "turns": turns,
        "baseline_mb": round(baseline, 1),
        "final_mb": round(final, 1),
        "net_mb": round(net, 1),
        "mb_per_turn": round(net / turns, 4),
        "slope_mb_per_turn": round(slope, 4),
        "peak_mb": round(max(mb for _, mb in samples), 1),
        "min_mb": round(min(mb for _, mb in samples), 1),
        "first_half_mb": round(mid - baseline, 1),
        "second_half_mb": round(final - mid, 1),
        "retained_mb": round(retained_mb, 1),
        "net_retained_mb": round(retained_mb - baseline, 1),
        "mb_per_turn_retained": round((retained_mb - baseline) / turns, 4),
        "samples": [[turn, round(mb, 1)] for turn, mb in samples],
    }


def run_profile(turns: int, warmup: int, sample_every: int, home: Path) -> dict:
    """Drive one REST session for `turns` turns and profile the server process RSS."""
    isolate(home)

    import psutil  # imported after isolation: it holds no Ephe state, order is incidental
    from fastapi.testclient import TestClient


    from core import multi_session as ms
    from server.main import create_app

    process = psutil.Process(os.getpid())

    def rss_mb() -> float:
        return process.memory_info().rss / 1048576.0

    session_turn = {"model": "gemma4:12b", "session_id": REST_SESSION_ID}
    samples: list[tuple[int, float]] = []
    started = time.perf_counter()

    from unittest.mock import AsyncMock, patch

    with (
        TestClient(create_app()) as client,
        patch("server.routes.chat.react_loop", new=AsyncMock(return_value="ok")),
    ):
        for i in range(warmup):
            response = client.post("/api/chat", json={**session_turn, "message": f"warmup {i}"})
            assert response.status_code == 200, response.text
        gc.collect()
        samples.append((0, rss_mb()))
        for turn in range(1, turns + 1):
            response = client.post("/api/chat", json={**session_turn, "message": f"turn {turn}"})
            assert response.status_code == 200, response.text
            if turn % sample_every == 0:
                samples.append((turn, rss_mb()))
        gc.collect()
        retained_mb = rss_mb()
        elapsed_s = time.perf_counter() - started

    from core.auto_memory import capture_enabled

    stored = len(ms.load_messages(f"rest-{REST_SESSION_ID}"))
    profile = summarize(samples, turns, retained_mb)
    profile.update(
        {
            "warmup_turns": warmup,
            "sample_every": sample_every,
            "stored_messages": stored,
            "capture_enabled": capture_enabled(),
            "elapsed_s": round(elapsed_s, 1),
            "ms_per_turn": round(elapsed_s * 1000 / turns, 1),
            "isolated_home": str(home),
        }
    )
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Server RSS profile across a 1000-turn session.")
    parser.add_argument("--turns", type=int, default=N_TURNS)
    parser.add_argument("--warmup", type=int, default=N_WARMUP_TURNS)
    parser.add_argument("--sample-every", type=int, default=SAMPLE_EVERY)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="rss-profile-") as tmp:
        profile = run_profile(args.turns, args.warmup, args.sample_every, Path(tmp) / "home")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    print(
        f"\n  [rss-profile] {profile['baseline_mb']:.1f}MB -> {profile['final_mb']:.1f}MB "
        f"over {profile['turns']} turns = {profile['mb_per_turn']:+.4f}MB/turn "
        f"(least-squares trend {profile['slope_mb_per_turn']:+.4f}MB/turn)"
    )
    print(
        f"  [rss-profile] retained after gc {profile['retained_mb']:.1f}MB "
        f"({profile['mb_per_turn_retained']:+.4f}MB/turn), peak {profile['peak_mb']:.1f}MB, "
        f"min {profile['min_mb']:.1f}MB"
    )
    print(
        f"  [rss-profile] {profile['stored_messages']} messages stored, "
        f"capture_enabled={profile['capture_enabled']}, "
        f"{profile['ms_per_turn']:.1f}ms/turn"
    )
    print(f"  [rss-profile] profile -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
