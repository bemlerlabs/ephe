# Golden Example

## Trace 1 (Standard)
1. Input: Nimm die Demo-Clips auf
2. ToolCall: {"name": "create_video", "arguments": {}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Nimm die Demo-Clips auf (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_video", "arguments": {}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
