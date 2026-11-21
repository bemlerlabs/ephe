# Quality Rubric

1. Always state: target pattern, regex flavor (Python/JS/grep), relevant flags.
2. Provide positive AND negative test cases: 3+ strings that must match and 3+ that must NOT match.
3. Explain the regex step by step (tokens in plain language).
4. Avoid catastrophic backtracking (no nested quantifiers like (.*)*).
5. If run_shell is available: actually run the regex against the test cases (python3 -c) and show the result.
6. Ground every number/path on real tool output; no simulated output without a returned path.
