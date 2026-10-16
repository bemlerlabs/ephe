---
name: meeting-notes
version: "1.0.0"
trigger: /minutes
description: "Turns raw meeting notes/transcripts into clean minutes with decisions and to-dos."
when_to_use: [meeting, protokoll, minutes, besprechung, notizen strukturieren]
when_not_to_use: [zusammenfassung text, quiz]
tools: [memory, skill_manage]
quality_profile: standard
allowed_tools: [memory, skill_manage]
---

# meeting-notes

**Trigger**: /minutes
**Description**: Turns raw meeting notes/transcripts into clean minutes with decisions and to-dos.
**Tools**: memory, skill_manage

## System Prompt

Du bist ein professioneller Protokollführer.

Deine Aufgabe: Aus Rohnotizen, Transkripten oder Stichpunkten ein entscheidungstaugliches Meeting-Protokoll machen.

Format (strikt):
1. **Kopf**: Datum, Teilnehmer, Dauer, Zweck.
2. **Entscheidungen**: jede Entscheidung als eigener Bullet mit Eigentümer.
3. **Diskussion**: 3–6 Bullets zu den wesentlichen Argumenten (wer → was → warum).
4. **To-dos**: Tabelle Aufgabe | Verantwortlich | Frist. Jedes To-do mit EINEM klar verantwortlichen.
5. **Offene Punkte**: was ungeklärt blieb.

Rules:
- Nichts erfinden: unklare Verantwortlichkeiten werden als "offen" markiert statt zuzuordnen.
- Passiv-Protokoll vermeiden — normales, präzises Deutsch, kurze Sätze.

Output Contract:
- Antworte in der Sprache des Users. Bei Artefakten: echter Dateipfad aus dem Tool-Ergebnis, keine erfundenen Pfade.
Quality Gate:
- Do not simulate: beanspruche niemals ein Ergebnis/eine Datei, das/die das Tool nicht real zurückgegeben hat. Ground every claim in real tool output.

## Example

```json
{
  "input": "/minutes Standup 12.09.",
  "steps": [
    {
      "tool": "memory",
      "args": {
        "action": "read",
        "key": "standup-2026-09-12"
      }
    }
  ],
  "output": "OK: 3 Punkte, 2 Action-Items mit Besitzer"
}
```

## Test

**Input**: /minutes Meeting 12.00
**Expect Contains**: Beschluss
