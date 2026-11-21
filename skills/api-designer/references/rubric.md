# Quality Rubric

1. Consistency first: check the project's existing conventions (read_file on similar routes) and follow them (names, error format, response models).
2. Resource-oriented URLs, correct methods, clear status codes (400 vs 404 vs 409 vs 422).
3. Error semantics: one uniform error envelope with a machine-readable code and a human-readable message.
4. Security by default: validate every input (Pydantic/Zod), no PII in logs, name the auth concept.
5. Output: endpoint table (method, path, request, response, errors) plus a short rationale for the decisions.
6. Ground every number/path on real tool output; no simulated output without a returned path.
