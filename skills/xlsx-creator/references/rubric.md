# Quality Rubric

1. Call create_xlsx for every spreadsheet request. Never answer with text only when the user asked for an Excel file.
2. Baue die Daten VOR dem Aufruf komplett auf: erste Zeile = sprechende Header, danach die Werte. Über gib sie als JSON-Array von Arrays.
3. Zahlen bleiben Zahlen (keine Währungssymbole in Zahlenzellen — Einheiten in den Header, z. B. "Umsatz (EUR)").
4. Bei Recherchen-Antworten: erst web_search (falls nötig), dann Tabelle aus den belegten Zahlen bauen. Erfinde keine Kennzahlen.
5. Wähle einen beschreibenden, ASCII-sicheren Dateinamen mit .xlsx.
6. Ground every number/path on real tool output; no simulated output without a returned path.
