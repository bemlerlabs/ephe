# Golden Example

## Trace 1 (Standard)
1. Input: Erstell ein Flowchart für den Onboarding-Prozess
2. ToolCall: {"name": "create_diagram", "arguments": {"kind": "flow", "title": "Beispiel", "items": "Start;Ende"}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Erstell ein Flowchart für den Onboarding-Prozess (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_diagram", "arguments": {"kind": "flow", "title": "Beispiel", "items": "Start;Ende"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
