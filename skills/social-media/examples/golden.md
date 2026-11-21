# Golden Example

## Trace 1 (Standard)
1. Input: /social LinkedIn post about AI
2. ToolCall: {"name": "web_search", "arguments": {"query": "/social LinkedIn post about AI", "max_results": 5}}
3. Observation: Hook
4. Final: Hook (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /social LinkedIn post about AI (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/social LinkedIn post about AI", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: Hook.
