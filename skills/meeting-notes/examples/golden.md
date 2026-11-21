# Golden Example

## Trace 1 (Standard, text skill - no tool)
1. Input: /minutes meeting 12.00
2. Final: decision (direct, without a tool call).

Quality checklist (covers the rubric fields):
1. Invent nothing: unclear ownership is marked "open" instead of assigned.
2. Avoid passive minutes - plain, precise language, short sentences.
3. Answer in the user's language. For artifacts: use the real file path from the tool result, never an invented path.
4. Do not simulate: never claim a result or a file the tool did not actually return. Ground every claim in real tool output.
5. Ground every number/path on real tool output; no simulated output without a returned path.
