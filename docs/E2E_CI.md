# E2E over the built bundle — the state of the `frontend-build` browser legs

Written 2026-11-24. `frontend-build.yml` pointed at two dated pages under `docs/` that the tree never
held: one promised the measurements and the reasoning behind the e2e leg, its name carrying the date
2026-10-11, and the other promised the defect list of a theme sweep, its name carrying 2026-10-18.
Neither name appears anywhere else in the repository, and no commit ever added either file:

```
git log --oneline --all --diff-filter=A -- 'docs/*E2E*' 'docs/*THEME*'
  (empty)
```

Nothing was decided on 2026-10-11 or 2026-10-18 and written down here after the fact. What this document
holds is the state of the path as measured on 2026-11-24 on one developer machine, plus the code barriers
that decide what a green step may mean. Every number names the command that produced it, the engine it ran
on and the machine it ran on. Where the CI box differs from this machine, the difference is named.

## The machine and the versions

One Apple Silicon Mac, 10 logical CPUs (`sysctl -n hw.ncpu`), macOS. This document's runs are the first
runs of these legs on this tree on this machine.

```
cd app && pnpm exec playwright --version      → Version 1.64.0
rg -n '"@playwright/test"' app/package.json    → 71:    "@playwright/test": "1.64.0",
```

The Python side of the repository is a different engine and gets a different browser: the project's Python
environment carries playwright **1.62.0**, which wants chromium **v1234** (Chrome for
Testing 151.0.7922.34). The npm leg below is **1.64.0** and wants chromium **v1248** (CfT 156.0.8078.4).
Reading one version as the other is how a browser-leg claim stops describing the leg it names.

## The download the timeout is sized for

The install step (`frontend-build.yml:124-146`) runs `pnpm exec playwright install chromium` after
`pnpm install`, because the browser binary is not a package dependency. Its `--with-deps` apt pass is
bounded and falls back to the plain download; when even that fails the step sets `PLAYWRIGHT_NO_BROWSER=1`
and the three e2e steps below skip, so a CDN outage cannot redden a product gate.

Measured, from the install log of this machine's first `@playwright/test` 1.64.0 setup:

```
Downloading Chrome for Testing 156.0.8078.4 (playwright chromium v1248)
  from https://cdn.playwright.dev/builds/cft/156.0.8078.4/mac-arm64/chrome-mac-arm64.zip
  185.8 MiB                                   (log /tmp/pw_install_npm.log)
  99.0 MiB                                    (chromium headless shell, same log)
du -sh ~/Library/Caches/ms-playwright/chromium-1248            → 366M
du -sh ~/Library/Caches/ms-playwright/chromium_headless_shell-1248 → 203M
```

285 MiB across the two artifacts, so the `~150 MB` in the timeout comment at `frontend-build.yml:32`
understates what the step pulls by roughly a fifth of a gigabyte. The timeout itself stays 30 minutes, and
its other half is the pnpm install, the vitest suite and the build.

## The main leg: the 19 named spec files

The step (`frontend-build.yml:181-217`) names its files one by one so a spec added tomorrow cannot join by
accident, and hands the three timing files to their own `--workers=1` step above. Collected count:

```
cd app && pnpm exec playwright test -c tests/playwright/playwright.config.ts --list <the 19 files>
  Total: 98 tests in 19 files                          exit 0, 00:07:38
```

The workflow comment at `:32` says this leg runs 91 specs. Today it collects 98 tests in those 19 files.

Run of the step as CI invokes it (`--reporter=list`, default workers), 00:08:01 to 00:08:50, exit 0,
log `/tmp/e2e_step_run.log`:

```
Running 98 tests using 5 workers
67 passed (47.7s)      31 skipped      real 49.01 s   user 129.64 s   sys 26.52 s
```

Five workers is Playwright's default here, half of 10 logical CPUs; there is no `workers` at the top of
`playwright.config.ts`. The config's own note at `:114-118` records ten workers on the CI box for the
timing files, measured 2026-10-14, so this machine runs the leg with half the parallelism CI brings to it.

Per file, read off that run:

| spec | passed | skipped |
|---|---|---|
| app-boot | 5 | 0 |
| glass-layers | 4 | 0 |
| langsession | 0 | 1 |
| mobile-viewport | 26 | 0 |
| modals | 4 | 0 |
| panel | 12 | 2 |
| plan-live | 0 | 2 |
| plan-page-floors | 2 | 0 |
| q-quality | 3 | 5 |
| r12 | 3 | 2 |
| r14 | 4 | 3 |
| r36-dd27 | 0 | 3 |
| r36-fixes | 2 | 1 |
| r41-toolcards | 0 | 2 |
| r42-livetakt | 0 | 1 |
| r5-perceived-latency | 0 | 5 |
| sidebar-row | 2 | 0 |
| u6-keyboard | 0 | 3 |
| z16-plan | 0 | 1 |

A third of the leg skips, and each skip is decided by a guard in the spec, which is what makes the number
readable instead of suspicious. Three classes, with the line that decides each:

- The built bundle ships no `window.__epheStore` handle, so specs that seed state through it stand down:
  `app/tests/playwright/q-quality.spec.ts:260,318,362,392`, `r12.spec.ts:17,51`, `r14.spec.ts:62`,
  `r41-toolcards.spec.ts:27`, `r42-livetakt.spec.ts:63`, `z16-plan.spec.ts:22`, `langsession.spec.ts:20`,
  `panel.spec.ts:278`. The handle is dev-only by product design, and `app/scripts/dev_handle_check.py`
  run against `dist` (the step at `frontend-build.yml:113-122`) is what keeps it out of `dist/`.
