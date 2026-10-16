# Golden Example

## Trace 1 (Standard)
1. Input: /metrics core/
2. ToolCall: {"name": "execute_code", "arguments": {"code": "import pathlib; [print(p.name, len(p.read_text().splitlines())) for p in pathlib.Path(\"core\").glob(\"*.py\")]"}}
3. Observation: skills.py 650
registry.py 1250
4. Final: 2 Module, groesstes: registry.py (1250 Zeilen).

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /metrics nonexist/
2. ToolCall: {"name": "list_directory", "arguments": {"path": "nonexist/"}}
3. Observation: Directory not found
4. Final: Pfad nicht gefunden, keine Metriken.
