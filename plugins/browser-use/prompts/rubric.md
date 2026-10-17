# Rubric — Plugin `browser-use`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run browser-use`).

Criteria:
1. **Real navigation**: browser_go/browser_click — no claiming page contents.
2. **Proof**: a screenshot or a quoted page for visual questions.
3. **Stepwise**: every action is named before it happens.
4. **Safe**: no form submits without confirmation.
5. **Anti-slop**: no 'die Seite zeigt wahrscheinlich' guessing.
