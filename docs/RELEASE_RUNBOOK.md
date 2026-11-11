# Release runbook

A release is a tag on `main` in this repository. There is no export step, no
snapshot and no release manifest: the commit CI validated is the commit that
ships. Commits between tags are normal — the release channel ignores them and
the opt-in commit channel follows them ([UPDATES.md](UPDATES.md)); only the tag
makes a release.

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
names all six, and `scripts/version_carriers.py` is the one list the cut, the
checklist, `scripts/bump_version.py` and the release workflow's version guard read.
Bump all six with one command rather than by hand:

```bash
python scripts/bump_version.py --version X.Y.Z
```

The install lines carry the same number: the three root READMEs and the four
start documents (`docs/QUICKSTART.md`, `docs/INSTALL.md`,
`docs/INSTALL_OPTIONS.md`, `docs/FIRST_RUN.md`) name the release tag in the
`raw.githubusercontent.com` URL and in the sentence beneath it. They name the
new tag *before* it exists — `scripts/release_cut.sh` tags the commit that
carries them — so `readme_check.py --public` is what proves the tag now exists
(step 6). Flip all seven files in the version commit, not after the tag.

## 3. Local gates

```bash
python -m pytest tests/ -q
python scripts/language_gate.py
node scripts/architecture_check.mjs
python scripts/readme_check.py --root .
python scripts/readme_check.py --public   # the install tag exists on GitHub
python scripts/changelog_unreleased.py --check   # every feat/fix commit since the last tag is named
python scripts/catalog_freshness.py              # the committed catalogs are what their sources imply
```

`scripts/release_cut.sh` runs `scripts/release_checklist.py` as its first gate, so the cut and the
tag-triggered workflow judge the same checklist instead of two disjoint sets.

## 3a. The signing key

The updater pubkey in `app/src-tauri/tauri.conf.json` belongs to the `ephe2` key pair

```
minisign key id  e01157dba5c1d5b5     ->  ~/.tauri/ephe2.key.pub  (matches the config, byte for byte)
                                        ~/.tauri/ephe.key.pub    (the retired pair, matches nothing)
```

A build signed with the default path produces a bundle the client refuses, so the local signed
build names the pair explicitly and the release checklist confirms it:

```bash
EPHE_UPDATER_KEY="$HOME/.tauri/ephe2.key" python scripts/release_checklist.py --version X.Y.Z
# release-check: PASS signing-key    signing key matches the updater pubkey
```

The private key is passphrase-protected: the passphrase is an owner input, entered when the build
signs, and CI carries the same pair as the `TAURI_SIGNING_PRIVATE_KEY` secret. A missing or
mismatched key is a checklist FAIL and a `release.yml` build refusal, not a warning: a milestone
release ships a signed shell. `ephe.key` stays on disk as the retired pair, which is why the check
names a matching sibling.

A machine with no key can still rehearse or build locally. `--dry-run` prints the plan and
touches nothing; `--unsigned` builds without updater artifacts:

```bash
scripts/release_desktop.sh --dry-run
scripts/release_desktop.sh --unsigned
```

The unsigned build has no `.sig` and no `latest.json`, and `--publish` is refused on it.

### The browser the frontend gate drives

`pnpm install` installs no browser. The revision is pinned but the binary is not
shipped: `@playwright/test` is `1.64.0` in `app/package.json` and the lockfile, and
that `playwright-core` asks for exactly `chromium` / `chromium-headless-shell`
revision **1248** (`app/node_modules/playwright-core/browsers.json`). A machine whose
`ms-playwright` cache predates it fails every browser test with
`Executable doesn't exist at .../chromium_headless_shell-1248/...` — measured on an
empty cache 2026-11-09: 124 of the 139 collected tests red in 10 s, none of them a
product defect. Nothing in the config can fetch the binary, so the step is an
environment one and it is automated at the command that needs it:

```bash
cd app
pnpm run test:e2e        # pretest:e2e runs `playwright install chromium`, a no-op once 1248 is cached
```

On a fresh Linux box install the OS libraries too. `--with-deps` looks for `sudo`
before it looks for a missing library, so on a runner without passwordless sudo it
exits 1 and downloads nothing — the probe the frontend gate in
`.github/workflows/frontend-build.yml:95` carries:

```bash
cd app
if sudo -n true 2>/dev/null; then pnpm exec playwright install --with-deps chromium
else pnpm exec playwright install chromium; fi
```

`--list` is the check that the leg collects what the config says: 139 tests in 27
files (127 `chromium` + 12 `load-sensitive`), and no `setup-e2e`, `dogfood`,
`artifact-export` or `u6-focus`.

## 4. Dry run

```bash
gh workflow run release.yml --ref <branch>
```

The dispatch runs the release-bar test gate and the frontend gate.
`build-bundles` runs only on a tag push, so the dry run creates no draft.

## 5. Tag

`scripts/release_cut.sh` refuses a wrong branch, a dirty tree, disagreeing
version carriers (all six), an existing tag and a HEAD that is not on
`origin/main`. A rehearsal writes nothing:

```bash
scripts/release_cut.sh --dry-run
scripts/release_cut.sh --push
```

`--skip-gates` is the audited exception: it needs `--skip-reason "why"` (or
`EPHE_RELEASE_SKIP_REASON`) and appends a record with the tag, the commit and the
reason to `~/.ephe/release-skips.jsonl` (or `EPHE_RELEASE_RECEIPT`).

The annotated `vX.Y.Z` tag starts `release.yml`. The test gate and the frontend
gate run first; the Tauri bundles land as a draft release.

## 6. Publish

The owner publishes the draft. That click is what moves `releases/latest` and
the updater feed. `readme_check.py --public` is the check that the install lines
name a tag that exists. The publish job measures the released DMG and source
archive, refuses a template hash that matches neither, renders the tap and bucket
manifests, and then publishes them and the npm wrapper.

## 7. After the tag

Policy: `main` carries the next milestone from the day the previous one shipped.
Move all six carriers in one commit and do not tag again for a fix:

```bash
python scripts/bump_version.py --next-minor
git add pyproject.toml app/package.json app/src-tauri/tauri.conf.json \
  app/src-tauri/Cargo.toml app/src-tauri/Cargo.lock uv.lock
git commit -m "chore: open the next milestone"
```

A version that stays equal to the last tag makes `main` look like the release it
already shipped, and a release-pinned installation then cannot tell them apart.
