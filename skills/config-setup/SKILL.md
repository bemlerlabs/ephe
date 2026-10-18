---
name: config-setup
version: "1.0.0"
trigger: /setup
description: "Gefuehrter Setup-Dialog: Engine, API-Keys und Optionen."
when_to_use: [setup, konfiguration, engine waehlen, api key hinterlegen]
when_not_to_use: [schnelle abfrage, benchmark vergleich]
tools: [read_file, write_file, get_datetime, memory, skill_manage]
quality_profile: standard
allowed_tools: [read_file, write_file, get_datetime, memory, skill_manage]
---

# config-setup

**Trigger**: /setup
**Description**: Gefuehrter Setup-Dialog: Engine, API-Keys und Optionen.
**Tools**: read_file, write_file, get_datetime, memory, skill_manage

## System Prompt

Du bist der Ephe-Setup-Assistent. Lies und aktualisiere ~/.ephe/engine.json.
Ground every claim in real tool output.

Do not simulate: never claim a result unless the tool returned it in this session.
Ground every claim in real tool output.

Output Contract:
- Structured response with key facts from tool output
- No invented values or placeholder texts

Quality Gate:
- Accuracy verified against tool result
- No truncation of important information

## Example

```json
{
  "input": "/setup",
  "steps": [
    {
      "tool": "read_file",
      "args": {
        "path": "~/.ephe/engine.json"
      }
    },
    {
      "tool": "write_file",
      "args": {
        "path": "~/.ephe/engine.json",
        "content": "{\"provider\": \"ollama\", \"model\": \"gemma4:12b\"}"
      }
    }
  ],
  "output": "Engine gespeichert."
}
```

## Test

**Input**: /setup
**Expect Contains**: "OK"
