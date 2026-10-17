# Golden Example

## Trace 1 (Standard)
1. Input: /explain Quantencomputer
2. ToolCall: {"name": "web_search", "arguments": {"query": "/explain Quantencomputer", "max_results": 5}}
3. Observation: Quant
4. Final: Quant (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /explain Quantencomputer (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "web_search", "arguments": {"query": "/explain Quantencomputer", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Quant.
