# Quality Rubric

1. Before: read the target code and its callers (file_search/read_file). Never change blindly.
2. Refactor in small, nameable steps: Extract Function, Rename, Move, Inline - each step explainable.
3. Justify every change: which code smell, which improvement (readability, duplication, coupling, testability).
4. If tests exist: run them after every step. If none exist: propose minimal safety tests first.
5. No feature creep: refactoring adds NO new features.
6. Ground every number/path on real tool output; no simulated output without a returned path.
