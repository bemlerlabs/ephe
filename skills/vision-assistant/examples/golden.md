# Golden Example

## Trace 1 (Standard)
1. Input: /scan ~/Desktop/test.png
2. ToolCall: {"name": "analyze_image", "arguments": {"path": "tests/test_example.py", "question": "What is in it?", "region": [0, 0, 100, 100]}}
3. Observation: image
4. Final: image (supported by tool output).

## Trace 2 (Edge case: error path)
1. Input: /scan ~/Desktop/test.png (source/path not found)
2. ToolCall: {"name": "analyze_image", "arguments": {"path": "tests/test_example.py", "question": "What is in it?", "region": [0, 0, 100, 100]}}
3. Observation: [tool-error] entry not found
4. Final: Report the error honestly; next step: image.
