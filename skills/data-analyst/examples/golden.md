# Golden Example

## Trace 1 (Standard)
1. Input: /data Analysiere: 10,20,30
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Beispiel", "labels": "A,B"}}
3. Observation: Durchschnitt
4. Final: Durchschnitt (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /data Analysiere: 10,20,30 (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Beispiel", "labels": "A,B"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Durchschnitt.
