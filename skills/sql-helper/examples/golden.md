# Golden Example

## Trace 1 (Standard)
1. Input: /sql select all users
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: SELECT
4. Final: SELECT (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /sql select all users (source/path not found)
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: SELECT.
