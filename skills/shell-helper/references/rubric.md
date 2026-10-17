# Quality Rubric

1. Nutze IMMER das run_shell Tool – der Befehl wird dem User zur Bestätigung präsentiert.
2. Erkläre JEDEN Befehl bevor du ihn vorschlägst: Was macht er? Was verändert er?
3. Warnung bei gefährlichen Befehlen (rm -rf, chmod 777, sudo etc.)
4. Empfehle immer ein Backup vor destruktiven Operationen.
5. Bevorzuge idempotente Befehle (mehrfach ausführen = gleiches Ergebnis).
6. Ground every number/path on real tool output; no simulated output without a returned path.
