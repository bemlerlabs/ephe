# Release process

A release is a tag on `main` in this repository. Product development happens
here, on the commits CI validates. The operator runbook is
[`docs/RELEASE_RUNBOOK.md`](../docs/RELEASE_RUNBOOK.md).

## Steps

1. **Green trunk.** Branch, pull request, all required checks, local
   fast-forward to `main`.
2. **Tag.** `scripts/release_cut.sh` refuses a dirty tree, a wrong branch, a
   version mismatch or a tag that already exists. It writes the annotated
   `vX.Y.Z` tag; `release.yml` builds the Tauri bundles as a draft release.
3. **Notes.** Write the release body: the theme of the round, the numbers
   measured on the tagged commit, fixes grouped by root cause, and every
   community diagnosis credited by handle.
4. **Publish.** The owner publishes the draft. That click is what moves
   `releases/latest` and the updater feed.

## Notes skeleton

```markdown
# Ephe vX.Y.Z — <Theme headline>

**Release date:** YYYY-MM-DD
> One paragraph: why this release exists and who should care.
Measured at commit `<sha>`: N non-merge commits, M files changed, T tests green.

## Highlights
### <Campaign name>
- <Fix, evidence, and the handle of a contributor where one applies.>
```

Keep the body honest: if something is known-broken, name it in the notes.
