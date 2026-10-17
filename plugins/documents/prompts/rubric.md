# Rubric — Plugin `documents`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run documents`).

Criteria:
1. **Real artifact**: create_pdf/create_docx delivers an openable file — no text that merely describes a file.
2. **Structure**: title, outline, key figures — a document, not prose.
3. **Sources**: stated provenance of numbers/quotes; nothing invented.
4. **Right size**: the user can hand the file on directly.
5. **Anti-slop**: no placeholders, no TODOs, no "Beispiel Corp".
