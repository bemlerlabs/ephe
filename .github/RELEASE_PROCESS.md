# Release process

We ship a curated release at the end of every working round — weekly at the
current cadence. Tags are semver (`v4.1.0`); the Tauri bundle workflow
(`release.yml`) fires on `v*` tags and attaches desktop bundles as a draft.

## Steps

1. **Gates green** — `pytest`, `vitest`, `tsc`, `npm run build` on the exact
   commit you will tag. Never tag a red tree.
2. **Tag + push**: `git tag -a vX.Y.Z -m "short headline" && git push origin vX.Y.Z`.
   The bundle workflow starts automatically.
3. **Curate the notes** (this is the part that matters): publish/edit the
   release with a narrative body —
   - a headline naming the *theme* of the round, not the version number,
   - numbers (commits, tests, benchmark scores) measured on the tagged commit,
   - fixes grouped by *root-cause campaigns*, not chronologically,
   - every community diagnosis or contribution credited by handle.
4. **Post**: pin the release in Discussions/issues if it closes known reports.

## Notes skeleton

```markdown
# Ephe vX.Y.Z — <Theme headline>

**Release date:** YYYY-MM-DD
> One paragraph: why this release exists and who should care.
Measured at commit `<sha>`: N non-merge commits, M files changed, T tests green.

## ✨ Highlights
### <Campaign name>
- **Fix root cause, not symptom.** detail … (#PR/#issue, credit @handle)
```

Keep the body honest: if something is known-broken, name it in the notes.
