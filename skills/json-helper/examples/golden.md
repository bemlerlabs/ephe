# Golden Example

## Trace 1 (Standard)
1. Input: /json pretty-print data.json
2. ToolCall: {"name": "read_file", "arguments": {"path": "data.json"}}
3. Observation: {"id": 1, "name": "Test"}
4. Final: JSON pretty-printed (2 spaces indent, 3 keys).

## Trace 2 (Edge case: error path)
1. Input: /json nonexist.json
2. ToolCall: {"name": "read_file", "arguments": {"path": "nonexist.json"}}
3. Observation: [tool-error] file not found
4. Final: Error reported, no JSON output.
