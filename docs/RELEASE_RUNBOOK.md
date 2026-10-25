# Release runbook

A release is a tag on `main` in this repository. There is no export step, no
snapshot and no release manifest: the commit CI validated is the commit that
ships.

## 1. Branch and pull request

Branch from `main` and open a pull request into `main`. Every required check
runs on the pull-request event (currently 25 contexts, including the macOS leg
and the coverage floor). Land with a local fast-forward; the GitHub web merge,
rebase and squash actions rewrite authorship and are not used.

```bash
git switch main && git pull --ff-only
git merge --ff-only <branch>
git push origin main
```

The push runs the same checks on the merged commit. A red push is fixed forward
with a new pull request.

## 2. Version

`pyproject.toml` `[project].version` is the source. `app/package.json`,
`app/src-tauri/tauri.conf.json` and `app/src-tauri/Cargo.toml` carry copies;
`uv.lock` and `app/src-tauri/Cargo.lock` follow. `tests/test_version_sync.py`
names all six.

## 3. Local gates

```bash
python -m pytest tests/ -q
python scripts/language_gate.py
node scripts/architecture_check.mjs
python scripts/readme_check.py --root .
python scripts/readme_check.py --public   # the install tag exists on GitHub
```

## 4. Dry run

```bash
gh workflow run release.yml --ref <branch>
```

The dispatch runs the release-bar test gate and the frontend gate.
`build-bundles` runs only on a tag push, so the dry run creates no draft.

## 5. Tag

`scripts/release_cut.sh` refuses a wrong branch, a dirty tree, disagreeing
version carriers, an existing tag and a HEAD that is not on `origin/main`. A
rehearsal writes nothing:

```bash
scripts/release_cut.sh --dry-run
scripts/release_cut.sh --push
```

The annotated `vX.Y.Z` tag starts `release.yml`. The test gate and the frontend
gate run first; the Tauri bundles land as a draft release.

## 6. Publish

The owner publishes the draft. That click is what moves `releases/latest` and
the updater feed. `readme_check.py --public` is the check that the install lines
name a tag that exists.
