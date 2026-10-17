# Golden Example

## Trace 1 (Standard)
1. Input: /notebook Erstelle aus ~/Documents/company/strategy.pdf ein Quellen-Notebook und beantworte die wichtigsten Risiken
2. ToolCall: {"name": "create_source_notebook", "arguments": {"title": "Beispiel"}}
3. Observation: SOURCE_NOTEBOOK_FILE
4. Final: SOURCE_NOTEBOOK_FILE (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /notebook Erstelle aus ~/Documents/company/strategy.pdf ein Quellen-Notebook und beantworte die wichtigsten Risiken (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_source_notebook", "arguments": {"title": "Beispiel"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: SOURCE_NOTEBOOK_FILE.
