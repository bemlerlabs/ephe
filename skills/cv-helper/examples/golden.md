# Golden Example

## Trace 1 (Standard)
1. Input: /cv optimize my resume
2. ToolCall: {"name": "create_pdf", "arguments": {"title": "Example", "content": "# Example\nx = 1", "filename": "out"}}
3. Observation: experience
4. Final: experience (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /cv optimize my resume (source/path not found)
2. ToolCall: {"name": "create_pdf", "arguments": {"title": "Example", "content": "# Example\nx = 1", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: experience.
