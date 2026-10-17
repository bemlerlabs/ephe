# Rubric — Plugin `voice`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run voice`).

Criteria:
1. **Real audio**: TTS delivers a playable file (.wav/.mp3), not 'vorgestellt'.
2. **Voice choice**: the requested voice/language is honoured (local piper, otherwise an honest cloud hint).
3. **Transcript fidelity**: STT gives back what was said — no smoothing.
4. **Honest failure**: a missing voice/model is reported with a setup hint.
5. **Anti-slop**: no 'hier wäre die Audio-Datei'.
