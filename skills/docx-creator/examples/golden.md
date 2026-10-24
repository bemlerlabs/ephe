# Golden Example

## Trace 1 (Standard)
1. Input: Create a Word document about Project Phoenix
2. ToolCall: {"name": "create_docx", "arguments": {"title": "Example", "content": "# Example\nx = 1", "filename": "out"}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Create a Word document about Project Phoenix (source/path not found)
2. ToolCall: {"name": "create_docx", "arguments": {"title": "Example", "content": "# Example\nx = 1", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
