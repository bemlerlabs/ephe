# Golden Example

## Trace 1 (Standard)
1. Input: /review – hier ist eine einfache Python-Funktion: def add(a, b): return a + b
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: Zusammenfassung
4. Final: Zusammenfassung (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /review – hier ist eine einfache Python-Funktion: def add(a, b): return a + b (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "read_file", "arguments": {"path": "tests/test_example.py", "offset": 1, "limit": 50}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Zusammenfassung.
