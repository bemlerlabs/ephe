# Rubric — Plugin `web-research`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run web-research`).

Criteria:
1. **Real search**: web_search/fetch_url with genuine hits — no hallucinated content.
2. **Sources mandatory**: every claim carries a URL.
3. **Density**: 3-5 solid facts instead of 10 side sentences.
4. **Artifact on request**: source notebook/Markdown when asked.
5. **Anti-slop**: no invented studies, no 'man sagt' hearsay.
