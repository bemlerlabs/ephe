# Golden Example

## Trace 1 (Standard)
1. Input: /businessplan fuer einen Kaffeehandel
2. ToolCall: {"name": "web_search", "arguments": {"query": "/businessplan fuer einen Kaffeehandel", "max_results": 5}}
3. Observation: USP
4. Final: USP (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /businessplan fuer einen Kaffeehandel (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/businessplan fuer einen Kaffeehandel", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: USP.
