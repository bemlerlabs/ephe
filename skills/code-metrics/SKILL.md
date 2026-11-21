---
name: code-metrics
version: "1.0.0"
trigger: /metrics
description: "Measures LOC, McCabe complexity and import density for a project."
when_to_use: [metrics, loc counts, complexity, project size, import analysis]
when_not_to_use: [explain a single function, code refactoring]
tools: [list_directory, file_search, read_file, execute_code, memory, skill_manage]
quality_profile: source_grounded
allowed_tools: [list_directory, file_search, read_file, execute_code, memory, skill_manage]
---

# code-metrics

**Trigger**: /metrics
**Description**: Measures LOC, McCabe complexity and import density for a project.
**Tools**: list_directory, file_search, read_file, execute_code, memory, skill_manage

## System Prompt

You are the code analyst. Count LOC and McCabe complexity.
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
  "output": "| File | LOC |\n| skills.py | 610 |"
}
```

## Test

**Input**: /metrics
**Expect Contains**: "OK"
