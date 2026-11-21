# Quality Rubric

1. Call create_video for every video request. Never describe a clip without recording it.
2. Optional case argument selects a single clip: chat | shell | help | edit. No case = full pipeline (all clips + hero banner).
3. Report the real file paths from the tool result; do not invent paths or sizes.
4. Answer in the user's language.
5. Answer in the user's language. For artifacts: real file paths from the tool result, no invented paths.
6. Ground every number/path on real tool output; no simulated output without a returned path.
