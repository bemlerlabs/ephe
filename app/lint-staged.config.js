// Ephe — W3a (2026-09-24): lint-staged configuration (plan step 4).
//
// No `git add` task here on purpose. Since lint-staged 10 the tool re-stages whatever
// a task rewrites; a bare `git add` in the list is legacy advice and, in a shared
// working tree, the one unbounded staging command in the pipeline. See .husky/pre-commit
// for why the whole frontend pass is scoped to commits that carry frontend files.
export default {
  '*.{ts,tsx}': ['prettier --write', 'eslint --fix'],
};
