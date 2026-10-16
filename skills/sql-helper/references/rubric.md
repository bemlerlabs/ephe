# Quality Rubric

1. Explizite JOINs (keine impliziten Komma-Joins), sprechende Aliase, keine SELECT * in Produktionsvorschlägen.
2. Injektionssicherheit: Immer parametrisierte Queries im Anwendungscode zeigen — String-Konkatenation niemals.
3. Performance: Auf Indizes hinweisen, die die WHERE/JOIN/ORDER-BY-Klauseln nutzen würden; bei großen Tabellen EXPLAIN erwähnen.
4. Dialekt angeben (PostgreSQL vs SQLite vs MySQL), wenn Syntax abweicht.
5. Bei echten Datenbanken im Projekt: Query über run_shell testen, wenn eine Test-DB verfügbar ist, und das Ergebnis zeigen.
6. Ground every number/path on real tool output; no simulated output without a returned path.
