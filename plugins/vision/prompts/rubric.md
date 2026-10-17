# Rubric — Plugin `vision`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run vision`).

Criteria:
1. **Real seeing**: analyze_image/vision_click on real image data — no guessing.
2. **Descriptive, not invented**: only what is visible in the image.
3. **Locatable**: positions/regions with coordinates or clear areas.
4. **File honesty**: a missing image file is reported, not talked around.
5. **Anti-slop**: no invented details ('wahrscheinlich ein Baum').
