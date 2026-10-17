# Benchmarks

Ephe ships a reproducible agent benchmark (`evals/bench_option_b.py`): 60 tasks across three families
(τ-style policy compliance 17, GAIA-style research 17, end-state verification 26; counted from its
`TASKS` list on 2026-10-10). Every task runs **3 times at temperature 0** (`--reps` default,
`"temperature": 0` in the request) against the real streaming endpoint, and scoring is `pass³`: a task
counts only when **all three runs** succeed. For scale, frontier-class agents score below 50 % at pass¹
on τ-bench retail.

**Per-plugin golden matrix** (`ephe bench`): every production plugin carries a golden suite —
`plugins/<name>/prompts/golden.jsonl` (at least 6 mechanically gradable cases: real artifacts, real
tool calls, anti-slop traps) plus `prompts/rubric.md`. **92 cases across 14 plugins** as of the E4
wave. Two paths share one semantics:

- `ephe bench` (no flags) is the structural verify-gate every CI run and every commit passes; it
  needs no engine.
- `ephe bench --run [plugin …]` measures **pass³** (all 3 runs must pass, the same TAU-reliability
  semantics as Option B) against the configured engine, writes reports to `~/.ephe/benchmarks/`, and
  gates at **pass³ ≥ 90 % per plugin**.

The reference target is Opus 5.5 / GPT Astra 6 — measured there when such an engine is configured,
never claimed from a smaller run.

**Latest full run** (2026-10-12, commit `613a8945`, engine `qwen3.8-flash-next`):

| Metric | Value |
|---|---|
| pass³ | **57 / 60 (95.0 %)** |
| Families | τ-policy 94 % · GAIA-style 100 % · end-state 92 % |
| Wall-clock median | ~25 s per run |
| TTFT median | ~155 ms (streaming first event) |
| Cost of the full matrix | ~$0.50 (local-first engine) |

Every figure in that table is a single trend point and
**volatile** — it moves with each run. The ledger is the authority when the two disagree; the table is
the reading at commit `613a8945`.

Scope: this is a **product benchmark**, not an academic SOTA claim. It measures Ephe's own success
criteria with a fully reproducible harness (deterministic scoring, no LLM judge), and the tracked run
manifests are the evidence. Methodology, family definitions, and the deliberate limits live in
[`benchmark-mapping.md`](benchmark-mapping.md); the CI job re-aggregates pass³ from the
manifests without any model in the loop.
