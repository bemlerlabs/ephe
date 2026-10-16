# Golden Example

## Trace 1 (Standard)
1. Input: /project finde mein ephe Projekt und analysiere den Ist-Zustand
2. ToolCall: {"name": "discover_projects", "arguments": {"query": "/project finde mein ephe Projekt und analysiere den Ist-Zust", "max_results": 5}}
3. Observation: Ist-Zustand
4. Final: Ist-Zustand (belegt durch Tool-Output).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /project finde mein ephe Projekt und analysiere den Ist-Zustand (Quelle/Pfad nicht gefunden)
2. ToolCall: {"name": "discover_projects", "arguments": {"query": "/project finde mein ephe Projekt und analysiere den Ist-Zust", "max_results": 5}}
3. Observation: [tool-error] Eintrag nicht gefunden
4. Final: Fehler ehrlich melden; naechster Schritt: Ist-Zustand.
