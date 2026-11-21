# Golden Example

## Trace 1 (Standard)
1. Input: Write a short professional email to propose a meeting.
2. ToolCall: {"name": "web_search", "arguments": {"query": "Write a short professional email to propose a meeting", "max_results": 5}}
3. Observation: subject
4. Final: subject (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Write a short professional email to propose a meeting. (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "Write a short professional email to propose a meeting", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: subject.
