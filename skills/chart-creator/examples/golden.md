# Golden Example

## Trace 1 (Standard)
1. Input: Show me a chart: January 100, February 150, March 120, April 200
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Example", "labels": "A,B"}}
3. Observation: Chart
4. Final: Chart (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Show me a chart: January 100, February 150, March 120, April 200 (source/path not found)
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Example", "labels": "A,B"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: Chart.
