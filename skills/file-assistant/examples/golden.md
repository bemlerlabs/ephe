# Golden Example

## Trace 1 (Standard)
1. Input: Was ist auf meinem Desktop?
2. ToolCall: {"name": "list_directory", "arguments": {"path": "tests/test_example.py"}}
3. Observation: ok
4. Final: ok (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Was ist auf meinem Desktop? (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "list_directory", "arguments": {"path": "tests/test_example.py"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: ok.
