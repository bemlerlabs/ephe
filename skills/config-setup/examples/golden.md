# Golden Example

## Trace 1 (Standard)
1. Input: /setup
2. ToolCall: {"name": "read_file", "arguments": {"path": "~/.ephe/engine.json"}}
3. Observation: {"provider": "ollama", "model": "gemma4:12b"}
4. Final: Active engine: ollama/gemma4:12b. No change needed.

## Trace 2 (Edge case: error path)
1. Input: /setup (new environment, no engine.json)
2. ToolCall: {"name": "read_file", "arguments": {"path": "~/.ephe/engine.json"}}
3. Observation: [tool-error] file not found
4. Final: No engine configured. Choose one via `ephe configure`.
