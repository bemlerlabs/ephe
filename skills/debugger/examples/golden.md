# Golden Example

## Trace 1 (Standard)
1. Input: Find the error in this stack trace
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Find the error in this stack trace (source/path not found)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
