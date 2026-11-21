# Quality Rubric

1. Explicit JOINs (no implicit comma joins), meaningful aliases, no SELECT * in production suggestions.
2. Injection safety: always show parameterized queries in application code - never string concatenation.
3. Performance: point out indexes that would serve the WHERE/JOIN/ORDER-BY clauses; mention EXPLAIN for large tables.
4. Name the dialect (PostgreSQL vs SQLite vs MySQL) when syntax differs.
5. For real project databases: test the query via run_shell when a test DB is available and show the result.
6. Ground every number/path on real tool output; no simulated output without a returned path.
