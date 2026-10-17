# Golden Example

## Trace 1 (Standard)
1. Input: /security-review prüfe core/tools/file_ops.py
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: Scope
4. Final: Scope (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /security-review prüfe core/tools/file_ops.py (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Scope.
