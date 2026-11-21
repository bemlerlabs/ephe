"""Skill-Index performance baseline (the fast-path tests were removed in R36).

build_skill_index must stay well under the context budget for small models;
the baseline pins both cold (uncached loader) and warm (cached loader)
latencies.
"""
from __future__ import annotations

import time

from core.skills import SkillLoader, BUILTIN_SKILLS_DIR


def test_build_skill_index_warm_latency():
    loader = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    loader.load_all()  # warm the TTL cache
    samples: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        loader.build_skill_index()
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 10.0, f"warm build_skill_index p95 too slow: {p95:.2f} ms"


def test_build_skill_index_cold_latency():
    loader = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    t0 = time.perf_counter()
    loader.build_skill_index()
    cold_ms = (time.perf_counter() - t0) * 1000.0
    assert cold_ms < 50.0, f"cold build_skill_index too slow: {cold_ms:.2f} ms"


def test_build_skill_index_covers_enabled_skills():
    loader = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    index = loader.build_skill_index()
    assert index.strip(), "skill index must not be empty"
