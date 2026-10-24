# Rubric — Plugin `skill-creator`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Anatomy**: SKILL.md + references/rubric.md + examples/golden.md.
2. **Instruction fidelity**: SKILL.md says WHEN and HOW, with 2+ few-shot examples.
3. **Golden-saturated**: ≥ 6 cases, at least 1 of them an anti-slop trap.
4. **Gradeable**: grade returns a number, not a gut feeling.
5. **Anti-slop**: no empty example files.
