# Latency budgets — what the serial timing segment holds

`tests.yml` runs four timing files and six budget node ids in "Run timing gates (serial)" and keeps
them out of the `-n auto` leg; `tests/test_timing_assertion_guard.py` holds that split and
`tests/timing_segment.py` holds the runtime half. This page is where those budgets' numbers live,
which is what `tests/test_wall_clock_budgets.py` and the workflow point at when they say a number
"stays where `docs/LATENCY_BUDGETS.md` put it".

A budget is a wall clock, so the reading belongs to a machine and a condition:

- **Machine:** Apple Silicon, macOS 26.6, arm64, 10 CPU — a developer box, which is what the
  `_LOCAL_BASELINE_ONLY` gates in `tests/test_bench_gates.py` are written for.
- **Runtime:** Python 3.13.18, the repository's own `.venv`.
- **Tree:** `5ebce54`, measured 2026-11-24 00:36 +01:00.
- **Engine:** none. The suite runs offline against the mock Ollama fixtures in `tests/conftest.py`,
  and the TTFB gate answers from a fake provider at 50 ms per token. No number here is an engine
  turn, which is what owner decision 2026-10-11 asks a published number to say.
- **Load:** 3.00 runnable tasks at the start of the run, 0.30 per CPU, under the 2.0 per CPU bar in
  `core/load_bar.py`.

Server start-up, `import server.main` and `ephe doctor` are measured on
[`PERFORMANCE_BASELINE.md`](PERFORMANCE_BASELINE.md) and are not repeated here.

## The gates and the numbers they hold

Taken with the segment's own node list, read out of the workflow:

```bash
export EPHE_CONFIG_DIR=$(mktemp -d)
python -m pytest -q -s $(the node ids of "Run timing gates (serial)" in .github/workflows/tests.yml) \
  -p no:cacheprovider --benchmark-json=.benchmarks/bench-timing.json
```

| gate | budget | measured on this machine | verdict |
|---|---|---|---|
| `test_bench_gates.py::test_startup_budget` — one `ephe --version` spawn | p90 150 ms | p50 143.1 ms, p90 163.9 ms, mean 150.6 ms; interpreter boot p50 24.2 ms, ratio 5.92 | pass |
| `test_bench_gates.py::test_ttfb_budget` — first token from the fake provider | mean 500 ms | p50 56.1 ms, mean 56.5 ms; spread p50 57.0 ms, worst 59.9 ms | pass |
| `test_wall_clock_budgets.py::test_search_route_cold_call_within_budget` — first `GET /api/search`, which also builds the FTS index | 200 ms | 9.2 ms | pass |
| `test_bilingual_bench_p3b.py::test_build_skill_index_cold_latency` — one uncached `build_skill_index()` over the 154 builtin skill files | 50 ms | 0.2–0.8 ms with the page cache warm | pass |
| `test_bench_gates.py::test_memory_budget` — 60 turns | 0.50 MB/turn | −0.053 MB/turn | pass |

`17 passed, 1 skipped` in 12.67 s. The skip is
`tests/test_r25_latency_budgets.py:78`, a live-endpoint budget that names its own requirement
(`EPHE_DGX_BASE` plus `EPHE_DGX_MODEL`): no number here claims anything about a remote endpoint.

## Why the start-up p90 exceeds its own budget and still passes

The nominal ceiling is 150 ms (`STARTUP_BUDGET_S`, `tests/test_bench_gates.py:71`), and today's p90
is 163.9 ms — above it. The gate does not decide on that number: `startup_gate_verdict` compares the
median spawn against the median interpreter boot of the same moment, so CPU contention moves both
sides, and the absolute p90 is reported rather than asserted. A box where the ratio stays in band and
the absolute number is over budget is the re-baseline case the gate's own docstring names, not a
product regression. Anyone publishing a start-up p90 from this tree publishes the boot p50 beside it
or the number means nothing.

## What the search budget does and does not measure

`core/session_search.py` points here for its honest limits, so they are stated with the code that
holds them:

- The timer in `server/routes/search.py:24-27` encloses `search_messages()` only. The optional `role`
  filter runs after the timer stops, so `elapsed_ms` is not what a browser waits for end to end, and
  the number above is the route's own accounting, read at the same place the gate asserts it.
- The index run is inside that call but is `O(changed sessions)`: a session file whose fingerprint
  already matches is not re-read (`core/session_search.py:182-218`), so a steady-state search touches
  0 files. The 9.2 ms above is a cold call in the sense the test means — a fresh database whose FTS
  index has to be built once — not a search after a long idle period.
- A query full of FTS5 operators is not a latency risk: `core/session_search.py:118` falls back to a
  phrase-quoted query instead of letting the syntax raise, so the budget is never measured against a
  crash path.

## The condition this page refuses to publish

Until 2026-11-24 the workflow comment above the serial step quoted five numbers "measured with the
parallel leg running beside this segment at load ~15": a 127.7 ms start-up p90, a 54.5 ms TTFB mean,
a 2.4 ms search route, a 61.8 ms idle p90, and a cold index that missed at 54.6 ms. None of them is
reproducible, and the reason is the segment's own rule: measured at 00:38 with `pytest tests/ -n auto`
running beside it, load 2.1 runnable tasks per CPU, all **18** timing gates skipped with

```
serial timing segment: load 2.1 runnable tasks per CPU (bar 2.0), so a budget read here measures the machine
```

A wall clock read under `-n auto` is not evidence (`tests/AGENTS.md`), so a number taken in that
condition cannot be taken at all. The four Linux legs also share one box through three listeners,
which [`decisions/ci-capacity-and-runners.md`](decisions/ci-capacity-and-runners.md) covers; this
page does not restate it.

The cold index is the same story in miniature: the gate takes one uncached sample, and the first
sample taken while a parallel leg drains measured 198 ms and 395 ms on this box against the 50 ms
ceiling, while every sample taken with the page cache warm landed between 0.2 ms and 0.8 ms. The
ceiling is a claim about a quiet box; on a busy one the sample measures the queue.

## Re-taking these numbers

Run the segment on a machine that is doing nothing else, with the load printed in the record. Where
a row cannot be measured today, the row is deleted rather than carried forward from a log: a number
from a run nobody can re-take is not a number, and CI has not run on this repository since
2026-11-21 — the Actions budget is the reason, in the decision record above.
