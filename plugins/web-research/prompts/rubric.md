# Rubric — Plugin `web-research`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Real search**: web_search/fetch_url with genuine hits — no hallucinated content.
2. **Sources mandatory**: every claim carries a URL.
3. **Density**: 3-5 solid facts instead of 10 side sentences.
4. **Artifact on request**: source notebook/Markdown when asked.
5. **Anti-slop**: no invented studies, no 'they say' hearsay.
