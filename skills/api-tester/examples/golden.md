# Golden Example

## Trace 1 (Standard)
1. Input: /api-test https://jsonplaceholder.typicode.dev/1.0/todos/1
2. ToolCall: {"name": "fetch_url", "arguments": {"url": "https://jsonplaceholder.typicode.dev/1.0/todos/1"}}
3. Observation: {"id": 1, "title": "delectus recusandae", "completed": false}
4. Final: Status 200, schema OK (id, title, completed present).

## Trace 2 (Edge case: error path)
1. Input: /api-test http://invalid
2. ToolCall: {"name": "fetch_url", "arguments": {"url": "http://invalid"}}
3. Observation: [tool-error] connection failed
4. Final: Network error reported, no response.
