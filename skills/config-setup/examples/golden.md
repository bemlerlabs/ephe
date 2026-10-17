# Golden Example

## Trace 1 (Standard)
1. Input: /setup
2. ToolCall: {"name": "read_file", "arguments": {"path": "~/.ephe/engine.json"}}
3. Observation: {"provider": "ollama", "model": "gemma4:12b"}
4. Final: Aktive Engine: ollama/gemma4:12b. Keine Aenderung noetig.

## Trace 2 (Edge-Case: Fehlerpfad)
1. Input: /setup (neue Umgebung, keine engine.json)
2. ToolCall: {"name": "read_file", "arguments": {"path": "~/.ephe/engine.json"}}
3. Observation: [tool-error] Datei nicht gefunden
4. Final: Keine Engine konfiguriert. Via `ephe configure` waehlen.
