---
name: code-metrics
version: "1.0.0"
trigger: /metrics
description: "Erhebt LOC, McCabe-Komplexitaet und Import-Dichte fuer ein Projekt."
when_to_use: [metriken, loc zahlen, komplexitaet, projekt groesse, import analyse]
when_not_to_use: [einzelne function erklaeren]
tools: [list_directory, file_search, read_file, execute_code, memory, skill_manage]
quality_profile: source_grounded
allowed_tools: [list_directory, file_search, read_file, execute_code, memory, skill_manage]
---

# code-metrics

**Trigger**: /metrics
**Description**: Erhebt LOC, McCabe-Komplexitaet und Import-Dichte fuer ein Projekt.
**Tools**: list_directory, file_search, read_file, execute_code, memory, skill_manage

## System Prompt

Du bist der Code-Analyst. Zaehle LOC und McCabe-Komplexitaet.
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
  "input": "/metrics core/",
  "steps": [
    {
      "tool": "execute_code",
      "args": {
        "code": "import ast,pathlib\nfor p in pathlib.Path(\"core\").glob(\"*.py\"):\n    print(p.name, len(p.read_text().splitlines()))"
      }
    }
  ],
  "output": "| Datei | LOC |\n| skills.py | 610 |"
}
```

## Test

**Input**: /metrics
**Expect Contains**: "OK"
