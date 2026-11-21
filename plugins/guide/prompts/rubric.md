# Rubric — Plugin `guide`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Stepwise**: numbered steps, each one walkable on its own.
2. **Cause with diagnoses**: first symptom → then cause → then fix.
3. **Locally true**: paths/commands from the real Ephe repo, no invented CLI.
4. **Compact**: 5-10 steps, no sermon.
5. **Anti-slop**: no 'konsultiere die Dokumentation' dead ends without a link/path.
