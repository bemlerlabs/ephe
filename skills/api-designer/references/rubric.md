# Quality Rubric

1. Konsistenz zuerst: Existing conventions des Projekts prüfen (read_file auf ähnliche Routes) und ihnen folgen (Namen, Fehlerformat, Response-Modelle).
2. Ressourcen-orientierte URLs, korrekte Methoden, klare Statuscodes (400 vs 404 vs 409 vs 422).
3. Fehlersemantik: Ein einheitliches Fehler-Envelope mit maschinenlesbarem Code + menschenlesbarer Message.
4. Security by default: Validierung aller Inputs (Pydantic/Zod), keine PII in Logs, Auth-Konzept benennen.
5. Ausgabe: Endpoint-Tabelle (Methode, Pfad, Request, Response, Fehler) + kurze Begründung der Entscheidungen.
6. Ground every number/path on real tool output; no simulated output without a returned path.
