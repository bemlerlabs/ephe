# Golden Example

## Trace 1 (Standard)
1. Input: /deck Erstelle ein Pitchdeck fuer Ephe fuer Investoren
2. ToolCall: {"name": "create_pptx_deck", "arguments": {"topic": "KI 2026", "audience": "Technik", "thesis": "KI wachst"}}
3. Observation: PPTX_DECK_FILE
4. Final: PPTX_DECK_FILE (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /deck Erstelle ein Pitchdeck fuer Ephe fuer Investoren (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "create_pptx_deck", "arguments": {"topic": "KI 2026", "audience": "Technik", "thesis": "KI wachst"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: PPTX_DECK_FILE.
