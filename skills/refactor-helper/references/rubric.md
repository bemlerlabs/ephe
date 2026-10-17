# Quality Rubric

1. Vorher: Zielcode und seine Aufrufer lesen (file_search/read_file). Niemals blind ändern.
2. Refactoring in kleinen, benennbaren Schritten: Extract Function, Rename, Move, Inline — jeder Schritt erklärbar.
3. Jede Änderung begründen: Welcher Code-Smell, welche Verbesserung (Lesbarkeit, Duplikation, Kopplung, Testbarkeit).
4. Wenn Tests existieren: nach jedem Schritt laufen lassen. Wenn keine existieren: zuerst minimale Absicherungstests vorschlagen.
5. Kein Feature-Creep: Refactoring fügt KEINE neuen Features hinzu.
6. Ground every number/path on real tool output; no simulated output without a returned path.
