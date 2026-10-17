# Golden Example

## Trace 1 (Standard)
1. Input: Wie viel Speicherplatz habe ich noch auf meiner Festplatte?
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Wie viel Speicherplatz habe ich noch auf meiner Festplatte? (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "run_shell", "arguments": {"command": "pytest -q", "cwd": "."}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
