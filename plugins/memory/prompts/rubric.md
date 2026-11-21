# Rubric — Plugin `memory`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Really stored**: the memory tool is called, not just claimed as noted.
2. **Retrievable**: stored facts reappear in later answers.
3. **Discriminating**: meaning, source and date are captured.
4. **Forgettable**: the user can delete entries; the way to do it is shown.
5. **Anti-slop**: no 'ich habe mir das gemerkt' without a tool call.
