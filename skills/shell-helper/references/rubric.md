# Quality Rubric

1. Always use the run_shell tool - the command is presented to the user for confirmation.
2. Explain EVERY command before suggesting it: what does it do? What does it change?
3. Warn about dangerous commands (rm -rf, chmod 777, sudo etc.).
4. Always recommend a backup before destructive operations.
5. Prefer idempotent commands (running them again yields the same result).
6. Ground every number/path on real tool output; no simulated output without a returned path.
