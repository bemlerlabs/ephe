# Golden Example

## Trace 1 (Standard)
1. Input: Erstell ein Word-Dokument zum Projekt Phoenix
2. ToolCall: {"name": "create_docx", "arguments": {"title": "Beispiel", "content": "# Beispiel\nx = 1", "filename": "out"}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Erstell ein Word-Dokument zum Projekt Phoenix (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_docx", "arguments": {"title": "Beispiel", "content": "# Beispiel\nx = 1", "filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
