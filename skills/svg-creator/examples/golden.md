# Golden Example

## Trace 1 (Standard)
1. Input: Erstell mir ein SVG-Logo mit einem Kreis und dem Text "EPHE"
2. ToolCall: {"name": "create_svg", "arguments": {"filename": "out"}}
3. Observation: svg
4. Final: svg (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: Erstell mir ein SVG-Logo mit einem Kreis und dem Text "EPHE" (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_svg", "arguments": {"filename": "out"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: svg.
