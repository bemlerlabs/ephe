# Golden Example

## Trace 1 (Standard)
1. Input: /explain quantum computer
2. ToolCall: {"name": "web_search", "arguments": {"query": "/explain quantum computer", "max_results": 5}}
3. Observation: quantum
4. Final: quantum (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /explain quantum computer (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/explain quantum computer", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: quantum.
