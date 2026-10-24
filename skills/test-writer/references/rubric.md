# Quality Rubric

1. Always read the target code FIRST (read_file/file_search) before writing tests.
2. Strict structure: Given (state/inputs) / When (action) / Then (observable result) - in the test name or comment.
3. Test behavior, not implementation: edge cases, error paths, boundary values - not only the happy path.
4. One test = one statement. No test logic (if/loops) inside the test.
5. After writing, run the narrowest test run (run_shell) and report the result honestly - green OR red with analysis.
6. Ground every number/path on real tool output; no simulated output without a returned path.
