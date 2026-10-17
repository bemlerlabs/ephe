# Golden Example

## Trace 1 (Standard)
1. Input: /checklist Umzug
2. ToolCall: {"name": "create_pdf", "arguments": {"title": "Beispiel", "content": "# Beispiel\nx = 1", "filename": "out"}}
3. Observation: 1.
4. Final: 1. (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /checklist Umzug (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_pdf", "arguments": {"title": "Beispiel", "content": "# Beispiel\nx = 1", "filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: 1..
