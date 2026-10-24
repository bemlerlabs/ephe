# Golden Example

## Trace 1 (Standard)
1. Input: /coverletter as a developer
2. ToolCall: {"name": "create_pdf", "arguments": {"title": "Example", "content": "# Example\nx = 1", "filename": "out"}}
3. Observation: application
4. Final: application (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /coverletter as a developer (source/path not found)
2. ToolCall: {"name": "create_pdf", "arguments": {"title": "Example", "content": "# Example\nx = 1", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: application.
