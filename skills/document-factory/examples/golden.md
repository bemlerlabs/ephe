# Golden Example

## Trace 1 (Standard)
1. Input: /doc-factory Solar briefing
2. ToolCall: {"name": "build_document", "arguments": {"topic": "AI 2026", "filename": "out"}}
3. Observation: FILE
4. Final: FILE (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /doc-factory Solar briefing (source/path not found)
2. ToolCall: {"name": "build_document", "arguments": {"topic": "AI 2026", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: FILE.
