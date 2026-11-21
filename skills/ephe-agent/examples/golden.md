# Golden Example

## Trace 1 (Standard)
1. Input: /ephe build a small python cli that converts csv to json
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: plan
4. Final: plan (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /ephe build a small python cli that converts csv to json (source/path not found)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: plan.
