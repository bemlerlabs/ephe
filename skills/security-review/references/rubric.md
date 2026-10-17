# Quality Rubric

1. Injection: SQL, Shell (subprocess mit shell=True / f-string-Kommandos), Pfadtraversierung (fehlende Whitelist-Checks)
2. Secrets/Token im Code, in Logs, in Fehlermeldungen
3. Auth/AuthZ: fehlende Prüfungen an Routen-Grenzen, CORS/Bind Defaults
4. Deserialisierung (pickle, yaml.load ohne SafeLoader), eval/exec
5. XSS: ungefiltertes User-HTML (dangerouslySetInnerHTML, innerHTML)
6. Ground every number/path on real tool output; no simulated output without a returned path.
