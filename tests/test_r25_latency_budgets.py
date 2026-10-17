"""R25: latency budgets as executable tests (Roadmap R25.5).

Budgets (docs/LATENCY_BUDGETS.md):
- Deterministic routing detection < 50 ms (p95) — the non-mutating path that
  runs BEFORE the engine/tools for each message (a SkillLoader hit).
  R36: the fast path was dropped; the detection layer is now
  `SkillLoader.resolve_for_message` (trigger + intent rules, no LLM).
- Session full-text search over 1k messages < 50 ms (p95) — see
  test_r25_session_search.py::test_search_budget_1000_messages_under_50ms_p95.
- TTFT p95 (LIVE, DGX): only with a reachable engine endpoint — otherwise SKIP
  (no fake green). Measures the time until the first stream chunk.
"""

from __future__ import annotations

import os
import time
from urllib.error import URLError

import pytest

from core.skills import SkillLoader

_PROMPTS = [
    "Erstelle eine Zusammenfassung meines Projekts mit allen Modulen",
    "Write a summary of my project with all modules",
    "Erstelle eine PDF über Künstliche Intelligenz im Schwarzwald",
    "Analyse die Tabelle: Name, Alter; Anna, 34; Ben, 27",
    "was kannst du?",
]


def _routing_detection_ms(loader: SkillLoader, prompt: str) -> float:
    """The non-mutating deterministic routing path (a SkillLoader hit)."""
    start = time.perf_counter()
    loader.resolve_for_message(prompt)
    return (time.perf_counter() - start) * 1000


def test_skill_routing_detection_under_50ms_p95() -> None:
    loader = SkillLoader()
    loader.load_all()  # warm the TTL cache (imports/regex compile amortise)
    # Warmup
    for p in _PROMPTS:
        _routing_detection_ms(loader, p)

    samples: list[float] = []
    for _ in range(40):
        for p in _PROMPTS:
            samples.append(_routing_detection_ms(loader, p))
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 50, f"Skill-Routing-Erkennung zu langsam: p95={p95:.2f} ms (Budget 50 ms)"


# TTFT p95 (LIVE, only with a reachable engine — no fake green)

# W18: the live endpoint comes from the env only (no private hostname in the repo).
DGX_BASE = (os.environ.get("EPHE_DGX_BASE") or "").strip().rstrip("/")
DGX_MODEL = os.environ.get("EPHE_DGX_MODEL", "")


def _endpoint_reachable() -> bool:
    import urllib.request

    if not (DGX_BASE and DGX_MODEL):
        return False
    key = os.environ.get("EPHE_DGX_KEY") or os.environ.get("EPHE_OPENAI_COMPAT_API_KEY") or ""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        req = urllib.request.Request(f"{DGX_BASE}/models", headers=headers)
        with urllib.request.urlopen(req, timeout=2):
            return True
    except (URLError, OSError, TimeoutError):
        return False


@pytest.mark.skipif(
    not _endpoint_reachable(),
    reason=(
        "Kein Live-Endpoint konfiguriert/erreichbar — setze EPHE_DGX_BASE + "
        "EPHE_DGX_MODEL (+ EPHE_DGX_KEY): SKIP (Latenz-Marker ist ein Live-Budget, kein Fake)."
    ),
)
def test_ttft_p95_under_budget_live() -> None:
    """TTFT p95 over 5 short prompts (max_tokens=16, temperature=0)."""
    import json as _json
    import urllib.request

    ttfts: list[float] = []
    for i in range(5):
        payload = _json.dumps(
            {
                "model": DGX_MODEL,
                "messages": [{"role": "user", "content": f"Sag nur: Test {i}"}],
                "max_tokens": 16,
                "temperature": 0.0,
                "stream": True,
            }
        ).encode()
        req = urllib.request.Request(
            f"{DGX_BASE}/chat/completions",
            data=payload,
            headers={"Authorization": "Bearer smoke", "Content-Type": "application/json"},
        )
        start = time.perf_counter()
        first_chunk: float | None = None
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("data:") and "[DONE]" not in line:
                    if first_chunk is None:
                        first_chunk = (time.perf_counter() - start) * 1000
                    break  # the first chunk is enough for TTFT
        if first_chunk is not None:
            ttfts.append(first_chunk)

    assert len(ttfts) == 5
    ttfts.sort()
    p95 = ttfts[-1]
    # Honest budget for the local/vLLM path: 3000 ms TTFT p95 (the engine
    # cold start dominates; budget progress in docs/LATENCY_BUDGETS.md).
    assert p95 < 3000, f"TTFT p95 = {p95:.0f} ms über Budget (3000 ms)"
