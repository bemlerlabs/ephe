# Golden Example

## Trace 1 (Standard)
1. Input: /businessplan for a coffee trade
2. ToolCall: {"name": "web_search", "arguments": {"query": "/businessplan for a coffee trade", "max_results": 5}}
3. Observation: USP
4. Final: USP (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /businessplan for a coffee trade (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/businessplan for a coffee trade", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: USP.
