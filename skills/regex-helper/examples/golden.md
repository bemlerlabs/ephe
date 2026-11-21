# Golden Example

## Trace 1 (Standard)
1. Input: /regex for email validation
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: @
4. Final: @ (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /regex for email validation (source/path not found)
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: @.
