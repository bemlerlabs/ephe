# Golden Example

## Trace 1 (Standard)
1. Input: /test write tests for add
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: def test
4. Final: def test (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /test write tests for add (source/path not found)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: def test.
