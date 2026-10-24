# Golden Example

## Trace 1 (Standard)
1. Input: Create an SVG logo with a circle and the text "EPHE"
2. ToolCall: {"name": "create_svg", "arguments": {"filename": "out"}}
3. Observation: svg
4. Final: svg (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Create an SVG logo with a circle and the text "EPHE" (source/path not found)
2. ToolCall: {"name": "create_svg", "arguments": {"filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: svg.
