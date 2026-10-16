# Rubric — Plugin `presentations`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run presentations`).

Criteria:
1. **Real deck**: create_pptx_deck delivers a .pptx — not a slide sketch in the chat.
2. **Dramaturgy**: title → core message → evidence → close.
3. **One idea per slide**, no wall of text.
4. **QA**: qa_pptx_deck is used, or the slide count is checked.
5. **Anti-slop**: no 'Folie X' placeholders without content.
