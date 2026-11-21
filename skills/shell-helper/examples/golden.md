# Golden Example

## Trace 1 (Standard)
1. Input: How much disk space do I have left?
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: How much disk space do I have left? (source/path not found)
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
