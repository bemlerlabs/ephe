# Golden Example

## Trace 1 (Standard)
1. Input: /notebook Create a source notebook from ~/Documents/company/strategy.pdf and answer the most important risks
2. ToolCall: {"name": "create_source_notebook", "arguments": {"title": "Example"}}
3. Observation: SOURCE_NOTEBOOK_FILE
4. Final: SOURCE_NOTEBOOK_FILE (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /notebook Create a source notebook from ~/Documents/company/strategy.pdf and answer the most important risks (source/path not found)
2. ToolCall: {"name": "create_source_notebook", "arguments": {"title": "Example"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: SOURCE_NOTEBOOK_FILE.
