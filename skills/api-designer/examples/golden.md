# Golden Example

## Trace 1 (Standard)
1. Input: /api Design a REST API for notes
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: endpoint
4. Final: endpoint (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /api Design a REST API for notes (source/path not found)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: endpoint.
