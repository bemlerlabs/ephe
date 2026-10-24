# Rubric — Plugin `code-shell`

Quality criteria for the golden matrix. Each case runs 3 times and counts
only when all 3 runs pass (TAU reliability); target pass³ ≥ 90 %. The receipt
names the engine, the model, the commit and n. A comparison against Opus 5.5 /
GPT Astra 6 is only stated after those models have run the same cases.

Criteria:
1. **Cause before patch**: the error is named before anything is edited.
2. **Real tools**: run_shell/read_file/edit_file/run_tests — no blind command submission without a check.
3. **Verification**: after the fix the test/command runs and the result is shown.
4. **Minimally invasive**: no big-bang rewrite for a one-liner.
5. **Anti-slop**: no 'your code goes here' filler.
