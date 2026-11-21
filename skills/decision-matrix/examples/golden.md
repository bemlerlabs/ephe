# Golden Example

## Trace 1 (Standard)
1. Input: /decision matrix: A vs B
2. ToolCall: {"name": "create_xlsx", "arguments": {"title": "Example", "data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: weight
4. Final: weight (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /decision matrix: A vs B (source/path not found)
2. ToolCall: {"name": "create_xlsx", "arguments": {"title": "Example", "data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: weight.
