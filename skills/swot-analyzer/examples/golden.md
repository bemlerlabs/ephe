# Golden Example

## Trace 1 (Standard)
1. Input: /swot fuer Startup
2. ToolCall: {"name": "web_search", "arguments": {"query": "/swot fuer Startup", "max_results": 5}}
3. Observation: St
4. Final: St (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /swot fuer Startup (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/swot fuer Startup", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: St.
