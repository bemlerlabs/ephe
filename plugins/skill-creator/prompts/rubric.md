# Rubric — Plugin `skill-creator`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run skill-creator`).

Criteria:
1. **Anatomy**: SKILL.md + references/rubric.md + examples/golden.md.
2. **Instruction fidelity**: SKILL.md says WHEN and HOW, with 2+ few-shot examples.
3. **Golden-saturated**: ≥ 6 cases, at least 1 of them an anti-slop trap.
4. **Gradeable**: grade returns a number, not a gut feeling.
5. **Anti-slop**: no empty example files.
