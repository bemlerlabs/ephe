# Golden Example

## Trace 1 (Standard)
1. Input: /sql Select alle Nutzer
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: SELECT
4. Final: SELECT (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /sql Select alle Nutzer (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: SELECT.
