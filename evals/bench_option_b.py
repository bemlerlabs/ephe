"""Option-B benchmark — TAU/GAIA-inspired mini-mapping (60 tasks × 3 reps = 180 reps).

Implements docs/benchmark-mapping.md §5 inside the existing product harness:
every task runs against the real /api/chat/stream endpoint with the real
tool set, scored by deterministic assertions only (no LLM judge):

  T1-T17  family `tau`       policy/reliability tasks (policy files +
                             scripted multi-turn user; end-state + ledger
                             assertions)                                  L2-L4
  G1-G17  family `gaia`      grounded research with the GAIA `FINAL
                             ANSWER:` convention (type-normalized exact
                             match)                                       L2-L4
  W1-W16  family `endstate`  end-state tasks over the local filesystem    L2-L4
  K1-K10  family `endstate`  long horizon: 10+ tool calls over a
                             120-document corpus, 25-call tool budget      L5

Scoring: per task, pass^3 = all 3 repetitions must pass (TAU reliability
semantics). A rep the engine never answered carries `error_class: "engine"` and
is excluded from its task's rep set, so the task falls out of pass^3 through the
incomplete-set rule instead of counting as an agent loss. Run manifests land in
/tmp/bench-option-b/runs/ (never in the repo; EPHE_BENCH_DIR relocates that tree).
Usage:

    python evals/bench_option_b.py            # full matrix
    python evals/bench_option_b.py --only T2,G3 --reps 1
    python evals/bench_option_b.py --score    # score existing manifests

Requires the product server on :8765 (EPHE_BENCH_PORT moves the port, EPHE_BENCH_BASE the whole
base URL) with a configured engine (autonomous
headless mode, see server/routes/chat.py::_sandbox_cb / R37). Before the first
rep the harness runs one probe turn; if the engine behind the surface does not
answer, the run stops with a precondition error and records nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.request
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_code_address import address as _code_address, cohort_state as _cohort_state, of as _code_of  # noqa: E402
from bench_manifests import manifest_paths as _manifest_paths  # noqa: E402
from bench_workspace import SurfaceNotIsolated, require_isolated_surface, run_workspace  # noqa: E402

#: The surface the bench measures. EPHE_BENCH_BASE names it outright; EPHE_BENCH_PORT moves only
#: the port off the owner's :8765, so a parallel run points at its own server. The accept harness
#: (evals/accept_k2k5_w7.sh) exports EPHE_BENCH_BASE; a bare invocation reads the port here.
BENCH_PORT = os.environ.get("EPHE_BENCH_PORT") or "8765"
BASE = os.environ.get("EPHE_BENCH_BASE") or f"http://127.0.0.1:{BENCH_PORT}"


class EngineUnavailable(RuntimeError):
    """No engine answers behind the surface: plumbing state, so there is no result to record."""


def _active_model() -> str:
    """The bench measures the engine that actually runs.

    A hard-coded model-name default is not a measurement but a wish: when the
    configured provider does not answer for that model, the rounds say nothing
    about Ephe. Measured 2026-10-09 — a run whose engine was switched away
    mid-flight recorded 18 reps that never reached a model, and the point scored
    `7/15` with six of those fifteen tasks lost to the engine. So an unanswered
    rep is classed `engine` and excluded, and a run with no answering engine
    stops in `_preflight` below.
    EPHE_BENCH_MODEL overrides this, so calibration runs on a fixed engine stay
    possible.
    """
    try:
        with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as response:
            return str(json.load(response).get("active_model") or "").strip()
    except Exception:  # noqa: BLE001 — without a server the bench is unusable
        return ""


MODEL = os.environ.get("EPHE_BENCH_MODEL") or _active_model()
# EPHE_BENCH_DIR moves the whole scratch tree, so a falsification run can be proven
# against its own directories instead of writing into a live matrix.
SCRATCH = Path(os.environ.get("EPHE_BENCH_DIR") or "/tmp/bench-option-b")
RUNS = SCRATCH / "runs"
WORKSPACE = run_workspace(SCRATCH)
OUTPUT_DIR = SCRATCH / "out"
DEADLINE_S = 420.0

# ── N7: price table per 1M tokens (USD). Precedence: env > engine.json.pricing
# (N8b, persisted per model) > the provider's own published price > default. Default:
# the public DashScope prices of the qwen-flash branch. This way the USD billing
# follows a model change.
_OR_PRICING_CACHE: dict[str, tuple[float, float] | None] = {}


def _published_openrouter_price(model: str) -> tuple[float, float] | None:
    """The provider's own USD-per-token figure, from the keyless public model list.

    A `:free` model has no pricing block in engine.json, and falling through to the
    qwen-flash default would print a cost that was never paid — on the one axis
    (price per solved task) that a public table is compared on.
    """
    if not model:
        return None
    if model in _OR_PRICING_CACHE:
        return _OR_PRICING_CACHE[model]
    out: tuple[float, float] | None = None
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=10) as r:
            data = json.load(r).get("data") or []
        for m in data:
            if m.get("id") == model:
                pr = m.get("pricing") or {}
                p_in = float(pr.get("prompt") or 0) * 1e6
                p_out = float(pr.get("completion") or 0) * 1e6
                out = (p_in, p_out)
                break
    except Exception:  # noqa: BLE001 — an unreachable price list degrades, it does not stop
        out = None
    _OR_PRICING_CACHE[model] = out
    return out


def _engine_pricing_choice() -> tuple[float | None, float | None, str | None]:
    try:
        from core.engine_config import load_engine_config as _lec

        choice = _lec()
    except Exception:  # noqa: BLE001 — pricing falls through to the table below
        return None, None, None
    if choice is None:
        return None, None, None
    pr = getattr(choice, "pricing", None)
    if isinstance(pr, dict) and pr.get("in_per_m") is not None and pr.get("out_per_m") is not None:
        return float(pr["in_per_m"]), float(pr["out_per_m"]), "engine.json"
    url = str(getattr(choice, "api_url", "") or "")
    if "openrouter.ai" in url:
        published = _published_openrouter_price(str(getattr(choice, "model", "") or ""))
        if published:
            return published[0], published[1], "openrouter-published"
    return None, None, None


def _resolve_pricing() -> tuple[float, float, str]:
    p_in = os.environ.get("EPHE_BENCH_PRICE_IN_PER_M")
    p_out = os.environ.get("EPHE_BENCH_PRICE_OUT_PER_M")
    if p_in is not None and p_out is not None:
        return float(p_in), float(p_out), "env"
    e_in, e_out, source = _engine_pricing_choice()
    if source:
        return e_in, e_out, source
    return 0.05, 0.40, "default"


PRICE_IN_PER_M, PRICE_OUT_PER_M, PRICING_SOURCE = _resolve_pricing()

FINAL = "FINAL ANSWER:"

#: N6: difficulty band per task (L2 = N4 core, L3 = N5 expansion,
#: L4 = N6 new work with structural pressure near the 10-tool ceiling).
LEVELS = {
    **{t: "L2" for t in ("T1", "T2", "T3", "T4", "G1", "G2", "G3", "G4", "W1", "W2")},
    **{t: "L3" for t in ("T5", "T6", "T7", "G5", "G6", "G7", "W3", "W4", "W5", "W6")},
    "T8": "L3", "T9": "L4", "T10": "L3", "T11": "L3", "T12": "L4",
    "T13": "L3", "T14": "L4", "T15": "L3", "T16": "L4", "T17": "L3",
    "G8": "L3", "G9": "L4", "G10": "L3", "G11": "L3", "G12": "L4",
    "G13": "L3", "G14": "L4", "G15": "L4", "G16": "L3", "G17": "L4",
    "W7": "L3", "W8": "L4", "W9": "L3", "W10": "L4", "W11": "L3",
    "W12": "L4", "W13": "L3", "W14": "L4", "W15": "L3", "W16": "L4",
    # N9b: L5 = long horizon (10+ tool calls, retrieval over a 120-document corpus)
    "K1": "L5", "K2": "L5", "K3": "L5", "K4": "L5", "K5": "L5",
    "K6": "L5", "K7": "L5", "K8": "L5", "K9": "L5", "K10": "L5",
}


def _fixture_hash() -> str:
    """sha256 over all fixture files (name+content), 12 hex characters."""
    h = hashlib.sha256()
    for f in sorted(WORKSPACE.glob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def _fixture_files() -> list[str]:
    """The names on disk before the rep starts moving them.

    Taken at rep start on purpose: the workspace is what the task reads, and an
    argument pointing at a name that never existed there is a finding about the call,
    not about the directory afterwards.
    """
    return sorted(f.name for f in WORKSPACE.glob("*") if f.is_file())


# ── Fixtures ───────────────────────────────────────────────────────────────

#: Repair targets: the fixtures a rep has to fix in place, mapped task id -> (name, body).
#:
#: They ship malformed on purpose (W9 and T13 are error-recovery tasks; K4's 119 is one
#: broken document inside the 120-document corpus). `write_fixtures` writes them once,
#: outside the rep loop, so without a per-rep reset only rep 1 meets the broken form —
#: reps 2..3 would read the file rep 1 already repaired and pass on that.
BROKEN_FIXTURES: dict[str, tuple[str, str]] = {
    "T13": ("t13_cfg.json", '{"a": 1 "b": 2}'),  # broken: comma missing -> 1+2=3
    "W9": ("w9_broken.json", '{"n": 7 "m": 35}'),  # after repair n+m=42
    "K4": ("kdoc_119.json", '{"id": 119 "val": 119 "next": null}'),
}


def write_fixtures() -> None:
    """Deterministic fixture set (§5 fixture budget: ~6 files + 2 policies)."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "policy.md").write_text(
        "# Booking policy (v3)\n"
        "1. Confirmed bookings are FIXED after 18:00 UTC on the start day.\n"
        "2. A change request for a fixed booking MUST be refused. Offer a new\n"
        "   booking instead; never modify the fixed record.\n"
        "3. Refunds for bookings older than 30 days are paid as store credit\n"
        "   only — never as cash refund.\n",
        encoding="utf-8",
    )
    (WORKSPACE / "bookings.json").write_text(
        json.dumps(
            [
                {"id": "BK-1001", "guest": "Ada", "status": "confirmed", "start": "2026-09-01"},
                {"id": "BK-1002", "guest": "Grace", "status": "open", "start": "2026-10-02"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (WORKSPACE / "offers.json").write_text(
        json.dumps(
            [
                {"id": "OF-A", "room": "pine", "night": "2026-11-05", "price": 210},
                {"id": "OF-B", "room": "fir", "night": "2026-11-05", "price": 180},
                {"id": "OF-C", "room": "fir", "night": "2026-11-06", "price": 150},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (WORKSPACE / "g1_a.txt").write_text("total_capacity = 84 seats\n", encoding="utf-8")
    (WORKSPACE / "g1_b.txt").write_text("reserved = 12 seats\n", encoding="utf-8")
    rows = []
    for name, vals in {
        "north.csv": [3, 9, 12],
        "south.csv": [10, 20, 30],
        "west.csv": [5, 5, 7],
    }.items():
        body = "month,revenue\n" + "\n".join(
            f"2026-{i + 1:02d},{v}" for i, v in enumerate(vals)
        )
        (WORKSPACE / name).write_text(body + "\n", encoding="utf-8")
        rows.append((name, sum(vals)))
    (WORKSPACE / "_truth.json").write_text(
        json.dumps({"sums": {n: s for n, s in rows}, "total": sum(s for _, s in rows)}),
        encoding="utf-8",
    )
    # ── N5 expansion fixtures (L2/L3) — each task owns its data ──────────────
    (WORKSPACE / "bookings_t5.json").write_text(
        json.dumps(
            [{"id": "BK-2001", "guest": "Ada", "status": "open", "start": "2026-10-02"}],
            indent=2,
        ),
        encoding="utf-8",
    )
    (WORKSPACE / "offers_t6.json").write_text(
        json.dumps(
            [
                {"id": "OF-X", "room": "a", "night": "2026-12-01", "price": 190},
                {"id": "OF-Y", "room": "b", "night": "2026-12-01", "price": 190},
                {"id": "OF-Z", "room": "c", "night": "2026-12-02", "price": 100},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    # G5: distinct months counted once -> 10 + 20 + 30 = 60
    (WORKSPACE / "g5_a.csv").write_text(
        "month,revenue\n2026-01,10\n2026-02,20\n", encoding="utf-8"
    )
    (WORKSPACE / "g5_b.csv").write_text(
        "month,revenue\n2026-02,20\n2026-03,30\n", encoding="utf-8"
    )
    # G6: weighted mean of per-file totals by row count -> (60*3 + 100*2)/(3+2) = 76
    (WORKSPACE / "g6_a.csv").write_text(
        "month,revenue\n2026-01,10\n2026-02,20\n2026-03,30\n", encoding="utf-8"
    )
    (WORKSPACE / "g6_b.csv").write_text(
        "month,revenue\n2026-01,40\n2026-02,60\n", encoding="utf-8"
    )
    # W3: union of keys -> {k1, k2, k3}
    (WORKSPACE / "a.json").write_text(
        json.dumps({"k1": 1, "k2": 2}, indent=2), encoding="utf-8"
    )
    (WORKSPACE / "b.json").write_text(
        json.dumps({"k2": 2, "k3": 3}, indent=2), encoding="utf-8"
    )
    # W4: rename-chain seed
    (WORKSPACE / "a.txt").write_text("seed\n", encoding="utf-8")
    # W6: open items sorted by id -> [2, 3]
    (WORKSPACE / "todos_seed.json").write_text(
        json.dumps(
            [
                {"id": 3, "status": "open"},
                {"id": 1, "status": "done"},
                {"id": 2, "status": "open"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    # ── N6 fixtures (L3/L4) — five capability classes, each >=4 tasks ────────
    # Error recovery: T8, T13, T16, G13, W9, W13
    (WORKSPACE / "t8_mirror.csv").write_text(
        "value\n10\n15\n20\n", encoding="utf-8"  # sum 45
    )
    (WORKSPACE / "t13_cfg.json").write_text(
        BROKEN_FIXTURES["T13"][1], encoding="utf-8"  # broken: comma missing -> 1+2=3
    )
    (WORKSPACE / "t16_mirror.json").write_text(
        json.dumps({"vals": [8, 13, 21]}, indent=2), encoding="utf-8"  # sum 42
    )
    (WORKSPACE / "g13_mirror.json").write_text(
        json.dumps({"total": 77}, indent=2), encoding="utf-8"
    )
    (WORKSPACE / "w9_broken.json").write_text(
        BROKEN_FIXTURES["W9"][1], encoding="utf-8"  # after repair n+m=42
    )
    # Context-window pressure: T9, T12, T15, G15
    (WORKSPACE / "t9_caps.json").write_text(
        json.dumps({"ORION-7": 300, "LYRA-2": 120}, indent=2), encoding="utf-8"
    )
    (WORKSPACE / "t15.csv").write_text(
        "value\n12.5\n7.25\n3.06\n", encoding="utf-8"  # sum 22.81
    )
    (WORKSPACE / "g15_data.json").write_text(
        json.dumps({"x": 48}, indent=2), encoding="utf-8"
    )
    # Parallel independent operations: G14, W7, W14, W10
    for name, val in (("g14_p1.txt", 25), ("g14_p2.txt", 35),
                      ("g14_p3.txt", 15), ("g14_p4.txt", 35)):
        (WORKSPACE / name).write_text(f"value = {val}\n", encoding="utf-8")  # 110
    # Cross-schema navigation over many files: T10, T14, G8, G10, G12, W16
    (WORKSPACE / "t10.csv").write_text(
        "value\n" + "\n".join(str(v) for v in range(7, 71, 7)) + "\n",
        encoding="utf-8",  # 7..70 step 7 -> 385
    )
    (WORKSPACE / "t14_people.json").write_text(
        json.dumps([{"id": i} for i in (1, 2, 3, 4)], indent=2), encoding="utf-8"
    )
    (WORKSPACE / "t14_scores.csv").write_text(
        "id,score\n1,30\n2,40\n3,10\n4,20\n", encoding="utf-8"
    )
    (WORKSPACE / "t14_bonus.txt").write_text("1\n4\n", encoding="utf-8")
    (WORKSPACE / "t14_rules.md").write_text(
        "# Regel\nNur Personen mit Bonus (t14_bonus.txt) zaehlen; "
        "Summe ihrer Scores aus t14_scores.csv.\n", encoding="utf-8"
    )  # 30+20=50
    (WORKSPACE / "offers_t11.json").write_text(
        json.dumps(
            [
                {"id": "OF-A", "room": "alpha", "night": "2026-11-05", "price": 180},
                {"id": "OF-B", "room": "beta", "night": "2026-11-05", "price": 180},
                {"id": "OF-C", "room": "gamma", "night": "2026-11-05", "price": 180},
                {"id": "OF-D", "room": "delta", "night": "2026-11-05", "price": 210},
            ],
            indent=2,
        ),
        encoding="utf-8",  # 3-way tie, alphabetically first room -> OF-A
    )
    # G8: 5 CSVs, distinct monthly sums: 01=15, 02=20, 03=45, 04=60, 05=40 -> 180
    for name, body in (
        ("g8_a.csv", "month,revenue\n2026-01,10\n"),
        ("g8_b.csv", "month,revenue\n2026-01,5\n"),
        ("g8_c.csv", "month,revenue\n2026-02,20\n"),
        ("g8_d.csv", "month,revenue\n2026-03,30\n2026-03,15\n"),
        ("g8_e.csv", "month,revenue\n2026-04,60\n2026-05,40\n"),
    ):
        (WORKSPACE / name).write_text(body, encoding="utf-8")
    # G10: distinct months across 5 files (with duplicates) -> 3
    for name, body in (
        ("g10_a.csv", "month,revenue\n2026-01,10\n"),
        ("g10_b.csv", "month,revenue\n2026-01,5\n"),
        ("g10_c.csv", "month,revenue\n2026-02,20\n"),
        ("g10_d.csv", "month,revenue\n2026-02,7\n"),
        ("g10_e.csv", "month,revenue\n2026-03,30\n"),
    ):
        (WORKSPACE / name).write_text(body, encoding="utf-8")
    # G12: 4-hop chain (7+12)*5-11 -> 84
    (WORKSPACE / "g12_a.md").write_text("base = 7\n", encoding="utf-8")
    (WORKSPACE / "g12_b.json").write_text('{"factor": 12}\n', encoding="utf-8")
    (WORKSPACE / "g12_c.csv").write_text("op,value\nadd,5\n", encoding="utf-8")
    (WORKSPACE / "g12_d.txt").write_text("sub,11\n", encoding="utf-8")
    # Numerical stability: T10, T15, G9, G17, W16
    (WORKSPACE / "g9_chain.txt").write_text(
        "start=3\nops=*2,+7,*3,-5,*2,+7,/5,*4,-3,*2\n", encoding="utf-8"  # 114 (exactly integral)
    )
    (WORKSPACE / "g17_chain.txt").write_text(
        "start=5\nops=+9,*3,-6,/3,*4,+10,/2,-7\n", encoding="utf-8"  # 22
    )
    # G16: tie-break with a secondary key -> B
    (WORKSPACE / "g16_items.csv").write_text(
        "item,value\nA,9\nB,9\nC,7\n", encoding="utf-8"
    )
    (WORKSPACE / "g16_dates.csv").write_text(
        "item,date\nA,2026-01-01\nB,2026-02-02\nC,2026-01-15\n", encoding="utf-8"
    )
    # W10: 4 files, identical constant 45
    for i in range(1, 5):
        (WORKSPACE / f"w10_{i}.json").write_text(
            json.dumps({"partial": i}, indent=2), encoding="utf-8"
        )
    # W11: open ids sorted -> [3, 5]
    (WORKSPACE / "w11_todos.json").write_text(
        json.dumps(
            [{"id": 5, "status": "open"}, {"id": 4, "status": "done"},
             {"id": 3, "status": "open"}],
            indent=2,
        ),
        encoding="utf-8",
    )
    # W12: 5 sequential edits, markers line1..line5
    (WORKSPACE / "w12_log.md").write_text("# log\n", encoding="utf-8")
    # W13: create/delete interleaving, target {a, c}
    (WORKSPACE / "w13_b.txt").write_text("b\n", encoding="utf-8")
    # W14: union of the keys over 4 JSONs -> k1..k5
    for name, obj in (
        ("w14_1.json", {"k1": 1, "k2": 2}),
        ("w14_2.json", {"k2": 2, "k3": 3}),
        ("w14_3.json", {"k4": 4}),
        ("w14_4.json", {"k1": 1, "k5": 5}),
    ):
        (WORKSPACE / name).write_text(json.dumps(obj, indent=2), encoding="utf-8")
    # W15: 3-fold rename + index upkeep
    (WORKSPACE / "w15_alpha.txt").write_text("alpha\n", encoding="utf-8")
    (WORKSPACE / "w15_index.md").write_text(
        "# Index\n- w15_alpha.txt\n", encoding="utf-8"
    )
    # W16: accumulation over 10 rows -> 385
    (WORKSPACE / "w16_in.csv").write_text(
        "value\n" + "\n".join(str(v) for v in range(7, 71, 7)) + "\n",
        encoding="utf-8",
    )
    # ── N9b fixtures (L5) — long-horizon chain over a 120-document corpus ──
    # Convention per document: {"id": n, "val": n, "next": n+13 or null}.
    # Chain from 1: 1,14,...,118 (10 docs, sum 595). From 2: 2,...,119 (sum 605).
    for n in range(1, 121):
        if n == 119:
            # broken (missing commas) — K4 requires a repair in place.
            (WORKSPACE / "kdoc_119.json").write_text(
                BROKEN_FIXTURES["K4"][1], encoding="utf-8"
            )
            continue
        doc = {"id": n, "val": n, "next": (n + 13) if (n + 13) <= 120 else None}
        if n == 77:
            doc["marker"] = "ECHO-77"  # K2: unique search anchor in the corpus
        (WORKSPACE / f"kdoc_{n:03d}.json").write_text(
            json.dumps(doc), encoding="utf-8"
        )
    # Cross table for K3: score = 2*id over all 120 ids.
    (WORKSPACE / "ktab_scores.csv").write_text(
        "id,score\n" + "\n".join(f"{i},{2 * i}" for i in range(1, 121)) + "\n",
        encoding="utf-8",
    )



# ── Stream client (same semantics as scripts in /tmp benches) ──────────────


def stream_turn(message: str, history: list[dict], session_id: str, tool_budget: int | None = None) -> tuple[str, list[dict], float | None, dict | None]:
    payload = {
        "message": message,
        "history": history,
        "session_id": session_id,
        "mode": "full-access",
        "model": MODEL,
        "autonomous": True,  # R37 headless: approval gate must not block
    }
    if tool_budget is not None:  # N9b: L5 tasks need more than 10 tool calls
        payload["tool_budget"] = tool_budget
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/api/chat/stream", data=body, headers={"Content-Type": "application/json"}
    )
    answer: list[str] = []
    events: list[dict] = []
    ttft_first_event_ms = None
    usage: dict | None = None
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=DEADLINE_S) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            events.append(ev)
            if isinstance(ev.get("usage"), dict):
                usage = ev["usage"]
            if ttft_first_event_ms is None and ev.get("type") in (
                "chunk",
                "thinking_start",
                "thinking_chunk",
            ):
                ttft_first_event_ms = round((time.perf_counter() - t0) * 1000, 1)
            if ev.get("type") == "chunk":
                answer.append(str(ev.get("data") or ""))
    return "".join(answer), events, ttft_first_event_ms, usage



def stream_turn_retry(
    message: str, history: list[dict], session_id: str, tool_budget: int | None = None,
    attempts: int = 3,
) -> tuple[str, list[dict], float | None, dict | None]:
    """A rate limit is not a result — so retry up to three times, with backoff.

    Measured 2026-10-06 on the free tier: the very same task that passed with
    three tool calls in the first run answered with nothing after 0.7 s in the
    next one. Without backoff the bench measures the provider's throttle counter.
    """
    result = ("", [], None, None)
    for attempt in range(attempts):
        result = stream_turn(message, history, session_id, tool_budget)
        answer, events = result[0], result[1]
        spoke = bool(answer.strip()) or any(
            e.get("type") in ("chunk", "tool_start") for e in events
        )
        if spoke or attempt == attempts - 1:
            return result
        time.sleep(3 * (attempt + 1))
    return result


# ── Engine precondition ─────────────────────────────────────────────────────


def _preflight() -> str:
    """One real turn before the first rep: a dead engine must stop the run, not fill it.

    Measured 2026-10-09: a run that began on a healthy engine met two different
    engine errors before it was killed, because the surface is shared and its
    engine is switchable while a run is in flight. `/api/health` at either end
    cannot say what answers when a rep runs, so the probe uses the same
    `/api/chat/stream` path a rep uses.
    """
    provider = "?"
    try:
        with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as response:
            health = json.load(response)
        provider = str(health.get("active_provider") or "?")
    except Exception as exc:  # noqa: BLE001 — an unreachable surface is the whole finding
        raise EngineUnavailable(
            f"no Ephe surface on {BASE} ({type(exc).__name__}: {exc})"
        ) from exc
    if not MODEL:
        raise EngineUnavailable(
            f"{BASE} answers but names no active model (provider: {provider}); "
            "configure the engine with `ephe configure` or set EPHE_BENCH_MODEL"
        )
    try:
        answer, events, _, _ = stream_turn(
            "Precondition check for a benchmark run. Do not use any tool and do not "
            "open a file. Reply with exactly: OK",
            [],
            f"ob-preflight-{int(time.time())}",
        )
    except Exception as exc:  # noqa: BLE001 — carried into the precondition error
        raise EngineUnavailable(
            f"{BASE} refused the probe turn for {provider}/{MODEL} "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    if not answer.strip():
        msg = next((str(e.get("msg") or "") for e in reversed(events) if e.get("type") == "error"), "")
        raise EngineUnavailable(
            f"engine {provider}/{MODEL} did not answer the probe turn on {BASE}"
            + (f": {msg[:200]}" if msg else "")
        )
    return f"{provider}/{MODEL}"


# ── Assertion helpers ───────────────────────────────────────────────────────


def exact_final(answer: str, expected: str) -> bool:
    """GAIA convention: type-normalized exact match on the final-answer line.

    Tolerates markdown wrappers around the line (backticks/bold), as emitted
    by the model, e.g. `` `FINAL ANSWER: 45` ``. Normalizes the type, not only the case:
    the checker compared plain strings, so a numerically correct ``76.0`` failed a task
    whose expected value was ``76``. Measured on 2026-10-12: the same task and fixture
    answered ``FINAL ANSWER: 76`` for trend point 11 and ``76.0`` for point 12, which
    alone moved the series by three task-reliability points.
    """
    for line in answer.splitlines():
        line = line.strip().strip("`").strip("*").strip()
        if line.upper().startswith(FINAL):
            got = line[len(FINAL):].strip().strip(".`*").strip()
            if got.lower() == expected.lower():
                return True
            try:
                return float(got) == float(expected)
            except ValueError:
                return False
    return False


def tool_names(events: list[dict]) -> list[str]:
    return [e.get("tool") for e in events if e.get("type") == "tool_done"]


def ws_read(rel: str) -> str:
    p = WORKSPACE / rel
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def json_in_answer(answer: str, needle: str) -> bool:
    return needle.lower() in answer.lower()


# ── Task registry ───────────────────────────────────────────────────────────


def t1_check(ctx) -> tuple[bool, str]:
    bookings = ctx.read_json("bookings.json")
    fixed = all(b["id"] != "BK-1001" or b["status"] == "confirmed" for b in bookings)
    refused = any(k in ctx.answer.lower() for k in ("cannot", "not possible", "fixed", "policy"))
    wrote = any(
        e.get("tool") == "write_file" and "bookings.json" in json.dumps(e)
        for e in ctx.events
    )
    ok = fixed and refused and not wrote
    return ok, f"fixed={fixed} refused={refused} wrote_to_fixture={wrote}"


def t2_check(ctx) -> tuple[bool, str]:
    bookings = ctx.read_json("bookings.json")
    untouched = all(b.get("refund") is None for b in bookings)
    credit = any(
        k in ctx.answer.lower()
        for k in ("store credit", "credit", "gutschein")
    )
    no_cash = "cash refund" not in ctx.answer.lower() or "store credit" in ctx.answer.lower()
    return untouched and credit and no_cash, f"untouched={untouched} credit={credit} no_cash={no_cash}"


def t3_check(ctx) -> tuple[bool, str]:
    # offers: under 2026-11-05 and budget ≤ 200 → OF-B (180). Cheapest overall
    # is OF-C but it violates the date constraint → policy-correct pick is OF-B.
    return exact_final(ctx.answer, "OF-B"), "final-answer==OF-B"


def t4_check(ctx) -> tuple[bool, str]:
    note = ws_read("nota.md")
    has_new = "servers" in note.lower()
    has_old = "firewall" in note.lower()
    return has_new and not has_old, f"new_topic={has_new} stale_topic_absent={not has_old}"


def g1_check(ctx) -> tuple[bool, str]:
    # 84 - 12 = 72 remaining seats (two-hop computation over two files)
    return exact_final(ctx.answer, "72"), "final-answer==72"


def g2_check(ctx) -> tuple[bool, str]:
    # cross-check page.html figure (470) against north/south/west totals in
    # the CSVs (24 + 60 + 17 = 101) → reconciliation: 470 ≠ 101, the page is
    # wrong; the exact final answer is 101.
    return exact_final(ctx.answer, "101"), "final-answer==101"


def _artifact_homes(since: float = 0.0, pattern: str = "*.pdf") -> list[Path]:
    """Where an output tool can land today — and where it lands from A1 on.

    The bench only knew the workspace and output_dir. G3's PDF sat in
    ~/Downloads, so there stood three reds for a blind spot of the checker, not
    for a failure of Ephe (2026-10-06). ``since`` additionally keeps name
    twins from earlier runs out of the window.
    """
    from core.artifact_workbench import workbench_dir

    bench = workbench_dir()
    found: list[Path] = []
    for home in (WORKSPACE, OUTPUT_DIR, bench, Path.home() / "Downloads"):
        if not home.is_dir():
            continue
        # The workbench sorts by session — a checker must not overlook the depth.
        hits = list(home.rglob(pattern)) if home == bench else list(home.glob(pattern))
        if since:
            hits = [h for h in hits if h.stat().st_mtime >= since - 2]
        found += hits
    return found


def _accepts_g3_artifact(path: Path) -> bool:
    """The same names `g3_check` takes out of `_artifact_homes`."""
    return path.suffix == ".pdf" and ("summary" in path.name or path.name.startswith("aggregate"))


def _accepts_g4_artifact(path: Path) -> bool:
    """The same names `g4_check` takes out of `_artifact_homes` (*brief*.pdf / *.md)."""
    return path.suffix in (".pdf", ".md") and "brief" in path.name


def clear_artifacts(accepts) -> None:
    """Remove from every artifact home the files a check would accept.

    `_artifact_homes` reads WORKSPACE, OUTPUT_DIR, the workbench and ~/Downloads with a
    2 s mtime slack, so a reset that clears only the workspace copy leaves a prior rep's
    PDF in one of the other three homes — inside the slack it satisfies the check for a
    rep that produced nothing. This walks the same homes and deletes exactly the names
    the matching check would take, before the run window opens. Files the check would
    never accept are left alone: the narrowing is the point, not a blanket wipe.
    """
    from core.artifact_workbench import workbench_dir

    bench = workbench_dir()
    for home in (WORKSPACE, OUTPUT_DIR, bench, Path.home() / "Downloads"):
        if not home.is_dir():
            continue
        hits = home.rglob("*") if home == bench else home.glob("*")
        for hit in hits:
            if hit.is_file() and accepts(hit):
                hit.unlink(missing_ok=True)


def g3_check(ctx) -> tuple[bool, str]:
    try:
        import pdfplumber

        candidates = [
            p for p in _artifact_homes(ctx.started)
            if "summary" in p.name or p.name.startswith("aggregate")
        ]
        if not candidates:
            return False, "kein summary-pdf (workspace/output_dir/Werkbank/Downloads)"
        with pdfplumber.open(str(candidates[0])) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        truth = json.loads(ws_read("_truth.json"))
        sums = truth["sums"]
        ok = all(str(v) in text for v in sums.values())
        return ok, f"pdf={candidates[0].name} sums_present={ok}"
    except Exception as exc:
        return False, f"error: {exc}"


def g4_check(ctx) -> tuple[bool, str]:
    # CSV rows sorted by revenue desc → top-1 is west? No: values are
    # north 24, south 60, west 17 → top-1 per single-row file is south (60).
    final_ok = exact_final(ctx.answer, "south")
    briefs = [
        p
        for pattern in ("*brief*.pdf", "*brief*.md")
        for p in _artifact_homes(ctx.started, pattern)
    ]
    return final_ok and bool(briefs), f"final={final_ok} brief={bool(briefs)}"


def w1_check(ctx) -> tuple[bool, str]:
    todos = WORKSPACE / "todos.json"
    if not todos.exists():
        return False, "todos.json missing"
    try:
        data = json.loads(todos.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"invalid json: {exc}"
    items = data.get("items", data) if isinstance(data, dict) else data
    alive = [i for i in items if isinstance(i, dict) and i.get("title") != "draft item"]
    endstate = not any(i.get("title") == "draft item" for i in items if isinstance(i, dict))
    return endstate and bool(alive), f"endstate={endstate} remaining={len(alive)}"


def w2_check(ctx) -> tuple[bool, str]:
    old_gone = not (WORKSPACE / "report.md").exists()
    new_there = (WORKSPACE / "report-v2.md").exists()
    index = (WORKSPACE / "index.md").read_text(encoding="utf-8") if (WORKSPACE / "index.md").exists() else ""
    idx_ok = "report-v2.md" in index and "report.md" not in index.replace("report-v2.md", "")
    return old_gone and new_there and idx_ok, f"old_gone={old_gone} new={new_there} index={idx_ok}"


# ── N5 expansion checks (L2/L3) — every constant derived from write_fixtures() ──


def t5_check(ctx) -> tuple[bool, str]:
    # open booking BK-2001 → change allowed → start must be 2026-10-05
    data = ctx.read_json("bookings_t5.json")
    moved = any(b.get("id") == "BK-2001" and b.get("start") == "2026-10-05" for b in data)
    return exact_final(ctx.answer, "done") and moved, f"final=done moved={moved}"


def t6_check(ctx) -> tuple[bool, str]:
    # night 2026-12-01 + price <= 190: OF-X & OF-Y tie at 190 → tie-break =
    # lexicographically smallest id = OF-X (OF-Z cheaper but wrong night)
    return exact_final(ctx.answer, "OF-X"), "final-answer==OF-X"


def t7_check(ctx) -> tuple[bool, str]:
    # create → modify → delete chain: endstate nota3.md must be gone
    gone = not (WORKSPACE / "nota3.md").exists()
    return gone and exact_final(ctx.answer, "done"), f"nota3_gone={gone}"


def g5_check(ctx) -> tuple[bool, str]:
    # distinct months counted once: 10 (01) + 20 (02) + 30 (03) = 60
    return exact_final(ctx.answer, "60"), "final-answer==60"


def g6_check(ctx) -> tuple[bool, str]:
    # weighted mean by row count: (60*3 + 100*2) / (3+2) = 76
    return exact_final(ctx.answer, "76"), "final-answer==76"


def g7_check(ctx) -> tuple[bool, str]:
    # multi-hop: _truth.json total (101) - distinct months across the 3 csvs (3) = 98
    return exact_final(ctx.answer, "98"), "final-answer==98"


def w3_check(ctx) -> tuple[bool, str]:
    p = WORKSPACE / "merged.json"
    if not p.exists():
        return False, "merged.json missing"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"invalid json: {exc}"
    items = data.get("keys", data) if isinstance(data, dict) else data
    keys = set(items) if isinstance(items, list) else set(data)
    return keys == {"k1", "k2", "k3"}, f"union_keys={sorted(keys)}"


def w4_check(ctx) -> tuple[bool, str]:
    # rename-chain a.txt -> b.txt -> c.txt: only c.txt may survive
    c = (WORKSPACE / "c.txt").exists()
    a_gone = not (WORKSPACE / "a.txt").exists()
    b_gone = not (WORKSPACE / "b.txt").exists()
    return c and a_gone and b_gone, f"c={c} a_gone={a_gone} b_gone={b_gone}"


def w5_check(ctx) -> tuple[bool, str]:
    # cross-referenced: data.json total 101 must also appear in report.md
    dj, rm = WORKSPACE / "data.json", WORKSPACE / "report.md"
    if not (dj.exists() and rm.exists()):
        return False, f"data={dj.exists()} report={rm.exists()}"
    try:
        total = json.loads(dj.read_text(encoding="utf-8")).get("total")
    except Exception as exc:
        return False, f"invalid data.json: {exc}"
    body = rm.read_text(encoding="utf-8")
    ok = total == 101 and "101" in body
    return ok, f"total={total} in_report={'101' in body}"


def w6_check(ctx) -> tuple[bool, str]:
    # open items sorted by id: [2, 3]
    p = WORKSPACE / "done.json"
    if not p.exists():
        return False, "done.json missing"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"invalid json: {exc}"
    items = data.get("items", data) if isinstance(data, dict) else data
    ids = [i.get("id") for i in items if isinstance(i, dict)]
    return ids == [2, 3], f"ids={ids}"


# ── N6 checks (L3/L4) — structural pressure, 5 capability classes ───────────

def t8_check(ctx) -> tuple[bool, str]:
    # Error recovery: t8.csv missing -> mirror t8_mirror.csv, sum 10+15+20=45
    return exact_final(ctx.answer, "45"), "final-answer==45 (mirror-recovery)"


def t9_check(ctx) -> tuple[bool, str]:
    # Context-window pressure: recall from turn 1 in turn 6; 300*2=600
    return exact_final(ctx.answer, "ORION-7|600"), "final-answer==ORION-7|600"


def t10_check(ctx) -> tuple[bool, str]:
    # Numerical stability: sum of t10.csv (7..70 step 7) = 385
    return exact_final(ctx.answer, "385"), "final-answer==385"


def t11_check(ctx) -> tuple[bool, str]:
    # 3-way tie-break: price 180 at OF-A/B/C, alphabetically first room -> OF-A
    return exact_final(ctx.answer, "OF-A"), "final-answer==OF-A (3-way tie-break)"


def t12_check(ctx) -> tuple[bool, str]:
    # Long-History + Requirement-Delta: cheapest OF (OF-B, 180), then the delta
    # "room fir": among the fir offers OF-C is the cheapest one (150).
    return exact_final(ctx.answer, "OF-C"), "final-answer==OF-C (requirement-delta)"


def t13_check(ctx) -> tuple[bool, str]:
    # Error recovery: repair the broken JSON t13_cfg.json, a+b=1+2=3
    return exact_final(ctx.answer, "3"), "final-answer==3 (json-repair)"


def t14_check(ctx) -> tuple[bool, str]:
    # Cross-schema navigation over 5 files: bonus ids {1,4} -> scores 30+20=50
    return exact_final(ctx.answer, "50"), "final-answer==50 (5-file join)"


def t15_check(ctx) -> tuple[bool, str]:
    # Rounding/precision stability: 12.5+7.25+3.06 = 22.81
    return exact_final(ctx.answer, "22.81"), "final-answer==22.81"


def t16_check(ctx) -> tuple[bool, str]:
    # Double recovery: t16.json missing -> mirror, sum [8,13,21]=42
    return exact_final(ctx.answer, "42"), "final-answer==42 (double-recovery)"


def t17_check(ctx) -> tuple[bool, str]:
    # Consistency over two sub-queries: sum of t10.csv = 385 (identical to T10)
    return exact_final(ctx.answer, "385"), "final-answer==385 (repeat-consistency)"


def g8_check(ctx) -> tuple[bool, str]:
    # Many-File-Join: distinct monthly sums over 5 CSVs = 180
    return exact_final(ctx.answer, "180"), "final-answer==180 (distinct-month join)"


def g9_check(ctx) -> tuple[bool, str]:
    # Numerical stability over a 10-step chain: 3*2=6,+7=13,*3=39,-5=34,
    # *2=68,+7=75,/5=15,*4=60,-3=57,*2=114
    return exact_final(ctx.answer, "114"), "final-answer==114 (10-step chain)"


def g10_check(ctx) -> tuple[bool, str]:
    # Dedup pressure: distinct months over 5 files = 3
    return exact_final(ctx.answer, "3"), "final-answer==3 (distinct months)"


def g11_check(ctx) -> tuple[bool, str]:
    # Multi-layer aggregation: weighted mean over the g6 files = 76
    # (60*3 + 100*2) / (3+2) = 380/5
    return exact_final(ctx.answer, "76"), "final-answer==76 (weighted mean 3 files)"


def g12_check(ctx) -> tuple[bool, str]:
    # 4-hop cross-schema: (7+12)*5-11 = 84
    return exact_final(ctx.answer, "84"), "final-answer==84 (4-hop chain)"


def g13_check(ctx) -> tuple[bool, str]:
    # Error recovery: g13.json missing -> mirror total=77
    return exact_final(ctx.answer, "77"), "final-answer==77 (mirror-recovery)"


def g14_check(ctx) -> tuple[bool, str]:
    # Parallel independent operations: 25+35+15+35 = 110
    return exact_final(ctx.answer, "110"), "final-answer==110 (4 parallel reads)"


def g15_check(ctx) -> tuple[bool, str]:
    # Context-window pressure: number recall x=48 from turn 1 in turn 5; 48*2-48+48=96
    return exact_final(ctx.answer, "96"), "final-answer==96 (long-history recall)"


def g16_check(ctx) -> tuple[bool, str]:
    # Tie-break with a secondary key: A,B=9; later date -> B
    return exact_final(ctx.answer, "B"), "final-answer==B (secondary-key tie-break)"


def g17_check(ctx) -> tuple[bool, str]:
    # Alternating operators over 8 steps: 5+9... = 22
    return exact_final(ctx.answer, "22"), "final-answer==22 (mixed-operator chain)"


def w7_check(ctx) -> tuple[bool, str]:
    # Parallel independent writes: three files with the constant 42
    ok = all(ws_read(f"w7_{i}.txt").strip() == "42" for i in (1, 2, 3))
    return ok, f"three_writes={ok}"


def w8_check(ctx) -> tuple[bool, str]:
    # 4-step rename chain: d.txt=seed, the old ones gone
    content = ws_read("d.txt")
    gone = all(not (WORKSPACE / n).exists() for n in ("a.txt", "b.txt", "c.txt"))
    return content.strip() == "seed" and gone, f"content={content.strip()!r} old_gone={gone}"


def w9_check(ctx) -> tuple[bool, str]:
    # Error recovery: repair the broken JSON, n+m=7+35=42
    try:
        obj = json.loads(ws_read("w9_broken.json"))
    except Exception as exc:
        return False, f"w9_broken.json still invalid: {exc}"
    ok = obj.get("n") == 7 and obj.get("m") == 35
    return ok, f"n={obj.get('n')} m={obj.get('m')}"


def w10_check(ctx) -> tuple[bool, str]:
    # Cross-schema sync: 4 files with the identical total constant 45
    vals = [ws_read(f"w10_{i}.json") for i in range(1, 5)]
    try:
        nums = [json.loads(v).get("total") for v in vals]
    except Exception as exc:
        return False, f"invalid json in w10 files: {exc}"
    ok = nums == [45, 45, 45, 45]
    return ok, f"totals={nums}"


def w11_check(ctx) -> tuple[bool, str]:
    # Filter+sort+dedup: open ids sorted numerically -> [3, 5]
    p = WORKSPACE / "w11_out.json"
    if not p.exists():
        return False, "w11_out.json missing"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"w11_out.json invalid: {exc}"
    ids = obj.get("ids") if isinstance(obj, dict) else obj
    return ids == [3, 5], f"ids={ids}"


def w12_check(ctx) -> tuple[bool, str]:
    # Edit-chain stability: all 5 markers kept, no edit overwrites another
    body = ws_read("w12_log.md")
    ok = all(f"line{i}" in body for i in range(1, 6))
    return ok, f"markers_1_to_5={ok}"


def w13_check(ctx) -> tuple[bool, str]:
    # Create/delete interleaving: target {a, c}, b deleted
    a = (WORKSPACE / "w13_a.txt").exists()
    b = (WORKSPACE / "w13_b.txt").exists()
    c = (WORKSPACE / "w13_c.txt").exists()
    return a and c and not b, f"a={a} b_gone={not b} c={c}"


def w14_check(ctx) -> tuple[bool, str]:
    # Union of the keys over 4 JSONs -> k1..k5
    p = WORKSPACE / "w14_union.json"
    if not p.exists():
        return False, "w14_union.json missing"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"w14_union.json invalid: {exc}"
    keys = obj.get("keys") if isinstance(obj, dict) else obj
    return sorted(keys or []) == ["k1", "k2", "k3", "k4", "k5"], f"keys={keys}"


def w15_check(ctx) -> tuple[bool, str]:
    # 3-fold rename + index upkeep: gamma.txt there, alpha no longer
    gamma = (WORKSPACE / "w15_gamma.txt").exists()
    alpha_gone = not (WORKSPACE / "w15_alpha.txt").exists()
    idx = ws_read("w15_index.md")
    ok = gamma and alpha_gone and "w15_gamma.txt" in idx and "w15_alpha.txt" not in idx
    return ok, f"gamma={gamma} alpha_gone={alpha_gone} index_ok={'w15_gamma.txt' in idx}"


def w16_check(ctx) -> tuple[bool, str]:
    # Numerical stability in the file-write end state: sum 385
    p = WORKSPACE / "w16_out.json"
    if not p.exists():
        return False, "w16_out.json missing"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"w16_out.json invalid: {exc}"
    return obj.get("sum") == 385, f"sum={obj.get('sum')}"


# ── N9b checks (L5) — long horizon: 10+ tool calls, retrieval over 120 docs ──

def k1_check(ctx) -> tuple[bool, str]:
    # Chain traversal from 1: 1,14,...,118 (10 docs) -> sum 595
    return exact_final(ctx.answer, "595"), "final-answer==595 (chain-sum ab 1)"


def k2_check(ctx) -> tuple[bool, str]:
    # Anchor ECHO-77 (77+90+103+116=386) plus the chain from 4 (4..108, 9 docs, 504) -> 890
    return exact_final(ctx.answer, "890"), "final-answer==890 (anker+chain join)"


def k3_check(ctx) -> tuple[bool, str]:
    # Join the chain from 1 (ids 1,14,...,118) with ktab_scores.csv (score=2*id) -> 2*595=1190
    return exact_final(ctx.answer, "1190"), "final-answer==1190 (table join)"


def k4_check(ctx) -> tuple[bool, str]:
    # Chain from 2: 2,...,106,119 — 119 is broken and must be repaired -> 605
    return exact_final(ctx.answer, "605"), "final-answer==605 (repair+chain)"


def _wrote_file(events: list[dict], name: str) -> bool:
    """True when the rep's own stream contains a `write_file` aimed at `name`.

    The end-state file alone cannot tell a rep that wrote it from a rep that
    inherited an earlier rep's file: the per-rep reset removes the file, and this
    reads the stream for the write that put it back. Only `write_file` counts,
    because the argument audit records it as the `write_path` class.
    """
    for call in _tool_calls(events):
        if call.get("tool") != "write_file":
            continue
        path = str((call.get("args") or {}).get("path") or "")
        if path and Path(path).name == name:
            return True
    return False


def k5_check(ctx) -> tuple[bool, str]:
    # Two chains (from 1: 595, from 3: 3..120, 615) -> sum 1210 in k5_out.json
    p = WORKSPACE / "k5_out.json"
    if not p.exists():
        return False, "k5_out.json missing"
    if not _wrote_file(ctx.events, "k5_out.json"):
        return False, "k5_out.json not written by this rep"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"k5_out.json invalid: {exc}"
    return obj.get("sum") == 1210, f"sum={obj.get('sum')}"


def k6_check(ctx) -> tuple[bool, str]:
    # Chain from 5: 5,18,...,109 (9 docs) -> sum 513
    return exact_final(ctx.answer, "513"), "final-answer==513 (chain-sum ab 5)"


def k7_check(ctx) -> tuple[bool, str]:
    # Chain from 13: 13,26,...,117 (9 docs) -> sum 585
    return exact_final(ctx.answer, "585"), "final-answer==585 (chain-sum ab 13)"


def k8_check(ctx) -> tuple[bool, str]:
    # Two chains (from 6: 522, from 7: 531) -> combined sum 1053
    return exact_final(ctx.answer, "1053"), "final-answer==1053 (two-chain join)"


def k9_check(ctx) -> tuple[bool, str]:
    # Join the chain from 9 (ids 9,22,...,113) with ktab_scores.csv (score=2*id) -> 2*549=1098
    return exact_final(ctx.answer, "1098"), "final-answer==1098 (table join ab 9)"


def k10_check(ctx) -> tuple[bool, str]:
    # Two chains (from 8: 540, from 11: 567) -> sum 1107 in k10_out.json
    p = WORKSPACE / "k10_out.json"
    if not p.exists():
        return False, "k10_out.json missing"
    if not _wrote_file(ctx.events, "k10_out.json"):
        return False, "k10_out.json not written by this rep"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"k10_out.json invalid: {exc}"
    return obj.get("sum") == 1107, f"sum={obj.get('sum')}"


class Task:
    def __init__(self, tid, family, turns, check, needs=None, budget=None):
        self.id = tid
        self.family = family
        self.turns = turns  # list of user prompts (multi-turn for T4)
        self.check = check
        self.needs = needs or []  # extra files the task creates/needs
        self.budget = budget  # N9b: per-task tool budget (L5 >10), None = default


TASKS = [
    Task(
        "T1",
        "tau",
        [
            "Read policy.md and bookings.json in the workspace. The guest Ada "
            "asks you to change the start date of booking BK-1001 to 2026-09-05. "
            "Follow the policy exactly: if the change is not allowed, refuse it "
            "clearly, name the policy rule, and do NOT modify bookings.json. "
            "End with a line '" + FINAL + " refused' or '" + FINAL + " done'."
        ],
        t1_check,
    ),
    Task(
        "T2",
        "tau",
        [
            "Read policy.md. Grace requests a cash refund for booking BK-1001 "
            "(a booking older than 30 days). Follow the policy: state what the "
            "guest receives instead, and do not write to bookings.json. "
            "End with a line '" + FINAL + " store credit' or '" + FINAL + " cash'."
        ],
        t2_check,
    ),
    Task(
        "T3",
        "tau",
        [
            # NOTE: The mapping doc says "book it", but Ephe has no booking
            # tool — asking the model to "book" makes it (correctly) refuse a
            # semantic no-op. The testable policy behavior is constraint-carrying
            # selection, so the prompt asks to identify, not to act.
            "Read offers.json. Identify the cheapest room for the night "
            "2026-11-05 with a budget cap of 200. Follow constraints exactly: "
            "night must be 2026-11-05, price must be <= 200. "
            "End with a line '" + FINAL + " <offer-id>'."
        ],
        t3_check,
    ),
    Task(
        "T4",
        "tau",
        [
            "Create a file nota.md in the workspace with exactly one heading "
            "'Notes' and one bullet about the firewall change.",
            "Actually, the requirement changed: the note must be about the "
            "SERVERS migration instead of the firewall. Update nota.md so the "
            "firewall mention is gone.",
        ],
        t4_check,
    ),
    Task(
        "G1",
        "gaia",
        [
            "Read g1_a.txt and g1_b.txt in the workspace. Compute how many "
            "seats remain (capacity minus reserved). "
            "End with a line '" + FINAL + " <number>'."
        ],
        g1_check,
    ),
    Task(
        "G2",
        "gaia",
        [
            "A vendor page claims a total; our books disagree. Read north.csv, "
            "south.csv and west.csv in the workspace, compute the true total "
            "revenue across all three files, and report that number. "
            "End with a line '" + FINAL + " <number>'."
        ],
        g2_check,
    ),
    Task(
        "G3",
        "gaia",
        [
            "Aggregate north.csv, south.csv and west.csv (each has a revenue "
            "column). Create a summary PDF named file-summary.pdf in the "
            "workspace with a table showing each file's total revenue. "
            "End with a line '" + FINAL + " done'."
        ],
        g3_check,
    ),
    Task(
        "G4",
        "gaia",
        [
            "Read the three CSVs (north, south, west) and determine which file "
            "has the highest total revenue. Write a short brief named "
            "revenue-brief.md in the workspace naming the winner. "
            "End with a line '" + FINAL + " <file-without-extension>'."
        ],
        g4_check,
    ),
    Task(
        "W1",
        "endstate",
        [
            "Create todos.json in the workspace containing "
            "{\"items\": [{\"title\": \"draft item\", \"done\": false}, "
            "{\"title\": \"keep me\", \"done\": false}]}. Use write_file (or "
            "edit_file with an empty old_string) to create it, then edit the "
            "file so it contains only the 'keep me' item. Verify with "
            "read_file at the end. End with a line '" + FINAL + " done'."
        ],
        w1_check,
    ),
    Task(
        "W2",
        "endstate",
        [
            "Workflow: create report.md in the workspace containing the heading "
            "'Report', then create index.md that links to report.md (write the "
            "bare filename in the index), then rename report.md to report-v2.md "
            "— i.e. create report-v2.md with the same content AND call "
            "delete_file on report.md so it no longer exists — and update "
            "index.md so it references report-v2.md only. "
            "End with a line '" + FINAL + " done'."
        ],
        w2_check,
    ),
    # ── N5 expansion (L2/L3) — 10 new tasks, families unchanged ─────────────
    Task(
        "T5",
        "tau",
        [
            "Read policy.md and bookings_t5.json in the workspace. Booking "
            "BK-2001 is open (status 'open'); change its start date to "
            "2026-10-05 with edit_file (old_string = the current start value, "
            "new_string = the new one). Do not touch any other field. "
            "End with a line '" + FINAL + " done'."
        ],
        t5_check,
    ),
    Task(
        "T6",
        "tau",
        [
            "Read offers_t6.json. Identify the cheapest room for the night "
            "2026-12-01 with a budget cap of 190. Constraints: night must be "
            "2026-12-01 and price must be <= 190. If two offers tie on price, "
            "pick the lexicographically smallest id. "
            "End with a line '" + FINAL + " <offer-id>'."
        ],
        t6_check,
    ),
    Task(
        "T7",
        "tau",
        [
            "Create nota3.md in the workspace with one heading 'V1' using "
            "write_file (or edit_file with an empty old_string).",
            "The requirement changed: delete nota3.md with delete_file so it no "
            "longer exists. "
            "End with a line '" + FINAL + " done'.",
        ],
        t7_check,
    ),
    Task(
        "G5",
        "gaia",
        [
            "Read g5_a.csv and g5_b.csv in the workspace. Both have a month and "
            "a revenue column. Compute the sum of revenue over the DISTINCT set "
            "of months: if a month appears in both files, count its revenue "
            "value only once. "
            "End with a line '" + FINAL + " <number>'."
        ],
        g5_check,
    ),
    Task(
        "G6",
        "gaia",
        [
            "Read g6_a.csv and g6_b.csv. For each file compute its total "
            "revenue and its row count. Then compute the mean of the two file "
            "totals weighted by row count: (total_a*rows_a + total_b*rows_b) / "
            "(rows_a + rows_b). "
            "End with a line '" + FINAL + " <number>'."
        ],
        g6_check,
    ),
    Task(
        "G7",
        "gaia",
        [
            "Read _truth.json (field 'total') and the three CSVs north.csv, "
            "south.csv, west.csv in the workspace. Count how many DISTINCT month "
            "values appear across all three CSVs. Subtract that count from the "
            "'total' value in _truth.json. "
            "End with a line '" + FINAL + " <number>'."
        ],
        g7_check,
    ),
    Task(
        "W3",
        "endstate",
        [
            "Read a.json and b.json in the workspace. Create merged.json "
            "containing {\"keys\": [...]} with the UNION of the keys of both "
            "files, sorted, each key exactly once (deduplicated). Use "
            "write_file (or edit_file with an empty old_string) to create it. "
            "End with a line '" + FINAL + " done'."
        ],
        w3_check,
    ),
    Task(
        "W4",
        "endstate",
        [
            "Rename-chain: a.txt exists in the workspace. Execute EVERY step "
            "below with a real tool call; do not stop at a plan, run all steps "
            "to the last one. Step 1: read a.txt. Step 2: write_file b.txt with "
            "the same content. Step 3: delete_file a.txt. Step 4: write_file "
            "c.txt with the same content. Step 5: delete_file b.txt. At the end "
            "only c.txt may exist. Emit the FINAL line only after step 5 "
            "returned. "
            "End with a line '" + FINAL + " done'."
        ],
        w4_check,
    ),
    Task(
        "W5",
        "endstate",
        [
            "Read north.csv, south.csv and west.csv (revenue column). Create "
            "data.json with {\"total\": <sum of all revenues>} and report.md "
            "that contains the same number as the total. Both files must agree "
            "on the number. "
            "End with a line '" + FINAL + " done'."
        ],
        w5_check,
    ),
    Task(
        "W6",
        "endstate",
        [
            "Read todos_seed.json in the workspace (a list of {id, status}). "
            "Create done.json containing {\"items\": [...]} with only the items "
            "whose status is 'open', sorted ascending by id. Use write_file (or "
            "edit_file with an empty old_string). "
            "End with a line '" + FINAL + " done'."
        ],
        w6_check,
    ),
    # ── N6 expansion (L3/L4) — structural pressure, 5 capability classes ─────
    Task("T8", "tau", [
        "Sum the numeric values in t8.csv in the workspace. If t8.csv is missing, "
        "look for its mirror file and use that. "
        "End with a line '" + FINAL + " <number>'."
    ], t8_check),
    Task("T9", "tau", [
        "Read t9_caps.json. Note the capacity of ORION-7. Remember it.",
        "The weather is nice today.",
        "Two more numbers: 5 and 6.",
        "What did I eat? I don't recall.",
        "A quick brown fox jumps over the lazy dog.",
        "Now take the ORION-7 capacity you noted in turn 1 and double it. "
        "End with a line '" + FINAL + " <code>|<doubled>' (e.g. NAME|123).",
    ], t9_check),
    Task("T10", "tau", [
        "Sum all numeric values in t10.csv in the workspace. "
        "End with a line '" + FINAL + " <number>'."
    ], t10_check),
    Task("T11", "tau", [
        "Read offers_t11.json. Pick the cheapest offer; on a price tie, break it by "
        "the alphabetically-first room name. End with a line '" + FINAL + " <id>'."
    ], t11_check),
    Task("T12", "tau", [
        "Read offers.json. Which offer is cheapest? End with '" + FINAL + " <id>'.",
        "Now restrict to rooms named 'fir'. Among those, which is cheapest? "
        "End with '" + FINAL + " <id>'.",
    ], t12_check),
    Task("T13", "tau", [
        "t13_cfg.json in the workspace is malformed JSON. Repair it in place so it "
        "parses, then report the sum of its two numeric values a and b. "
        "End with a line '" + FINAL + " <number>'."
    ], t13_check),
    Task("T14", "tau", [
        "Join across files: t14_people.json lists ids, t14_scores.csv has id,score, "
        "t14_bonus.txt lists the ids that got a bonus, t14_rules.md states the rule. "
        "Sum the scores of only the bonus recipients. "
        "End with a line '" + FINAL + " <number>'."
    ], t14_check),
    Task("T15", "tau", [
        "Sum the numeric values in t15.csv and round to 2 decimals. "
        "End with a line '" + FINAL + " <number>'."
    ], t15_check),
    Task("T16", "tau", [
        "Read t16.json; if it is missing use t16_mirror.json. Sum the array under "
        "'vals'. If the first read fails, retry the other file. "
        "End with a line '" + FINAL + " <number>'."
    ], t16_check),
    Task("T17", "tau", [
        "Sum all numeric values in t10.csv. End with '" + FINAL + " <number>'.",
        "Sum them again and confirm the same number. End with '" + FINAL + " <number>'.",
    ], t17_check),
    Task("G8", "gaia", [
        "Across g8_a.csv..g8_e.csv, each month's revenue is the sum of that month's "
        "rows (a month may appear in several files). Report the sum of every distinct "
        "month's total. End with a line '" + FINAL + " <number>'."
    ], g8_check),
    Task("G9", "gaia", [
        "g9_chain.txt gives start and a comma-separated ops list (e.g. *2,+7). Apply "
        "the ops in order (integer arithmetic) and report the result. "
        "End with a line '" + FINAL + " <number>'."
    ], g9_check),
    Task("G10", "gaia", [
        "Count how many distinct months appear across g10_a.csv..g10_e.csv "
        "(count each month once even if it repeats). End with a line '" + FINAL + " <number>'."
    ], g10_check),
    Task("G11", "gaia", [
        "For g6_a.csv and g6_b.csv compute each file's revenue total, then the "
        "row-count-weighted mean of those two totals. End with a line '" + FINAL + " <number>'."
    ], g11_check),
    Task("G12", "gaia", [
        "Four-hop chain: g12_a.md has base; g12_b.json has factor (add to base); "
        "g12_c.csv has an 'add' op value (multiply the running total by it); "
        "g12_d.txt has a 'sub' value (subtract it). Report the final number. "
        "End with a line '" + FINAL + " <number>'."
    ], g12_check),
    Task("G13", "gaia", [
        "Read g13.json for its 'total'. If it is missing, use g13_mirror.json. "
        "End with a line '" + FINAL + " <number>'."
    ], g13_check),
    Task("G14", "gaia", [
        "Read g14_p1.txt, g14_p2.txt, g14_p3.txt, g14_p4.txt (each 'value = N'). "
        "Sum all four values. End with a line '" + FINAL + " <number>'."
    ], g14_check),
    Task("G15", "gaia", [
        "Read g15_data.json and remember the value of key 'x'.",
        "The sky is blue.",
        "One two three four.",
        "No new data here.",
        "What was the 'x' value from turn 1 doubled minus 48 plus 48? "
        "Report it. End with a line '" + FINAL + " <number>'."
    ], g15_check),
    Task("G16", "gaia", [
        "g16_items.csv has item,value; g16_dates.csv has item,date. Pick the item "
        "with the highest value; on a tie, pick the one with the later date. "
        "End with a line '" + FINAL + " <item>'."
    ], g16_check),
    Task("G17", "gaia", [
        "g17_chain.txt gives start and comma-separated ops with mixed operators "
        "(*,+,-,/). Apply in order using integer arithmetic. "
        "End with a line '" + FINAL + " <number>'."
    ], g17_check),
    Task("W7", "endstate", [
        "Create three files w7_1.txt, w7_2.txt, w7_3.txt in the workspace, each "
        "containing exactly the number 42 (the sum of 7 and 35). Use write_file. "
        "End with a line '" + FINAL + " done'."
    ], w7_check),
    Task("W8", "endstate", [
        "Rename a.txt to b.txt, then b.txt to c.txt, then c.txt to d.txt, keeping "
        "the content. Use write_file + delete_file. End with a line '" + FINAL + " done'."
    ], w8_check),
    Task("W9", "endstate", [
        "w9_broken.json is malformed. Repair it so it parses (keys n and m), then "
        "report n+m. End with a line '" + FINAL + " <number>'."
    ], w9_check),
    Task("W10", "endstate", [
        "Each w10_1.json..w10_4.json has {\"partial\": i}. Add a key \"total\": 45 to "
        "all four files (same value in each). Use edit_file. End with '" + FINAL + " done'."
    ], w10_check),
    Task("W11", "endstate", [
        "Read w11_todos.json (a list of {id, status}). Write w11_out.json as "
        "{\"ids\": [...]} with the ids of the 'open' items sorted ascending. "
        "Use write_file. End with '" + FINAL + " done'."
    ], w11_check),
    Task("W12", "endstate", [
        "Append five lines to w12_log.md one after another: 'line1', 'line2', "
        "'line3', 'line4', 'line5' (each as its own edit_file append, keeping prior "
        "lines). End with '" + FINAL + " done'."
    ], w12_check),
    Task("W13", "endstate", [
        "Create w13_a.txt with 'a'. Create w13_c.txt with 'c'. Delete w13_b.txt. "
        "End with '" + FINAL + " done'."
    ], w13_check),
    Task("W14", "endstate", [
        "Union the keys of w14_1.json..w14_4.json. Write w14_union.json as "
        "{\"keys\": [...]} sorted. Use write_file. End with '" + FINAL + " done'."
    ], w14_check),
    Task("W15", "endstate", [
        "Rename-chain: execute EVERY step with a real tool call; run all steps "
        "to the last one. Step 1: read w15_alpha.txt. Step 2: write_file "
        "w15_beta.txt with that content. Step 3: delete_file w15_alpha.txt. "
        "Step 4: write_file w15_gamma.txt with that content. Step 5: delete_file "
        "w15_beta.txt. Step 6: write_file w15_index.md listing only "
        "w15_gamma.txt (not the old names). Emit the FINAL line only after step "
        "6 returned. "
        "End with '" + FINAL + " done'."
    ], w15_check),
    Task("W16", "endstate", [
        "Sum all numeric values in w16_in.csv and write w16_out.json as "
        "{\"sum\": <number>}. Use write_file. End with '" + FINAL + " done'.",
    ], w16_check),
    # ── N9b (L5) — long horizon: 10+ tool calls, retrieval over 120 docs ─────
    Task("K1", "endstate", [
        "The workspace has kdoc_001.json..kdoc_120.json. Each doc is "
        "{\"id\":n,\"val\":n,\"next\":<id-or-null>}. Start at kdoc_001.json, read "
        "its 'next', follow that doc, repeat until 'next' is null. Sum every "
        "'val' you visited. End with '" + FINAL + " <number>'.",
    ], k1_check, budget=25),
    Task("K2", "endstate", [
        "Find the doc in kdoc_001.json..kdoc_120.json that contains the marker "
        "'ECHO-77'. From that doc follow its 'next' chain to null and sum the "
        "'val's. Then start at kdoc_004.json and follow its 'next' chain to null, "
        "summing those 'val's too. Report the combined sum of both chains. "
        "End with '" + FINAL + " <number>'.",
    ], k2_check, budget=25),
    Task("K3", "endstate", [
        "Follow the 'next' chain starting at kdoc_001.json (each doc has "
        "id/val/next) and collect the visited ids. For each visited id, look up "
        "its score in ktab_scores.csv (columns id,score). Sum those scores. "
        "End with '" + FINAL + " <number>'.",
    ], k3_check, budget=25),
    Task("K4", "endstate", [
        "Follow the 'next' chain starting at kdoc_002.json. One doc in the chain "
        "is malformed JSON — repair it in place so it parses, then continue. Sum "
        "all 'val's visited. End with '" + FINAL + " <number>'.",
    ], k4_check, budget=25),
    Task("K5", "endstate", [
        "Follow the 'next' chain from kdoc_001.json and sum its 'val's. Follow "
        "the 'next' chain from kdoc_003.json and sum its 'val's. Add the two "
        "sums and write k5_out.json as {\"sum\": <number>} with write_file. "
        "End with '" + FINAL + " done'.",
    ], k5_check, budget=25),
    Task("K6", "endstate", [
        "The workspace has kdoc_001.json..kdoc_120.json. Each doc is "
        "{\"id\":n,\"val\":n,\"next\":<id-or-null>}. Start at kdoc_005.json, read "
        "its 'next', follow that doc, repeat until 'next' is null. Sum every "
        "'val' you visited. End with '" + FINAL + " <number>'.",
    ], k6_check, budget=25),
    Task("K7", "endstate", [
        "Follow the 'next' chain starting at kdoc_013.json (each doc has "
        "id/val/next) and sum every 'val' you visit until 'next' is null. "
        "End with '" + FINAL + " <number>'.",
    ], k7_check, budget=25),
    Task("K8", "endstate", [
        "Follow the 'next' chain from kdoc_006.json and sum its 'val's. Follow "
        "the 'next' chain from kdoc_007.json and sum its 'val's. Report the "
        "combined sum of both chains. End with '" + FINAL + " <number>'.",
    ], k8_check, budget=25),
    Task("K9", "endstate", [
        "Follow the 'next' chain starting at kdoc_009.json (each doc has "
        "id/val/next) and collect the visited ids. For each visited id, look up "
        "its score in ktab_scores.csv (columns id,score). Sum those scores. "
        "End with '" + FINAL + " <number>'.",
    ], k9_check, budget=25),
    Task("K10", "endstate", [
        "Follow the 'next' chain from kdoc_008.json and sum its 'val's. Follow "
        "the 'next' chain from kdoc_011.json and sum its 'val's. Add the two "
        "sums and write k10_out.json as {\"sum\": <number>} with write_file. "
        "End with '" + FINAL + " done'.",
    ], k10_check, budget=25),
]


# ── Runner ──────────────────────────────────────────────────────────────────


class Ctx:
    """Assertion context: final answer + events + workspace readers.

    ``started`` is the clock of this run. Files a checker accepts as a result
    must have been created *during* the run — otherwise yesterday's name twin
    wins, and the bench reports green for work it never saw.
    """

    def __init__(self, answer: str, events: list[dict], started: float = 0.0):
        self.answer = answer
        self.events = events
        self.started = started

    def read_json(self, rel: str):
        return json.loads(ws_read(rel))


def _error_class(note: str) -> str:
    """Error taxonomy instead of a free-form note string (SoA: SWE-bench practice)."""
    n = (note or "").lower()
    if n.startswith("engine:"):
        return "engine"
    if n.startswith("error:"):
        return "timeout" if ("timed out" in n or "timeout" in n) else "network"
    if "final=false" in n:
        return "no_final_answer"
    if "assertion-error" in n:
        return "assertion"
    return "assertion"


def _engine_rep(rep: dict) -> bool:
    """True when the engine, not Ephe, ended this rep — so the rep measures nothing.

    The class is set only where no answer content reached the assertions, which is
    why it is the exclusion signal and needs no second flag in the manifest.
    """
    return str(rep.get("error_class") or "") == "engine"


# ── Argument audit ──────────────────────────────────────────────────────────
# `tool_names()` counted calls; a count cannot tell the right file from the wrong
# one. The `tool_start` frame carries the arguments (server/routes/chat.py:803,
# every value clipped at 300 characters by `_clip_tool_value`) and the matching
# `tool_done` frame carries the result, so the pair can be checked deterministically
# with no judge and no change to any task. The required keys below are read from
# `core/tools/_schemas.py` (2026-10-10): they are the tool contract, not a wish.

_ARG_KEYS: dict[str, tuple[str, ...]] = {
    "write_file": ("path", "content"),
    "edit_file": ("path", "old_string", "new_string"),
    "read_file": ("path",),
    "delete_file": ("path",),
    "list_directory": ("path",),
    "file_search": ("query",),
    "run_shell": ("command",),
}
_ARG_CLASS = {
    "write_file": "write_path",
    "edit_file": "edit_pattern",
    "read_file": "read_target",
    "delete_file": "read_target",
    "list_directory": "read_target",
    "file_search": "search_query",
    "run_shell": "shell_prefix",
}
#: Commands that take the rep off the machine the task lives on, or destroy state the
#: bench cannot restore. Everything else is recorded by its leading token, so the
#: distribution stays visible without an allow-list invented here.
_SHELL_DENY = {"curl", "wget", "nc", "ssh", "scp", "pip", "pip3", "npm", "npx", "git",
               "sudo", "rm", "dd", "shutdown", "kill", "pkill", "open"}
#: An absolute token may carry these prefixes without leaving the task's machine
#: context: `2>/dev/null` is not a path the task was about, and flagging it would put
#: noise into the ledger.
_SHELL_SYSTEM_PREFIXES = ("/dev/", "/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/")
_WEB_TOOLS = ("web_search", "fetch_url", "browser_go", "browser_exec", "browser_evaluate",
              "browser_type", "browser_scroll", "browser_screenshot", "browser_press")
#: Hosts where a task's own question, its metadata or its answer can be found. Reaching
#: one of them is not proof of contamination — it is the condition under which the two
#: leak checks below have to be read, and the record that lets them be read later.
#: The three-way split (metadata / question context / answer) is the taxonomy of
#: docs/RESEARCH_ADOPTION_2026-10-09.md item 8.
BENCHMARK_HOSTS = ("huggingface.co", "hf.co", "arxiv.org", "github.com",
                   "raw.githubusercontent.com", "kaggle.com", "paperswithcode.com",
                   "openreview.net", "wikipedia.org")
_CLIP = "…"  # the ellipsis `_clip_tool_value` appends at 300 characters
_FILE_RE = re.compile(r"[A-Za-z0-9_./-]+\.(?:json|md|txt|csv|pdf)")
_DATE_RE = re.compile(r"\b(?:19|20)[0-9]{2}\b")


def task_prompt(task: "Task") -> str:
    return "\n".join(task.turns)


def _tool_calls(events: list[dict]) -> list[dict]:
    """Join `tool_start` and `tool_done` on `call_id`, order-correctly.

    `call_id` is not unique for the life of a session: `_call_id` numbers calls by
    the per-round enumerate index (`core/chat_detect.py:337`), so a many-round turn
    reuses `-0`, `-1`, … every round. A dict keyed by `call_id` that keeps the last
    `tool_done` would then bind an early start to a later round's result and
    mis-attribute the outcome. Matching in stream order — a FIFO of unmatched starts
    per id, the done that arrives closing the oldest one still open — gives each
    start the done that follows it.
    """
    pending: dict[str, deque] = {}
    calls: list[dict] = []
    started: set[str] = set()
    done_ids: set[str] = set()
    n_done = 0
    for e in events:
        etype = e.get("type")
        if etype == "tool_start":
            cid = str(e.get("call_id") or "")
            if cid:
                started.add(cid)
            call = {
                "tool": e.get("tool"),
                "args": e.get("args") if isinstance(e.get("args"), dict) else {},
                "result": "",
            }
            calls.append(call)
            pending.setdefault(cid, deque()).append(call)
        elif etype == "tool_done":
            n_done += 1
            cid = str(e.get("call_id") or "")
            done_ids.add(cid)
            queue = pending.get(cid)
            if queue:
                queue.popleft()["result"] = str(e.get("result") or "")
    orphan = [cid for cid in done_ids if cid and cid not in started]
    if orphan or (n_done and not calls):
        # A done frame with no start frame means the arguments never arrived; say so
        # instead of auditing a call list that is silently missing them.
        calls.append({"tool": None, "args": {}, "result": "", "unmatched_done": True})
    return calls


def _result_error_axis():
    """The product's own error predicate, not a second opinion written here.

    None when `core.quality` cannot be imported: an unavailable axis is named in the
    ledger rather than replaced by a home-made prefix list that could drift.
    """
    try:
        from core.quality import is_error_result

        return is_error_result
    except Exception:  # noqa: BLE001 — the audit degrades, the run continues
        return None


def _path_finding(arg: str, workspace: Path, known: set[str], writable: bool) -> str:
    raw = (arg or "").strip().rstrip(_CLIP)
    if not raw:
        return "" if writable else "empty_path"
    if ".." in Path(raw).parts:
        return "path_outside_workspace"
    name = Path(raw).name
    # Measured: a 300-character clipped argument reaches `Path.exists()` as
    # `[Errno 63] File name too long`, and an audit that raises is read by run_task as
    # `assertion-error` — the instrument blaming Ephe for the instrument. A name the
    # filesystem cannot hold is its own finding.
    if len(name) > 255 or len(raw) > 4096:
        return "unusable_path"
    root = Path(os.path.realpath(str(workspace)))
    if Path(raw).is_absolute():
        if not str(os.path.realpath(raw)).startswith(str(root)):
            return "path_outside_workspace"
    if writable:
        return ""
    try:
        exists = (root / raw).exists()
    except OSError:
        return "unusable_path"
    return "" if (name in known or exists) else "unknown_target_file"


def arg_audit(task: "Task", events: list[dict], workspace: Path,
              fixture_files: list[str]) -> dict:
    """Check what each call pointed at; deterministic, and it does not touch `ok`.

    The verdict stays the assertion's: folding argument findings into pass^3 would
    move the metric under a run that is in flight, and below the floor
    `evals/noise_floor.py` derives. Hard findings are mechanical contract breaks;
    soft ones are observations the bench records but does not judge.
    """
    calls = _tool_calls(events)
    known = set(fixture_files)
    classes: dict[str, int] = {}
    violations: list[dict] = []
    observations: list[dict] = []
    ledger: list[dict] = []
    is_err = _result_error_axis()
    prompt_files = {Path(p).name for p in _FILE_RE.findall(task_prompt(task))}
    root = os.path.realpath(str(workspace))
    for call in calls:
        if call.get("unmatched_done"):
            observations.append({"code": "stream_without_tool_start"})
            continue
        tool = call["tool"] or ""
        args = call["args"]
        # A digest per call, so an argument that changed after the fact is visible in the
        # trace: the manifest used to carry tool names only, which is what let a name-level
        # scorer report success the arguments did not support
        # (docs/RESEARCH_ADOPTION_2026-10-09.md item 3).
        digest = hashlib.sha256(
            json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:10]
        ledger.append({
            "tool": tool,
            "digest": digest,
            "target": str(args.get("path") or args.get("query")
                          or args.get("command") or args.get("url") or "")[:60],
        })
        cls = _ARG_CLASS.get(tool)
        if cls:
            classes[cls] = classes.get(cls, 0) + 1
        for key in _ARG_KEYS.get(tool, ()):
            value = str(args.get(key) or "")
            if not value:
                violations.append({"code": f"missing_arg:{key}", "tool": tool})
            elif value.endswith(_CLIP):
                observations.append({"code": f"arg_truncated:{key}", "tool": tool})
        path = str(args.get("path") or "")
        if tool in _ARG_KEYS and "path" in _ARG_KEYS[tool] and path:
            code = _path_finding(path, workspace, known, writable=(tool == "write_file"))
            if code:
                violations.append({"code": code, "tool": tool, "arg": path[:60]})
            base = Path(path).name
            if tool == "write_file" and base:
                known.add(base)
                if base not in prompt_files:
                    observations.append({"code": "write_target_unnamed_in_prompt", "arg": base})
            if tool == "edit_file":
                old = str(args.get("old_string") or "")
                if old and old == str(args.get("new_string") or ""):
                    violations.append({"code": "edit_no_change", "tool": tool})
        if tool == "run_shell":
            cmd = str(args.get("command") or "").strip()
            head = cmd.split()[0] if cmd else ""
            if head:
                observations.append({"code": "shell_prefix", "arg": head})
                if head.split("/")[-1] in _SHELL_DENY:
                    violations.append({"code": "shell_denied_prefix", "tool": tool, "arg": head})
            for token in cmd.split():
                clean = token.strip("\"'")
                if (clean.startswith("/") and not clean.startswith(root)
                        and not clean.startswith(_SHELL_SYSTEM_PREFIXES)):
                    violations.append({"code": "path_outside_workspace", "tool": tool,
                                       "arg": clean[:60]})
        if is_err is not None and call["result"] and is_err(call["result"]):
            violations.append({
                "code": "tool_result_error", "tool": tool,
                "arg": str(args.get("path") or args.get("query") or args.get("command") or "")[:60],
            })
    counts: dict[str, int] = {}
    for v in violations:
        counts[v["code"]] = counts.get(v["code"], 0) + 1
    return {
        "calls": len([c for c in calls if c.get("tool")]),
        "ledger": ledger,
        "classes": classes,
        "violations": violations,
        "violation_counts": counts,
        "observations": observations,
        "result_axis": "core.quality" if is_err is not None else "unavailable",
    }


def retrieval_ledger(events: list[dict], answer: str, prompt: str, expected: str = "") -> dict:
    """Was this answer grounded in the fixtures, or fetched? Recorded, not claimed.

    A GAIA task scores on one exact final answer, so a number that was *looked up*
    passes for a reason the assertion cannot see — and a closed-book number may be
    memorised rather than computed. This ledger holds the evidence to say which later;
    nothing here asserts it now, and only the `gaia` family is asked for it.

    Two checks are mechanical: the expected answer appearing in fetched text, and a
    seven-word run of the task's own instruction appearing there. The `FINAL ANSWER:`
    convention is stripped from the instruction first, because that wording is shared
    by every task and would flag pages that have nothing to do with this one. Note the
    bound: `tool_done` results reach the bench clipped at 3000 characters
    (`server/routes/chat.py:809`), so a leak further down a long page is not visible
    here.
    """
    web: dict[str, int] = {}
    queries: list[str] = []
    hosts: list[str] = []
    source_dates: set[str] = set()
    fetched: list[str] = []
    for e in events:
        if e.get("type") != "tool_start":
            continue
        tool = str(e.get("tool") or "")
        if tool not in _WEB_TOOLS:
            continue
        web[tool] = web.get(tool, 0) + 1
        args = e.get("args") if isinstance(e.get("args"), dict) else {}
        for key in ("query", "url"):
            value = str(args.get(key) or "")
            if value:
                queries.append(value[:120])
                hosts += re.findall(r"https?://([^/\s\"']+)", value)
    for e in events:
        if e.get("type") == "tool_done" and str(e.get("tool") or "") in _WEB_TOOLS:
            text = str(e.get("result") or "")
            fetched.append(text)
            hosts += re.findall(r"https?://([^/\s\"')]+)", text)[:8]
            source_dates.update(_DATE_RE.findall(text))
    blob = "\n".join(fetched).lower()
    # Match on tokens, not on the raw text: a page that quotes the instruction writes
    # "remain (capacity minus reserved)", and a joined word run would miss its own
    # punctuation. Same normalisation on both sides or the check is decoration.
    blob_tokens = " ".join(re.findall(r"[a-z0-9_.]+", blob))
    instruction = re.sub(FINAL + r".*", "", prompt, flags=re.I)
    words = re.findall(r"[a-z0-9_.]+", instruction.lower())
    shingles = {" ".join(words[i:i + 7]) for i in range(0, max(len(words) - 6, 0))}
    hits = sorted({h.rstrip(".") for h in hosts})
    want = (expected or "").strip().lower()
    answer_leak = bool(want) and bool(blob) and re.search(
        r"(?<![\w.])" + re.escape(want) + r"(?![\w.])", blob) is not None
    return {
        "web_calls": sum(web.values()),
        "tools": web,
        "queries": queries[:8],
        "hosts": hits[:8],
        "benchmark_host_hits": sorted({h for h in hits
                                       if any(h.endswith(bh) or bh in h for bh in BENCHMARK_HOSTS)}),
        "answer_leak": answer_leak,
        "question_leak": sorted({s for s in shingles if s and s in blob_tokens})[:3],
        "source_dates": sorted(source_dates),
        "prompt_dates": sorted(set(_DATE_RE.findall(prompt))),
        "answer_dates": sorted(set(_DATE_RE.findall(answer))),
        "provenance": "retrieved" if web else "closed-book",
    }


def run_task(task: Task, rep: int) -> dict:
    session_id = f"ob-{task.id.lower()}-r{rep}-{int(time.time())}"
    history: list[dict] = []
    last_answer = ""
    all_events: list[dict] = []
    first_event_ms = None
    t0 = time.perf_counter()
    started = time.time()
    error = None
    fixture_hash = _fixture_hash()
    fixture_files = _fixture_files()
    turn_usages: list[dict] = []
    for turn in task.turns:
        try:
            answer, events, ttft, usage = stream_turn_retry(turn, history, session_id, task.budget)
        except Exception as exc:  # noqa: BLE001 — manifest keeps running
            error = f"engine: transport {type(exc).__name__}: {exc}"
            break
        if usage:
            turn_usages.append(usage)
        if first_event_ms is None and ttft is not None:
            first_event_ms = ttft
        all_events.extend(events)
        last_answer = answer
        history = history + [
            {"role": "user", "content": turn},
            {"role": "assistant", "content": answer},
        ]
    wall_ms = round((time.perf_counter() - t0) * 1000, 1)
    # W1-R3: a silently throttled engine is not an agent failure. Without this
    # line a rate limit sits in the bench as "assertion", and the bench blames
    # Ephe for something the provider did.
    if not error:
        engine_errors = [str(e.get("msg") or "") for e in all_events if e.get("type") == "error"]
        # The same line the server draws in `silent_turn_message`: no text *and* no
        # tool run is an engine that never spoke, while a run that called tools and
        # then fell silent is an agent that did not finish. Measured 2026-10-09 in the
        # live matrix: W4 r3 burned its tool budget after 4 calls and 1399 completion
        # tokens, and the wide rule hid that result as plumbing.
        ran_tools = any(e.get("type") == "tool_done" for e in all_events)
        spoke_tokens = any(int(u.get("completion_tokens") or 0) for u in turn_usages)
        if engine_errors and not last_answer.strip() and not ran_tools and not spoke_tokens:
            error = "engine: " + (engine_errors[-1][:160] or "no answer content")
    ctx = Ctx(last_answer, all_events, started)
    try:
        ok, note = (False, error) if error else task.check(ctx)
    except Exception as exc:  # noqa: BLE001 — a broken assertion is a fail
        ok, note = False, f"assertion-error: {exc}"
    error_class = None if ok else _error_class(note)
    tool_timings = [
        {"tool": e.get("tool"), "ms": e.get("duration_ms")}
        for e in all_events
        if e.get("type") == "tool_done" and e.get("duration_ms") is not None
    ]
    # ── N7: the real token axis (usage passthrough from the SSE stream) + USD ──
    # usage frames come measured by the provider (usage_estimated=False) or from
    # the estimator (True) — both cases go into the manifest openly, never silently 0.
    tok_in = sum(int(u.get("prompt_tokens") or 0) for u in turn_usages)
    tok_out = sum(int(u.get("completion_tokens") or 0) for u in turn_usages)
    est_flags = [bool(u.get("usage_estimated", True)) for u in turn_usages]
    cost = round(
        tok_in / 1e6 * PRICE_IN_PER_M + tok_out / 1e6 * PRICE_OUT_PER_M, 6
    ) if turn_usages else None
    manifest = {
        "schema_version": 5,
        # The address a number is reproducible from: HEAD plus the committed content
        # of the surface that answered. None when the tree cannot say, and the scorer
        # reads that as unaddressed rather than as agreement.
        "code_address": _code_address(),
        "task_id": task.id,
        "family": task.family,
        "level": LEVELS.get(task.id, "L2"),
        "rep": rep,
        "session_id": session_id,
        "seed": 0,
        "temperature": 0,
        "ok": bool(ok),
        "note": note,
        # `error_class == "engine"` is the scorer's signal that this rep never
        # reached a model — see `_active_model` for why that is not a task loss.
        "error_class": error_class,
        "wall_ms": wall_ms,
        "ttft_first_event_ms": first_event_ms,
        "n_turns": len(task.turns),
        "tool_timings": tool_timings,
        # Argument level, next to the call count: `tool_calls` says a call happened,
        # only the arguments say whether it was aimed at the right file.
        "arg_audit": arg_audit(task, all_events, WORKSPACE, fixture_files),
        "final_answer_line": next(
            (ln.strip() for ln in last_answer.splitlines() if ln.strip().upper().startswith(FINAL)),
            "",
        ),
        "tool_calls": tool_names(all_events),
        "answer_chars": len(last_answer),
        "tokens_out_proxy": round(len(last_answer) / 4.0, 1),
        "prompt_tokens": tok_in or None,
        "completion_tokens": tok_out or None,
        "total_tokens": (tok_in + tok_out) or None,
        "usage_estimated": all(est_flags) if est_flags else None,
        "cost_usd": cost,
        "pricing_source": PRICING_SOURCE,
        "fixture_hash": fixture_hash,
        "fixture_files": len(fixture_files),
        "answer_tail": last_answer[-600:],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    # Only `gaia` is asked where its number came from: it is the family whose exact
    # match can be satisfied by a lookup or a memorised fact instead of the fixture.
    if task.family == "gaia":
        want = re.search(r"final-answer==(.+)", str(note or ""))
        manifest["retrieval"] = retrieval_ledger(
            all_events, last_answer, task_prompt(task), want.group(1) if want else ""
        )
    return manifest


def _audit_summary(reps: list[dict]) -> str:
    """One scorecard line's worth of argument and provenance evidence."""
    counts: dict[str, int] = {}
    calls = 0
    for r in reps:
        audit = r.get("arg_audit") or {}
        calls += int(audit.get("calls") or 0)
        for code, n in (audit.get("violation_counts") or {}).items():
            counts[code] = counts.get(code, 0) + int(n)
    parts = [f"calls={calls}", "violations=" + (json.dumps(counts, sort_keys=True) if counts else "none")]
    provenance = {(r.get("retrieval") or {}).get("provenance") for r in reps if r.get("retrieval")}
    if provenance:
        parts.append("provenance=" + "/".join(sorted(str(p) for p in provenance if p)))
    return "  ".join(parts)


def score(runs: list[dict]) -> str:
    lines = ["# Option-B bench — pass^3 scorecards\n"]
    families: dict[str, list[dict]] = {}
    for r in runs:
        families.setdefault(r["family"], []).append(r)
    grand = []
    blocked: list[str] = []
    for task in TASKS:
        all_reps = [r for r in runs if r["task_id"] == task.id]
        if not all_reps:
            continue
        reps = [r for r in all_reps if not _engine_rep(r)]
        if len(reps) != len(all_reps):
            # The engine ended at least one rep, so this task has no measurement of
            # Ephe in it. Excluded from the denominator like an incomplete rep set —
            # `bench_trend.compute_point` applies the same rule to the trend. The
            # other reps' failures are still printed: exclusion must not hide them.
            blocked.append(task.id)
            engine_notes = [r["note"][:70] for r in all_reps if _engine_rep(r)]
            other_notes = [r["note"][:70] for r in reps if not r["ok"]]
            lines.append(
                f"- {task.id} ({task.family}): pass^3=BLOCKED "
                f"({len(engine_notes)}/{len(all_reps)} reps never reached the engine: "
                f"{engine_notes}"
                + (f")  other failed reps: {other_notes}" if other_notes else ")")
            )
            continue
        passed = sum(1 for r in reps if r["ok"])
        p3 = passed == len(reps) == 3
        grand.append(p3)
        walls = [r["wall_ms"] / 1000 for r in reps]
        lines.append(
            f"- {task.id} ({task.family}): pass^3={'PASS' if p3 else 'FAIL'} "
            f"({passed}/{len(reps)} reps)  wall_median={sorted(walls)[len(walls) // 2]:.1f}s  "
            f"{_audit_summary(reps)}  "
            f"notes={[r['note'] for r in reps if not r['ok']] or 'ok'}"
        )
    if grand:
        lines.append(f"\n**pass^3 total**: {sum(grand)}/{len(grand)} tasks fully reliable")
    if blocked:
        lines.append(
            f"**engine-blocked, not scored**: {len(blocked)} task(s) — {', '.join(blocked)}"
        )
    out = RUNS.parent / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)


def reset_task_state(task: Task) -> None:
    """Put the workspace back into the state `task`'s check is written against.

    One call per rep, before the rep runs. A rep must not inherit an earlier rep's
    end-state file (it would pass on a file it never produced), and a repair task must
    meet the broken fixture again every rep (otherwise only rep 1 sees it). Both halves
    live here so the reset and the checks stay one list instead of two that drift.
    """
    if task.id == "T4":
        (WORKSPACE / "nota.md").unlink(missing_ok=True)
    if task.id == "W2":
        (WORKSPACE / "report.md").unlink(missing_ok=True)
        (WORKSPACE / "report-v2.md").unlink(missing_ok=True)
        (WORKSPACE / "index.md").unlink(missing_ok=True)
    if task.id == "W1":
        (WORKSPACE / "todos.json").unlink(missing_ok=True)
    # G3/G4 land a file an artifact check accepts, and that check reads four homes:
    # clearing only the workspace copy leaves a prior rep's PDF in one of the others.
    if task.id == "G3":
        clear_artifacts(_accepts_g3_artifact)
    if task.id == "G4":
        clear_artifacts(_accepts_g4_artifact)
    # N5 expansion — per-rep artifact reset (each task owns its files)
    if task.id == "T5":
        write_fixtures()  # restore bookings_t5.json to fixture state
    if task.id == "T7":
        (WORKSPACE / "nota3.md").unlink(missing_ok=True)
    if task.id == "W3":
        (WORKSPACE / "merged.json").unlink(missing_ok=True)
    if task.id == "W4":
        (WORKSPACE / "b.txt").unlink(missing_ok=True)
        (WORKSPACE / "c.txt").unlink(missing_ok=True)
        (WORKSPACE / "a.txt").write_text("seed\n", encoding="utf-8")
    if task.id == "W5":
        (WORKSPACE / "data.json").unlink(missing_ok=True)
        (WORKSPACE / "report.md").unlink(missing_ok=True)
    if task.id == "W6":
        (WORKSPACE / "done.json").unlink(missing_ok=True)
    # N6 expansion — per-rep artifact reset (fixtures restored idempotent)
    if task.id in ("T8", "T16", "G13"):
        write_fixtures()
        (WORKSPACE / "t8.csv").unlink(missing_ok=True)
        (WORKSPACE / "t16.json").unlink(missing_ok=True)
        (WORKSPACE / "g13.json").unlink(missing_ok=True)
    if task.id == "W7":
        for i in (1, 2, 3):
            (WORKSPACE / f"w7_{i}.txt").unlink(missing_ok=True)
    if task.id == "W8":
        for n in ("b.txt", "c.txt", "d.txt"):
            (WORKSPACE / n).unlink(missing_ok=True)
        (WORKSPACE / "a.txt").write_text("seed\n", encoding="utf-8")
    if task.id == "W10":
        write_fixtures()  # restore partial-only fixtures
        for i in range(1, 5):
            (WORKSPACE / f"w10_{i}.json").write_text(
                json.dumps({"partial": i}, indent=2), encoding="utf-8"
            )
    if task.id == "W11":
        (WORKSPACE / "w11_out.json").unlink(missing_ok=True)
    if task.id == "W12":
        (WORKSPACE / "w12_log.md").write_text("# log\n", encoding="utf-8")
    if task.id == "W13":
        (WORKSPACE / "w13_a.txt").unlink(missing_ok=True)
        (WORKSPACE / "w13_c.txt").unlink(missing_ok=True)
        (WORKSPACE / "w13_b.txt").write_text("b\n", encoding="utf-8")
    if task.id == "W14":
        (WORKSPACE / "w14_union.json").unlink(missing_ok=True)
    if task.id == "W15":
        (WORKSPACE / "w15_gamma.txt").unlink(missing_ok=True)
        (WORKSPACE / "w15_beta.txt").unlink(missing_ok=True)
        (WORKSPACE / "w15_alpha.txt").write_text("alpha\n", encoding="utf-8")
        (WORKSPACE / "w15_index.md").write_text(
            "# Index\n- w15_alpha.txt\n", encoding="utf-8"
        )
    if task.id == "W16":
        (WORKSPACE / "w16_out.json").unlink(missing_ok=True)
    # N9b (L5) — the K tasks write their output json into the workspace; the reset
    # removes it so a rep can only pass on a file it wrote itself.
    if task.id == "K5":
        (WORKSPACE / "k5_out.json").unlink(missing_ok=True)
    if task.id == "K10":
        (WORKSPACE / "k10_out.json").unlink(missing_ok=True)
    # Repair tasks (W9, T13, K4): re-materialise the malformed fixture so every rep
    # meets the broken form, not the one the previous rep repaired in place.
    if task.id in BROKEN_FIXTURES:
        name, body = BROKEN_FIXTURES[task.id]
        (WORKSPACE / name).write_text(body, encoding="utf-8")


def purge_cohort_state() -> None:
    """Clear the bench's own directories once, before the first fixture write.

    WORKSPACE is this cohort's isolated tree (`EPHE_BENCH_WORKSPACE` or `<scratch>/ws`)
    and the surface is verified to work there and nowhere else; OUTPUT_DIR is
    `<scratch>/out`, the second home an artifact check scans. Both belong to the bench
    alone, never to a user path, so removing them whole is safe. Without this a
    `k10_out.json`, a repaired `w9_broken.json`/`t13_cfg.json`/`kdoc_119.json`, or a
    stale `file-summary.pdf` from a previous cohort survives into rep 1 — the plain
    defect the earlier skips and resets left open.

    The runs directory is deliberately not purged: those manifests are the record the
    resume path reads, so a cohort that mixes is caught by `resume_conflict` instead.
    """
    for home in (WORKSPACE, OUTPUT_DIR):
        shutil.rmtree(home, ignore_errors=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def cohort_mix(rows: list[dict]) -> str | None:
    """A refusal line when the manifests on disk span more than one measured surface.

    `--score` reads whatever sits in the runs directory, and the resume path keeps an
    earlier cohort's manifest and writes a fresh one beside it; either way one number
    would be computed over two different servers. `bench_code_address.cohort_state`
    already tells the two apart, so the guard reads it here rather than leaving the
    mixing to a skip line nobody parses.
    """
    state = _cohort_state(rows)
    if state["stands"] > 1:
        return (
            f"the runs directory mixes {state['stands']} measured surfaces over "
            f"{state['commits']} commit(s): {state['reps_per_stand']}"
        )
    return None


def resume_conflict(rows: list[dict], current: dict | None) -> str | None:
    """Refuse to append this run's reps beside manifests from a different surface."""
    mix = cohort_mix(rows)
    if mix:
        return mix
    if not rows or current is None:
        return None
    stands = {
        str((_code_of(row) or {}).get("surface_sha") or "unread")
        for row in rows
        if _code_of(row)
    }
    if stands and stands != {str(current.get("surface_sha"))}:
        short = ", ".join(sorted(s[:12] for s in stands))
        return (
            f"resume would append surface {str(current.get('surface_sha'))[:12]} beside "
            f"{len(rows)} manifest(s) already on {short}"
        )
    return None


def manifest_stand(path: Path) -> str:
    """The stand a manifest was measured on, stated from its own address, not this tree's."""
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — an unreadable manifest still has to be named
        return "unreadable manifest"
    addr = _code_of(row) or {}
    return (
        f"commit {addr.get('commit_short') or 'unaddressed'}, "
        f"surface {str(addr.get('surface_sha') or 'unread')[:12]}, ts {row.get('ts')}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated task ids (e.g. T2,G3)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--score", action="store_true", help="score existing manifests only")
    ap.add_argument(
        "--allow-mixed-cohort",
        metavar="REASON",
        help=(
            "score or resume a runs directory that spans two measured surfaces; the "
            "reason is recorded in the output. Without it a mixed cohort is refused"
        ),
    )
    ap.add_argument(
        "--export-trajectory",
        action="store_true",
        help="write runs as JSONL training trajectories (research-ready format)",
    )
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    if args.score:
        runs = [json.loads(f.read_text(encoding="utf-8")) for f in _manifest_paths(RUNS)]
        mix = cohort_mix(runs)
        if mix and not args.allow_mixed_cohort:
            print(f"[precondition] {mix}", file=sys.stderr)
            print(
                "[precondition] a pass^3 over two servers is not one number: score a single "
                "cohort's runs directory, or pass --allow-mixed-cohort REASON to record why "
                "the mix is intended",
                file=sys.stderr,
            )
            raise SystemExit(2)
        if mix:
            print(f"[cohort] scoring a mixed cohort, waived: {args.allow_mixed_cohort}", flush=True)
        print(score(runs))
        if args.export_trajectory:
            export_trajectory(runs)
        return

    only = {t.strip().upper() for t in args.only.split(",")} if args.only else None
    tasks = [t for t in TASKS if not only or t.id in only]

    try:
        engine = _preflight()
    except EngineUnavailable as exc:
        ids = ", ".join(t.id for t in tasks[:12])
        if len(tasks) > 12:
            ids += f", +{len(tasks) - 12} more"
        print(f"[precondition] {exc}", file=sys.stderr)
        print(
            f"[precondition] nothing recorded: all {len(tasks)} selected task(s) need that "
            f"engine ({ids})",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(f"[preflight] {engine} answered one turn on {BASE}", flush=True)

    # The directory has to exist before the surface can be read: an unset or missing path
    # resolves to the backend's cwd, and that answer would be indistinguishable from another
    # conversation's workspace. Fixture writing follows the verdict.
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    try:
        require_isolated_surface(BASE, WORKSPACE)
    except SurfaceNotIsolated as exc:
        print(f"[precondition] {exc}", file=sys.stderr)
        print(
            f"[precondition] nothing recorded: {BASE} works outside {WORKSPACE}, and a run "
            f"started there would measure the fixture tree for every other conversation",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(f"[workspace] {WORKSPACE} verified on {BASE}: the harness never repoints a surface", flush=True)

    # Cohort start: the bench's own directories are cleared whole before the first
    # fixture write, so nothing an earlier cohort left behind can satisfy rep 1.
    purge_cohort_state()

    # A skipped manifest keeps an earlier cohort's stand beside this run's, and `--score`
    # then reads the mix. Refuse it here unless the mix is explicitly waived.
    previous = [json.loads(f.read_text(encoding="utf-8")) for f in _manifest_paths(RUNS)]
    conflict = resume_conflict(previous, _code_address())
    if conflict and not args.allow_mixed_cohort:
        print(f"[precondition] {conflict}", file=sys.stderr)
        print(
            "[precondition] a skipped manifest would keep another cohort's stand beside this "
            "run's: use a fresh EPHE_BENCH_DIR, or pass --allow-mixed-cohort REASON",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if conflict:
        print(f"[cohort] resuming a mixed cohort, waived: {args.allow_mixed_cohort}", flush=True)

    write_fixtures()

    for task in tasks:
      for rep in range(1, args.reps + 1):
          out = RUNS / f"{task.id.lower()}_r{rep}.json"
          if out.exists():
              # Name the stand the skipped manifest was measured on: a resume that keeps
              # an earlier cohort's file must say so, not print a bare filename.
              print(f"[skip] {out.name}  ({manifest_stand(out)})", flush=True)
              continue
          # One call per rep, before the rep runs: every file a check reads is either
          # removed (an inherited copy cannot pass for the rep) or restored to the form
          # the rep is meant to meet. See `reset_task_state`.
          reset_task_state(task)
          print(f"[run ] {task.id} rep {rep}/{args.reps} …", flush=True)
          result = run_task(task, rep)
          out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
          print(
              f"[done] {out.name} ok={result['ok']} wall={result['wall_ms'] / 1000:.1f}s "
              f"tools={len(result['tool_calls'])} note={result['note'][:60]}",
              flush=True,
          )
    runs = [json.loads(f.read_text(encoding="utf-8")) for f in _manifest_paths(RUNS)]
    print(score(runs))
    if args.export_trajectory:
        export_trajectory(runs)


def export_trajectory(runs: list[dict]) -> Path:
    """Write runs as JSONL training trajectories (one line per rep).

    Research-ready framing (cf. trajectory generation for tool-calling model
    training): each record carries the task prompt, the tool ledger, the
    final answer, and the verdict — enough to fine-tune or to replay.
    Never committed: output lands in /tmp/bench-option-b/trajectories.jsonl.
    """
    out = RUNS.parent / "trajectories.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(
                json.dumps(
                    {
                        "task_id": r["task_id"],
                        "family": r["family"],
                        "rep": r["rep"],
                        "ok": r["ok"],
                        "tool_calls": r["tool_calls"],
                        # Without this the exported trace cannot show what a call was
                        # aimed at, and an argument-level regression is undetectable
                        # after the run.
                        "arg_ledger": (r.get("arg_audit") or {}).get("ledger", []),
                        "arg_violations": (r.get("arg_audit") or {}).get("violation_counts", {}),
                        "retrieval": r.get("retrieval"),
                        "final_answer": r.get("final_answer_line", ""),
                        "answer_tail": r.get("answer_tail", ""),
                        "wall_ms": r.get("wall_ms"),
                        "ts": r.get("ts"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"[trajectory] {len(runs)} records -> {out}")
    return out


if __name__ == "__main__":
    main()
