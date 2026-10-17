---
name: api-tester
version: "1.0.0"
trigger: /api-test
description: "Fuehrt HTTP-Requests aus und prueft Status, Latenz und JSON-Schema."
when_to_use: [http request testen, api antwort pruefen, endpoint testen, response time]
when_not_to_use: [datenbank abfrage, statische datei]
tools: [fetch_url, execute_code, validate_json, write_file, memory, skill_manage]
quality_profile: standard
allowed_tools: [fetch_url, execute_code, validate_json, write_file, memory, skill_manage]
---

# api-tester

**Trigger**: /api-test
**Description**: Fuehrt HTTP-Requests aus und prueft Status, Latenz und JSON-Schema.
**Tools**: fetch_url, execute_code, validate_json, write_file, memory, skill_manage

## System Prompt

Du bist der API-Tester. Fuehre fetch_url aus, pruefe Statuscode und Response.
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
  "input": "/api-test https://api.example.com/health",
  "steps": [
    {
      "tool": "fetch_url",
      "args": {
        "url": "https://api.example.com/health"
      }
    },
    {
      "tool": "validate_json",
      "args": {
        "data": "<response>",
        "schema": "{\"type\": \"object\"}"
      }
    }
  ],
  "output": "Status: 200 | Schema: OK"
}
```

## Test

**Input**: /api-test
**Expect Contains**: "OK"
