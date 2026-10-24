# Golden Example

## Trace 1 (Standard)
1. Input: /translate Hello into German
2. ToolCall: {"name": "web_search", "arguments": {"query": "/translate Hello into German", "max_results": 5}}
3. Observation: Hallo
4. Final: Hallo (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /translate Hello into German (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/translate Hello into German", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: Hallo.
