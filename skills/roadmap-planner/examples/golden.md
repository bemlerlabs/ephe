# Golden Example

## Trace 1 (Standard)
1. Input: /roadmap Q1 bis Q4
2. ToolCall: {"name": "create_diagram", "arguments": {"kind": "flow", "title": "Beispiel", "items": "Start;Ende"}}
3. Observation: Meilenstein
4. Final: Meilenstein (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /roadmap Q1 bis Q4 (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_diagram", "arguments": {"kind": "flow", "title": "Beispiel", "items": "Start;Ende"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Meilenstein.