- No backend on a static dist: `r36-dd27.spec.ts:17` (psutil gauges), `panel.spec.ts:133` (send needs an
  API), `r36-fixes.spec.ts:54` (terminal WebSocket), `r14.spec.ts:108` (workspace listing).
- Lanes that are opted into elsewhere: `u6-keyboard.spec.ts:430` runs under
  `app/tests/playwright/latency.config.ts`, and `plan-live.spec.ts:58,104` waits for `EPHE_PLAN_LIVE=1` before
  spending a real engine turn.

The leg's own barriers, from `app/tests/playwright/playwright.config.ts`: `timeout: 15000` (`:55`),
`retries: 0` (`:56`), viewport 1280×800 (`:60`), and a `webServer` that runs
`python3 -m http.server <port> --directory dist` on a port picked at run time (`:70-72`) so the leg can only
ever talk to a server it started — the shape `tests/test_playwright_port_hygiene.py` holds. No backend,
no Vite dev server, no engine. Two projects collect: `chromium` (`:88-110`, with its own repeated
`testIgnore`) and `load-sensitive` at `workers: 1` (`:120-123`).

## The theme leg

Invoked by CI alone, one worker, because it reads eight-second route timeouts and a pool of ten browsers
makes a slow route look dead. Run of that step as CI invokes it, 00:15:03 to 00:16:22, exit 0, log
`/tmp/theme_step_run.log`:

```
cd app && pnpm exec playwright test -c tests/playwright/playwright.config.ts --reporter=list \
  --workers=1 tests/playwright/theme-parity.spec.ts
1 passed (1.3m)
theme-parity workspaces/forest/390 text=0 boundary=0 render=0    (one line per surface, ground, width)
```

The instrument (`app/tests/playwright/theme-parity.spec.ts:7-37`) walks the painted DOM of every navigable
surface at 390 and 1280 px on the one shipped ground, computes WCAG contrast of each visible text run
against the ancestor stack it actually composites onto, and each control boundary against the ground behind
it. `getComputedStyle` only, no axe-core, per the wave rule against new npm packages.

Its committed record is `app/tests/playwright/theme-parity.baseline.json`, which is also the defect list the
removed citation promised:

```
python3 -c "json.load(...)":  entries 163, non-zero rows 6, metric entries 10
  intro-scene/forest/1280  boundary 1, text 1        intro-scene/forest/390   boundary 1, text 1
  setup/forest/1280        boundary 1, text 1        setup/forest/390         boundary 1, text 1
  tour-usage/forest/1280   text 1                    tour-usage/forest/390    text 1
```

The gate is a ratchet over that file: a surface above its entry, or a new surface without one, is red, and
the file moves in its own commit with the before and after counts. The contrast floor those numbers serve is
held in `docs/ACCESSIBILITY.md:39-48`, which already names `theme-parity.spec.ts` as where text and boundary
contrast live.

The capture pass, `EPHE_THEME_SWEEP=1`, writes PNGs to `out/forest-sweep-2026-10-19/`
(`theme-parity.spec.ts:32-33,42`). `.gitignore:166-168` ignores `out/**/*.png`, `*.jpg` and `*.webp`, so that
pass leaves no committed evidence and never did: no sweep capture is in the tree, and the baseline is the
only committed statement of the sweep's result. `theme-parity.spec.ts` cites `docs/DESIGN.md` at three points — §3 at `:11`, §12 at `:30`, §8 at `:579` —
and that document is not in the tree. It is recorded here so the claim has one home while the
spec header waits for its owner to give it one.

## Not measured

- No GitHub-hosted runner ran anything in this document. The runners for this repository are blocked on the
  Actions budget, so every number above is local and none of them is a CI result.
- The CI box's worker count: `playwright.config.ts:114-118` reports ten for the timing files, measured
  2026-10-14. This machine gives five. Not re-measured here.
- The timing leg (`composer-width`, `r33-a11y`, `r4-motion-paint`, `frontend-build.yml:147-164`) was not run
  today; only its contents and its serial barrier are described above.
- WebKit and Firefox: the config has no such project, and the Python browser set skips four webkit cases
  (`Executable doesn't exist at …/ms-playwright/webkit-2336/pw_run.sh`). No coverage to claim.
- `visual.spec.ts` needs `EPHE_VISUAL=1` (`playwright.config.ts:125-135`), and `dogfood`, `artifact-export`,
  `setup-e2e` and `u6-focus` are ignored by the `chromium` project (`:102-110`). None ran.
- The W10-51 story in the old comment — four of the then-21 files left out, ten red assertions between
  them — has no home: `rg -n 'W10-51' app/tests/playwright/` is empty and `git log --all --grep='W10-51'`
  is empty. What the tree can show today is the guards those files now carry, listed above.

## Reproducing the numbers

```
cd app
pnpm install --frozen-lockfile && pnpm run build
pnpm exec playwright install chromium
pnpm exec playwright test -c tests/playwright/playwright.config.ts --list <the 19 files named in the step>
pnpm exec playwright test -c tests/playwright/playwright.config.ts --reporter=list <the same 19 files>
pnpm exec playwright test -c tests/playwright/playwright.config.ts --reporter=list --workers=1 \
  tests/playwright/theme-parity.spec.ts
```

The dist has to be the one under test: the leg serves `app/dist` and nothing else.
