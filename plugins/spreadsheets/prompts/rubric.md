# Rubric — Plugin `spreadsheets`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Real workbook**: create_xlsx delivers an .xlsx, not a CSV description.
2. **Formulas over hard values**: sums/averages as formulas.
3. **Readable structure**: header row, unit columns, no number salad.
4. **Key figures**: the asked-for number sits visibly in a cell/row.
5. **Anti-slop**: no placeholder rows, no TODO columns.
