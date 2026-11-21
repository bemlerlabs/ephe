# Golden Example

## Trace 1 (Standard)
1. Input: Create an image of a fox in the Black Forest
2. ToolCall: {"name": "generate_image", "arguments": {"prompt": "A fox in the Black Forest", "filename": "out"}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Create an image of a fox in the Black Forest (source/path not found)
2. ToolCall: {"name": "generate_image", "arguments": {"prompt": "A fox in the Black Forest", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
