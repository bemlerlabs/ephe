# Rubric — Plugin `vision`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Real seeing**: analyze_image/vision_click on real image data — no guessing.
2. **Descriptive, not invented**: only what is visible in the image.
3. **Locatable**: positions/regions with coordinates or clear areas.
4. **File honesty**: a missing image file is reported, not talked around.
5. **Anti-slop**: no invented details ('wahrscheinlich ein Baum').
