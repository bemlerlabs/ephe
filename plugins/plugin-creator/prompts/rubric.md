# Rubric — Plugin `plugin-creator`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Schema-faithful**: manifest v1.1 with origin/permissions/components — valid against the loader.
2. **Real, not stub**: the named tools exist; the permissions cover them.
3. **Validating**: validateplugin runs and reports findings.
4. **Locatable**: the files live under plugins/<name>/.
5. **Anti-slop**: no 'füge hier deine Logik ein' filler.
