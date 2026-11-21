# Golden Example

## Trace 1 (Standard)
1. Input: Create a flowchart for the onboarding process
2. ToolCall: {"name": "create_diagram", "arguments": {"kind": "flow", "title": "Example", "items": "Start;End"}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Create a flowchart for the onboarding process (source/path not found)
2. ToolCall: {"name": "create_diagram", "arguments": {"kind": "flow", "title": "Example", "items": "Start;End"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
