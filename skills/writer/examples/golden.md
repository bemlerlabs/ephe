# Golden Example

## Trace 1 (Standard)
1. Input: Schreibe eine kurze professionelle E-Mail um ein Meeting vorzuschlagen.
2. ToolCall: {"name": "web_search", "arguments": {"query": "Schreibe eine kurze professionelle E-Mail um ein Meeting vor", "max_results": 5}}
3. Observation: Betreff
4. Final: Betreff (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Schreibe eine kurze professionelle E-Mail um ein Meeting vorzuschlagen. (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "Schreibe eine kurze professionelle E-Mail um ein Meeting vor", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Betreff.
