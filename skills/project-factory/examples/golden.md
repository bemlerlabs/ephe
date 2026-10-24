# Golden Example

## Trace 1 (Standard)
1. Input: /factory Build a calculator
2. ToolCall: {"name": "scaffold_project", "arguments": {"template": "default"}}
3. Observation: README
4. Final: README (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /factory Build a calculator (source/path not found)
2. ToolCall: {"name": "scaffold_project", "arguments": {"template": "default"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: README.
