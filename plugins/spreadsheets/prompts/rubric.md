# Rubric — Plugin `spreadsheets`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run spreadsheets`).

Criteria:
1. **Real workbook**: create_xlsx delivers an .xlsx, not a CSV description.
2. **Formulas over hard values**: sums/averages as formulas.
3. **Readable structure**: header row, unit columns, no number salad.
4. **Key figures**: the asked-for number sits visibly in a cell/row.
5. **Anti-slop**: no placeholder rows, no TODO columns.
