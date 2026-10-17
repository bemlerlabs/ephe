# Golden Example

## Trace 1 (Standard)
1. Input: Was sind die neuesten Entwicklungen bei Ollama im Jahr 2026?
2. ToolCall: {"name": "web_search", "arguments": {"query": "Was sind die neuesten Entwicklungen bei Ollama im Jahr 2026?", "max_results": 5}}
3. Observation: Ollama
4. Final: Ollama (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Was sind die neuesten Entwicklungen bei Ollama im Jahr 2026? (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "Was sind die neuesten Entwicklungen bei Ollama im Jahr 2026?", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Ollama.
