# Quality Rubric

1. Immer angeben: Ziel-Muster, verwendete Regex-Flavor (Python/JS/grep), relevante Flags.
2. Positiv- UND Negativ-Testfälle liefern: 3+ Strings, die matchen müssen, und 3+, die NICHT matchen dürfen.
3. Regex Schritt für Schritt erklären (Tokens in Klartext).
4. Katastrophales Backtracking vermeiden (keine verschachtelten Quantifizierer wie (.*)* ).
5. Wenn run_shell verfügbar ist: die Regex gegen die Testfälle real ausführen (python3 -c) und das Ergebnis zeigen.
6. Ground every number/path on real tool output; no simulated output without a returned path.
