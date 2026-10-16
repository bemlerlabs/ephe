# Benchmark Mapping Evaluation — Should Ephe Attach to TAU-bench / GAIA?

**Date:** 2026-09-12 · **Status:** Recommendation (decision: B) · **Scope:** Evaluation strategy only; no code changes proposed here.

> **Current state (2026-09-24):** the Option-B harness grew from the 10-task
> pilot to a **60-task matrix** (tau 17 / gaia 17 / endstate 26, 3 reps each).
> Latest trend entry (2026-10-12): **57/60 = 95.0% ± 6.0** pass^3, median wall
> 24.6 s.

## 1. Starting Point

Ephe runs an internal product benchmark: a 12-task matrix covering the four
pillars (research / document / code / multi-tool), 3 repetitions per task,
executed against an OpenAI-compatible endpoint (qwen3.8-flash-next). Scoring is
composed of (a) task completion, (b) the deterministic quality gate
(`core/quality.py::evaluate_quality`), and (c) artifact verification
(`verify_artifact`, `validate_pdf_artifact`, etc.).

This benchmark measures *our product's* success criteria, but its scores are not
comparable to anything external. The question: should we additionally map onto
established agentic benchmarks — specifically TAU-bench and GAIA — and if so, in
what form? Options evaluated:

- **A)** Product benchmark only, standard benchmarks used as literature anchors.
- **B)** Mini-mapping: 10–15 own tasks inspired by TAU-bench / GAIA task
  structures, executed inside the existing Ephe harness.
- **C)** Full integration with a standard framework (run the official suite).

## 2. What the Established Benchmarks Actually Measure

### 2.1 TAU-bench / τ²-bench / τ³-bench (τ-Bench-Forschungsreihe)

- **What:** Conversational service agents in a **tool–agent–user** triangle. The
  agent receives a domain policy document and domain API tools; a *second LLM
  simulates the human user*. Success requires both goal completion and policy
  compliance.
- **Domains:** retail (~115 tasks) and airline (~50) in τ-bench; τ²-bench adds
  telecom and a **dual-control** model (the simulated user has its own tools);
  τ³-bench adds a banking knowledge domain and a voice modality, plus ~75 task
  fixes.
- **Metrics:** `pass^k` — the fraction of tasks where **all k independent runs**
  succeed (reliability, not one-shot luck). Leaderboard reports pass^1…pass^4
  (τ-bench used up to pass^8 in the paper). Frontier-class agents score <50% at
  pass^1 and <25% at pass^8 on retail — the metric is deliberately brutal.
- **Harness:** Python package (uv-install), no Docker. Requires an agent LLM and
  a user-simulator LLM via a model-router (API keys). Error-identification tooling is
  LLM-based and acknowledged as imprecise.
- **Key sources:** <https://github.com/sierra-research/tau-bench>,
  <https://arxiv.org/abs/2406.12045>, <https://github.com/sierra-research/tau2-bench>

### 2.2 GAIA (offener Multi-Step-Benchmark)

- **What:** 466 real-world questions that are "conceptually simple for humans"
  (human baseline 92% vs. 15% for a plugin-equipped agent) but require multi-step
  reasoning, tool use, browsing, and multimodality (PDFs, images, audio,
  spreadsheets, code execution).
- **Structure:** three levels by annotator solution path — Level 1: ≤1 tool,
  ≤5 steps (146 questions, ~31%); Level 2: 5–10 steps, multiple tools combined
  (245, ~53%); Level 3: arbitrarily long action sequences (75, ~16%).
- **Metrics:** quasi-exact match on a factoid final answer
  (`FINAL ANSWER: ...` convention), type-normalized. No credit for reasoning
  traces. 166-question dev set is public with answers; 300 test questions are
  held out behind the HF leaderboard.
- **Harness:** no prescribed framework and no Docker — you run your own agent
  loop and submit answers. Faithful execution, however, assumes browsing,
  code execution, and broad file-type handling.
- **Key sources:** <https://arxiv.org/abs/2311.12983>,
  <https://huggingface.co/papers/2311.12983>,
  <https://huggingface.co/spaces/gaia-benchmark/leaderboard>

### 2.3 SWE-bench Verified

- **What:** 500 human-verified GitHub issues from real Python repositories.
  The agent must produce a patch; evaluation runs the repo's real test suite
  (FAIL_TO_PASS / PASS_TO_PASS test sets).
- **Harness:** Docker containers per repository for reproducible environments.
  Heavy infrastructure; the unit of work (multi-file patches to large
  established codebases) is not Ephe's product surface.
- **Anchor value:** the gold standard for "code agent actually works", useful as
  a literature reference point, nothing more.
