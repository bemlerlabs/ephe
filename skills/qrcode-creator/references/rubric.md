# Quality Rubric

1. Call create_qrcode for every QR request. Never describe a QR code without creating it.
2. Extrahiere den Payload präzise: URL komplett (inkl. https://), WLAN im Format WIFI:T:WPA;S:Name;P:Passwort;;, Kontakt als vCard wenn gewünscht.
3. Kein Payload erkennbar? Frage genau NACH, statt etwas zu raten.
4. Antworte in der Sprache des Users und nenne den echten Dateipfad.
5. Antworte in der Sprache des Users. Bei Artefakten: echter Dateipfad aus dem Tool-Ergebnis, keine erfundenen Pfade.
6. Ground every number/path on real tool output; no simulated output without a returned path.
