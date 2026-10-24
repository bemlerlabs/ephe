# Golden Example

## Trace 1 (Standard)
1. Input: Create a QR code for https://ephe.dev
2. ToolCall: {"name": "create_qrcode", "arguments": {"data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: ok
4. Final: ok (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: Create a QR code for https://ephe.dev (source/path not found)
2. ToolCall: {"name": "create_qrcode", "arguments": {"data": "[[1,2],[3,4]]", "filename": "out"}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: ok.
