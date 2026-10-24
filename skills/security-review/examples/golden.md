# Golden Example

## Trace 1 (Standard)
1. Input: /security-review check core/tools/file_ops.py
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: Scope
4. Final: Scope (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /security-review check core/tools/file_ops.py (source/path not found)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: Scope.
