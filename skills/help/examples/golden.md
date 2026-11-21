# Golden Example

## Trace 1 (Standard, text skill - no tool)
1. Input: What can you do?
2. Final: Chat (direct, without a tool call).

Quality checklist (covers the rubric fields):
1. Give a concise capability map grouped by user goal, not internal implementation.
2. For risky features, mention whether approval, local files, internet, or macOS permissions are required.
3. Include one concrete example command for the feature the user asked about.
4. Keep the answer accurate to current built-in skills.
5. Do not overpromise fully autonomous behavior when a permission or confirmation gate exists.
6. Ground every number/path on real tool output; no simulated output without a returned path.
