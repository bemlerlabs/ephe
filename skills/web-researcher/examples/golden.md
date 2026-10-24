# Golden Example

## Trace 1 (Standard)
1. Input: What are the latest developments at Ollama in 2026?
2. ToolCall: {"name": "web_search", "arguments": {"query": "What are the latest developments at Ollama in 2026?", "max_results": 5}}
3. Observation: Ollama
4. Final: Ollama (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: What are the latest developments at Ollama in 2026? (source/path not found)
2. ToolCall: {"name": "web_search", "arguments": {"query": "What are the latest developments at Ollama in 2026?", "max_results": 5}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: Ollama.
