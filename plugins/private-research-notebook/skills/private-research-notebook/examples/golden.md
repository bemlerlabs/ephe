# Golden Example

## Trace 1 (Standard, notebook question)
1. Input: Build a notebook from ~/Documents/strategy and name the top three risks.
2. ToolCall: {"name": "create_source_notebook", "arguments": {"paths": ["~/Documents/strategy"], "title": "Strategy review"}}
3. ToolCall: {"name": "query_source_notebook", "arguments": {"notebook_path": "<SOURCE_NOTEBOOK_FILE>", "question": "top three risks"}}
4. Observation: [S001-C004], [S002-C001]
5. Final: The three risks are ... [S001-C004], [S002-C001]. Evidence level: primary. Gap: no financial source was supplied.

## Trace 2 (Edge case: missing source)
1. Input: Build a notebook from ~/Documents/missing and answer the main claim.
2. ToolCall: {"name": "list_directory", "arguments": {"path": "~/Documents/missing"}}
3. Observation: [tool-error] directory not found
4. Final: No notebook was created because the source path does not exist. No claim was invented. Next step: provide the local files.
