# Golden Example

## Trace 1 (Standard)
1. Input: What is on my Desktop?
2. ToolCall: {"name": "list_directory", "arguments": {"path": "tests/test_example.py"}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: What is on my Desktop? (source/path not found)
2. ToolCall: {"name": "list_directory", "arguments": {"path": "tests/test_example.py"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
