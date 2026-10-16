# Golden Example

## Trace 1 (Standard)
1. Input: /translate Hello auf Deutsch
2. ToolCall: {"name": "web_search", "arguments": {"query": "/translate Hello auf Deutsch", "max_results": 5}}
3. Observation: Hallo
4. Final: Hallo (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /translate Hello auf Deutsch (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/translate Hello auf Deutsch", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Hallo.
