# Rubric — Plugin `memory`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run memory`).

Criteria:
1. **Really stored**: the memory tool is called, not 'notiert' and merely claimed.
2. **Retrievable**: stored facts reappear in later answers.
3. **Discriminating**: meaning, source and date are captured.
4. **Forgettable**: the user can delete entries; the way to do it is shown.
5. **Anti-slop**: no 'ich habe mir das gemerkt' without a tool call.
