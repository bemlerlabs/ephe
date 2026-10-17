# Rubric — Plugin `code-shell`

Quality criteria for the golden matrix. Benchmark: **Opus 5.5 / GPT Astra 6** —
the pass³ rate of this suite is measured, not asserted. A case counts only
when ALL 3 runs pass (TAU reliability, as in evals/bench_option_b.py);
gate: **pass³ ≥ 90 % per plugin** (`ephe bench --run code-shell`).

Criteria:
1. **Cause before patch**: the error is named before anything is edited.
2. **Real tools**: run_shell/read_file/edit_file/run_tests — no blind command submission without a check.
3. **Verification**: after the fix the test/command runs and the result is shown.
4. **Minimally invasive**: no big-bang rewrite for a one-liner.
5. **Anti-slop**: no 'hier könnte Ihr Code stehen'.
