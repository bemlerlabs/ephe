# Golden Example

## Trace 1 (Standard)
1. Input: /competitor coffee trade
2. ToolCall: {"name": "web_search", "arguments": {"query": "/competitor coffee trade", "max_results": 5}}
3. Observation: Strength
4. Final: Strength (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /competitor coffee trade (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/competitor coffee trade", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: Strength.
