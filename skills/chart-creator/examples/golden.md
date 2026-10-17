# Golden Example

## Trace 1 (Standard)
1. Input: Zeig mir einen Chart: Januar 100, Februar 150, März 120, April 200
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Beispiel", "labels": "A,B"}}
3. Observation: Chart
4. Final: Chart (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Zeig mir einen Chart: Januar 100, Februar 150, März 120, April 200 (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "generate_chart", "arguments": {"chart_type": "bar", "title": "Beispiel", "labels": "A,B"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Chart.
