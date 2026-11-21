# Golden Example

## Trace 1 (Standard)
1. Input: Record the demo clips
2. ToolCall: {"name": "create_video", "arguments": {}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Record the demo clips (source/path not found)
2. ToolCall: {"name": "create_video", "arguments": {}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
