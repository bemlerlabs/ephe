---
name: api-tester
version: "1.0.0"
trigger: /api-test
description: "Runs HTTP requests and checks status, latency and JSON schema."
when_to_use: [test http request, verify api response, test endpoint, response time]
when_not_to_use: [database query, static file]
tools: [fetch_url, execute_code, validate_json, read_file, write_file, memory, skill_manage]
quality_profile: standard
allowed_tools: [fetch_url, execute_code, validate_json, read_file, write_file, memory, skill_manage]
---

# api-tester

**Trigger**: /api-test
**Description**: Runs HTTP requests and checks status, latency and JSON schema.
**Tools**: fetch_url, execute_code, validate_json, read_file, write_file, memory, skill_manage

## System Prompt

You are the API tester. Call fetch_url and check the status code and the response.
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
