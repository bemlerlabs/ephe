# Golden Example

## Trace 1 (Standard)
1. Input: /decision Matrix: A vs B
2. ToolCall: {"name": "create_xlsx", "arguments": {"title": "Beispiel", "data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: Gewicht
4. Final: Gewicht (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /decision Matrix: A vs B (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_xlsx", "arguments": {"title": "Beispiel", "data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Gewicht.
