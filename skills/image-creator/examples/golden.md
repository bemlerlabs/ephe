# Golden Example

## Trace 1 (Standard)
1. Input: Erstelle ein Bild von einem Fuchs im Schwarzwald
2. ToolCall: {"name": "generate_image", "arguments": {"prompt": "Fasse zusammen", "filename": "out"}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Erstelle ein Bild von einem Fuchs im Schwarzwald (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "generate_image", "arguments": {"prompt": "Fasse zusammen", "filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
