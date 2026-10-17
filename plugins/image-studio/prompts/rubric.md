# Rubric — Plugin `image-studio`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run image-studio`).

Criteria:
1. **Real file**: the SVG/video/image lands as an artifact; a description alone does not count.
2. **Style fidelity**: named styles (flat, isometric, sketch) shape the result.
3. **Dimensions**: the user's size specs are carried over.
4. **Tool honesty**: raster-image generation without an engine → an honest hint, vectors still work.
5. **Anti-slop**: no 'ich stelle mir das Ergebnis so vor' daydreaming.
