# Rubric — Plugin `image-studio`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Real file**: the SVG/video/image lands as an artifact; a description alone does not count.
2. **Style fidelity**: named styles (flat, isometric, sketch) shape the result.
3. **Dimensions**: the user's size specs are carried over.
4. **Tool honesty**: raster-image generation without an engine → an honest hint, vectors still work.
5. **Anti-slop**: no 'ich stelle mir das Ergebnis so vor' daydreaming.
