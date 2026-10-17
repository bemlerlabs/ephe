# Golden Example

## Trace 1 (Standard)
1. Input: Erstell einen QR-Code für https://ephe.dev
2. ToolCall: {"name": "create_qrcode", "arguments": {"data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Erstell einen QR-Code für https://ephe.dev (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_qrcode", "arguments": {"data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
