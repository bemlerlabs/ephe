# Rubric — Plugin `mcp-connector`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run mcp-connector`).

Criteria:
1. **Configured, not dreamed**: only servers from mcp.json are contacted.
2. **Diagnosis before ejection**: health and tool list are shown when something hiccups.
3. **Descriptive**: tool_describe/tool_search are used for orientation.
4. **No secret leak**: quote URLs without query parameters.
5. **Anti-slop**: no 'ich verbinde mich einfach mal mit…' (a server that does not exist).
