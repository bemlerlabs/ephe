# Golden Example

## Trace 1 (Standard)
1. Input: /summary fasse den Text zusammen
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: zusammen
4. Final: zusammen (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /summary fasse den Text zusammen (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: zusammen.
