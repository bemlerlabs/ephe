# Rubric — Plugin `guide`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run guide`).

Criteria:
1. **Stepwise**: numbered steps, each one walkable on its own.
2. **Cause with diagnoses**: first symptom → then cause → then fix.
3. **Locally true**: paths/commands from the real Ephe repo, no invented CLI.
4. **Compact**: 5-10 steps, no sermon.
5. **Anti-slop**: no 'konsultiere die Dokumentation' dead ends without a link/path.
