# Rubric — Plugin `mcp-connector`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Configured, not dreamed**: only servers from mcp.json are contacted.
2. **Diagnosis before ejection**: health and tool list are shown when something hiccups.
3. **Descriptive**: tool_describe/tool_search are used for orientation.
4. **No secret leak**: quote URLs without query parameters.
5. **Anti-slop**: no 'ich verbinde mich einfach mal mit…' (a server that does not exist).
