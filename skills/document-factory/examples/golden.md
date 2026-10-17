# Golden Example

## Trace 1 (Standard)
1. Input: /doc-factory Briefing Solar
2. ToolCall: {"name": "build_document", "arguments": {"topic": "KI 2026", "filename": "out"}}
3. Observation: FILE
4. Final: FILE (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /doc-factory Briefing Solar (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "build_document", "arguments": {"topic": "KI 2026", "filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: FILE.
