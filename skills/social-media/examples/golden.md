# Golden Example

## Trace 1 (Standard)
1. Input: /social LinkedIn Post ueber KI
2. ToolCall: {"name": "web_search", "arguments": {"query": "/social LinkedIn Post ueber KI", "max_results": 5}}
3. Observation: Hook
4. Final: Hook (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /social LinkedIn Post ueber KI (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/social LinkedIn Post ueber KI", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Hook.