- **Key sources:** <https://www.swebench.com/>, <https://www.swebench.com/SWE-bench/faq/>,
  <https://www.swebench.com/SWE-bench/reference/harness/>

### 2.4 WebArena

- **What:** 812 long-horizon web tasks over **self-hosted replicas** of four
  sites (e-commerce, forum, GitLab, CMS). Evaluation is **functional
  correctness**: per-task validator programs check the *end state* of the
  environment, not the agent's text output.
- **Harness:** Docker-based multi-container environment that you host yourself;
  reproducible but operationally heavy.
- **Anchor value:** the pattern "self-hosted fixture + programmatic end-state
  validator" is exactly right for us; the full Docker zoo is not.
- **Key sources:** <https://webarena.dev/>, <https://github.com/web-arena-x/webarena>

### 2.5 OSWorld

- **What:** 369 open-ended tasks in a real Ubuntu VM across web and desktop
  apps, file I/O, and cross-application workflows. Success via executable
  state checks (file contents, VM state, screenshots). Human baseline ~72%;
  best agents ~42.5%.
- **Harness:** full desktop VM snapshots (VirtualBox-style). The heaviest
  harness of the five; requires a computer-use agent.
- **Key sources:** <https://osworld-v1.xlang.ai/>, <https://arxiv.org/abs/2404.07972>

## 3. Fit Analysis for a Local-First Assistant (53 Tools, Skill Fast-Path, No Docker Zoo)

| Benchmark | Measures | Harness weight | Offline-compatible? | Overlap with product matrix | Verdict |
|---|---|---|---|---|---|
| TAU-bench | Policy compliance + multi-turn tool use + reliability (pass^k) | Low (Python only), but needs a user-simulator LLM | Partially — user sim can be a second local model or a scripted stand-in | High: multi-tool pillar + quality gate ≈ policy/tool discipline | **Structure worth copying** |
| GAIA | Grounded multi-step research, multimodality, exact answers | Low formally; high capability-wise (browsing, code exec, multimodal parsing) | Partially — Ephe browsing/code-exec are opt-in, audio/video parsing missing | Medium: research pillar ≈ GAIA L1/L2 | **Task patterns worth copying** |
| SWE-bench Verified | Real patch integration, test-verified | High (Docker per repo) | No | Low (product is not a SWE agent) | Literature anchor |
| WebArena | Long-horizon web actions, end-state validation | High (multi-container sites) | No | Low-Medium (browser tools are opt-in) | Pattern anchor |
| OSWorld | Desktop OS computer use | Very high (full VM) | No | Low | Literature anchor |

Two structural findings:

1. **Our product benchmark already implements the *evaluation philosophy* of
   these suites** (deterministic artifact verification ≈ WebArena-style
   end-state checks; the 3-reps scoring is a crude pass^3). What it lacks is
   (a) *policy-compliance tasks with a user in the loop* (TAU) and (b)
   *grounded exact-answer research tasks* (GAIA).
2. **Full framework adoption buys comparability we cannot honestly claim.**
   Official TAU-bench scores require their user-simulator setup (typically a
   strong cloud model); GAIA leaderboard submission requires the held-out test
   set and capability stack (audio, code exec) that Ephe deliberately keeps
   opt-in. A "we ran it at home" score would invite apples-to-oranges
   comparisons — the failure mode the product benchmark was created to avoid.

## 4. Decision Matrix

| Criterion | A: Product only | B: Mini-mapping (10–15 tasks) | C: Full framework |
|---|---|---|---|
| Engineering cost | — (already done) | ~3–5 days: task specs + scripted user + scoring script | 1–3 weeks: harness glue, user-sim config, env setup; C.2 (SWE-bench/WebArena/OSWorld) adds Docker infra |
| Run cost per cycle | 36 runs, local | +30 runs (10 tasks × 3), local | τ-bench pass^k: hundreds of LLM conversations incl. user sim |
| Determinism / flake resistance | High (deterministic gates) | High (deterministic assertions, scripted user) | Low-Medium: LLM user sim is noisy; LLM-based error attribution is approximate |
| External comparability | None | None directly, but *task families* are citable anchors ("TAU-style policy suite", "GAIA-style grounded QA") | Illusory for a local 8B-class model; published scores use frontier cloud setups |
| Signal for product decisions | High for artifacts; blind spot: multi-turn policy behavior, groundedness of research | Closes exactly those two blind spots in our own semantics | High fidelity, low actionability per engineering hour |
| Maintenance | Current | Low (own fixtures, own assertions) | High (upstream task/env churn: τ³ rewrites, GAIA contamination fixes) |

