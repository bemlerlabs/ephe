# Quality Rubric

1. Injection: SQL, shell (subprocess with shell=True / f-string commands), path traversal (missing whitelist checks)
2. Secrets/tokens in code, logs, error messages
3. Auth/AuthZ: missing checks at route boundaries, CORS/bind defaults
4. Deserialization (pickle, yaml.load without SafeLoader), eval/exec
5. XSS: unfiltered user HTML (dangerouslySetInnerHTML, innerHTML)
6. Ground every number/path on real tool output; no simulated output without a returned path.
