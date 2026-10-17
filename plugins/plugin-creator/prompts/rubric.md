# Rubric — Plugin `plugin-creator`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run plugin-creator`).

Criteria:
1. **Schema-faithful**: manifest v1.1 with origin/permissions/components — valid against the loader.
2. **Real, not stub**: the named tools exist; the permissions cover them.
3. **Validating**: validateplugin runs and reports findings.
4. **Locatable**: the files live under plugins/<name>/.
5. **Anti-slop**: no 'füge hier deine Logik ein' filler.
