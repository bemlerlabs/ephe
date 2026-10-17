# Golden Example

## Trace 1 (Standard)
1. Input: /regex fuer E-Mail-Validierung
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: @
4. Final: @ (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /regex fuer E-Mail-Validierung (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: @.
