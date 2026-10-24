# Rubric — Plugin `presentations`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Real deck**: create_pptx_deck delivers a .pptx — not a slide sketch in the chat.
2. **Dramaturgy**: title → core message → evidence → close.
3. **One idea per slide**, no wall of text.
4. **QA**: qa_pptx_deck is used, or the slide count is checked.
5. **Anti-slop**: no 'Slide X' placeholders without content.
