# Golden Example

## Trace 1 (Standard)
1. Input: /factory Baue einen Taschenrechner
2. ToolCall: {"name": "scaffold_project", "arguments": {"template": "default"}}
3. Observation: README
4. Final: README (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /factory Baue einen Taschenrechner (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "scaffold_project", "arguments": {"template": "default"}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: README.
