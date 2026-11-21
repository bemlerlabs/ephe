# Golden Example

## Trace 1 (Standard)
1. Input: /project find my ephe project and analyze the current state
2. ToolCall: {"name": "discover_projects", "arguments": {"query": "/project find my ephe project and analyze the current state", "max_results": 5}}
3. Observation: current state
4. Final: current state (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /project find my ephe project and analyze the current state (source/path not found)
2. ToolCall: {"name": "discover_projects", "arguments": {"query": "/project find my ephe project and analyze the current state", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: current state.
