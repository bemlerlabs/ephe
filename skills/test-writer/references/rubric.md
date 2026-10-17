# Quality Rubric

1. Lies den Zielcode IMMER zuerst (read_file/file_search), bevor du Tests schreibst.
2. Struktur strikt: Given (Zustand/Inputs) / When (Aktion) / Then (beobachtbares Ergebnis) — im Testnamen oder Kommentar.
3. Teste Verhalten, nicht Implementierung: Grenzfälle, Fehlerpfade, Randwerte — nicht nur den Happy Path.
4. Ein Test = eine Aussage. Keine Test-Logik (if/loops) im Test selbst.
5. Nach dem Schreiben den engsten Testlauf ausführen (run_shell) und das Ergebnis ehrlich berichten — grün ODER rot mit Analyse.
6. Ground every number/path on real tool output; no simulated output without a returned path.
