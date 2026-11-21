# Rubric — Plugin `voice`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Real audio**: TTS delivers a playable file (.wav/.mp3), not 'vorgestellt'.
2. **Voice choice**: the requested voice/language is honoured (local piper, otherwise an honest cloud hint).
3. **Transcript fidelity**: STT gives back what was said — no smoothing.
4. **Honest failure**: a missing voice/model is reported with a setup hint.
5. **Anti-slop**: no 'hier wäre die Audio-Datei'.