**Decision: B**, with A retained as the primary release gate and the literature
anchors from Section 2 documented as design references. C is rejected for the
cost/fidelity reasons above; revisit only if a milestone explicitly requires an
external comparability claim (e.g., a public model card for qwen3.8-flash-next
as used by Ephe).

## 5. If B: The 10 Tasks

All tasks run in the existing harness (tool ledger + `verify_artifact` +
`evaluate_quality`), 3 reps each, scored with a proper `pass^3` (all 3 reps must
pass — mirroring TAU-bench's reliability semantics). Assertions are
deterministic; no LLM judge. Add `EPHE_FINAL_ANSWER:` as the extraction
convention for exact-answer tasks (GAIA's `FINAL ANSWER:` pattern).

### TAU-inspired family (policy + multi-turn + state)

| # | Task | Prompt pattern | Deterministic assertion |
|---|---|---|---|
| T1 | Order modification after policy cutoff | Scripted user asks to change the shipping address of a shipped order; policy forbids it; user pushes back once | Tool ledger contains refusal path (no `modify_order` call on shipped state); final answer acknowledges constraint |
| T2 | Refund outside window → correct alternative | Scripted user requests cash refund on an order older than the policy window | Ledger shows `offer_store_credit` (or policy-correct tool), no direct `refund` call; conversation completes |
| T3 | Constraint-carrying lookup + booking | Find the cheapest qualifying option, then book it with stated constraints (date, budget cap) | Booking tool args match constraints exactly (arg-level assertion); no out-of-budget booking |
| T4 | Mid-dialogue requirement change | Scripted user changes one requirement after the agent started executing | Ledger shows cancellation/redo of the stale step; final artifact matches the *new* requirement |

### GAIA-inspired family (grounded research + exact answer + artifact)

| # | Task | Prompt pattern | Deterministic assertion |
|---|---|---|---|
| G1 | Two-hop file research | Value A inside an attached local PDF + value B in a second file; compute A/B; answer + one-page PDF | Exact `FINAL ANSWER` match (numeric tolerance 0); PDF verified, ≥1 citation marker `[Sxxx-Cxxx]` |
| G2 | Local/remote cross-check | Extract a figure from a fixture page (fetched via web tool) and reconcile against a local CSV | Exact answer match; chart artifact verified with values equal to ground truth |
| G3 | Multi-file aggregation | Aggregate 3 local CSVs into a summary PDF with one table | Every table cell equals the deterministic aggregate; PDF table extractable via pdfplumber |
| G4 | Transformation chain | Sort/filter a dataset, write a brief, state the top-1 item | Exact answer + PDF pages ≥ 2 + no placeholder tokens (existing gate) |

### WebArena/OSWorld-inspired family (end-state, no Docker)

| # | Task | Prompt pattern | Deterministic assertion |
|---|---|---|---|
| W1 | CRUD end-state via local surface | Create, edit, then delete an item through the local PWA/API workflow | End state read from the local store (item absent, audit trail shows all three ops) |
| W2 | Cross-tool file workflow | Rename a file, update an index/manifest that references it, produce a summary | Filesystem end state consistent: manifest path updated, old path gone, summary artifact verified |

**Fixture budget:** T-family needs one in-memory tool sandbox with 3 policies;
G-family needs ~6 fixture files (PDF, CSVs, HTML mirror); W-family uses existing
local state only. No new infrastructure, no Docker, fully offline.

## 6. Harness Deltas Required (Estimate)

1. Scripted user-simulator runner (a queue of user turns with conditional
   pushback), asserted against the existing tool-call ledger/audit trail. ~1–2 d.
2. `pass^3` scorer + run manifest (per task: prompt, policy id, assertions,
   verdict per rep, latency, token counts) written next to the existing eval
   outputs (cf. `evals/skills/*.yaml` conventions). ~0.5 d.
3. `FINAL ANSWER` extraction + type-normalized comparison utility. ~0.5 d.

Total: ~3–5 engineering days; runs stay local and reproducible.

## 7. Sources

- τ-bench — <https://github.com/sierra-research/tau-bench> · paper: <https://arxiv.org/abs/2406.12045>
- τ²-bench — <https://github.com/sierra-research/tau2-bench>
- GAIA — <https://arxiv.org/abs/2311.12983> · HF: <https://huggingface.co/papers/2311.12983> · leaderboard: <https://huggingface.co/spaces/gaia-benchmark/leaderboard>
- SWE-bench — <https://www.swebench.com/> · harness: <https://www.swebench.com/SWE-bench/reference/harness/> · FAQ: <https://www.swebench.com/SWE-bench/faq/>
- WebArena — <https://webarena.dev/> · <https://github.com/web-arena-x/webarena>
- OSWorld — <https://osworld-v1.xlang.ai/> · <https://arxiv.org/abs/2404.07972>
