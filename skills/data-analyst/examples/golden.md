# Golden Example

## Trace 1 (Standard)
1. Input: /data Analyze: 10,20,30
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Example", "labels": "A,B"}}
3. Observation: average
4. Final: average (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /data Analyze: 10,20,30 (source/path not found)
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Example", "labels": "A,B"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: average.
