# Golden Example

## Trace 1 (Standard)
1. Input: /scan ~/Desktop/test.png
2. ToolCall: {"name": "analyze_image", "arguments": {"path": "tests/test_example.py", "question": "Was ist darauf?", "region": [0, 0, 100, 100]}}
3. Observation: Bild
4. Final: Bild (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /scan ~/Desktop/test.png (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "analyze_image", "arguments": {"path": "tests/test_example.py", "question": "Was ist darauf?", "region": [0, 0, 100, 100]}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Bild.
