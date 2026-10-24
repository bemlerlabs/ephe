# Golden Example

## Trace 1 (Standard)
1. Input: /deck Create a pitch deck for Ephe for investors
2. ToolCall: {"name": "create_pptx_deck", "arguments": {"topic": "AI 2026", "audience": "technical", "thesis": "AI grows"}}
3. Observation: PPTX_DECK_FILE
4. Final: PPTX_DECK_FILE (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /deck Create a pitch deck for Ephe for investors (source/path not found)
2. ToolCall: {"name": "create_pptx_deck", "arguments": {"topic": "AI 2026", "audience": "technical", "thesis": "AI grows"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: PPTX_DECK_FILE.
