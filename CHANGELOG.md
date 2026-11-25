# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

### Added

- plugins: the two studio bundles held out of the first release now ship with their
  implementations, tests and provenance. `ephe-motion-studio` cuts a motion film on this machine
  through ffmpeg and refuses when ffmpeg is absent; `ephe-template-library` copies a licensed
  template and carries its source and sha256 beside it (`6ce3c6d`).
- community: reports arrive through forms. A bug report, an install and first-run report and a
  capability request under `.github/ISSUE_TEMPLATE/`; a question, an idea and a built-with-ephe
  post under `.github/DISCUSSION_TEMPLATE/`. A free-form issue is no longer offered, and
  `SECURITY.md` stays the only channel for a finding.
- ci: a deep dataflow leg over `core/`, `server/` and `app/src`, with its queries and
  scope in one file. A pattern scanner answers what a call site looks like; this one
  answers whether a value entering at an HTTP route reaches a sink three calls away, and
  the engines behind it are licensed for public repositories, which is the state this
  repository is in as of 2026-11-23. Rust is absent because no query pack exists for it,
  and no build step runs because extraction reads sources (`fdacd76`).
- docs: `decisions/ci-capacity-and-runners.md`, the record six workflow comments cite and
  which was never in the tree. It holds the fork guard and what was measured for it, the two
  runner lanes and the single variable that switches between them (measured 2026-11-23:
  unset, with 0 runners registered, so every leg has been running hosted), the 146.4 hosted
  minutes one push costs on this account, what the plan refuses with the API answer that
  shows it, and the 2026-11-23 sequence in which the minute budget ran out, the repository
  went public, and the account lock turned out to cover public repositories of the same
  account while an organization's public repository ran normally at the same minute
  (`5ebce54`, placed under `decisions/` per the public-docs policy).
- CI: two action pins corrected against upstream. `dtolnay/rust-toolchain` was pinned to a
  commit that no upstream ref names any more and labelled `# stable`; it now pins the tip of
  the version branch `1.97.1`, which is the rustc every Rust number in this repository was
  produced with. `tauri-apps/tauri-action` was pinned to the annotated tag object of
  `v0.5.23` rather than the commit it points at, which no `uses:` line resolves; it now
  names the commit, and the major bump upstream has since published waits for a release
  dry-run. Zizmor at `--persona=auditor` reports no finding at warning or above for the
  whole workflow tree, online rules included (was four high and one warning).
- docs: `DESIGN.md`, the page five comments in the app and its tests cite by section (`§3` the
  one ground, `§8` a control's edge against a decorative hairline, `§12` a baseline moving in
  its own commit). It follows the brand page's rule -- state only what a file in this checkout
  already does -- so each of the twelve sections names the guardian that refuses its absence:
  the thirteen `app/src/styles/*.test.ts` files and `tests/test_forest_only.py`. The decision
  ledger also gained the line that was missing: one visual language, one theme, the forest,
  decided 2026-10-19 and recorded here on 2026-11-24, with the nine files that hold it and no
  reason invented for a choice whose file carried none.
- docs: `LATENCY_BUDGETS.md`, `COVERAGE_GAPS.md` and `CI_HYBRID_CAPACITY.md`, the three pages the
  scheduled legs cited by a dated name the tree never held. Each number names its machine,
  interpreter and load; two counts the workflows carried could not be reproduced and were
  replaced rather than copied -- the five loaded per-task latencies in `tests.yml` now show
  the skip reason they actually produce, and the "about five times" tracing cost in
  `ci-gates.yml` is the measured 1.47x (200.32 s traced against 136.01 s untraced, same tree,
  same box, two minutes apart). One claimed mechanism did not reproduce: under `-n 4` the two
  coverage forms agree to the statement on both subsets tried, so the comment points at the
  measurement instead of repeating the assertion.
- docs: `E2E_CI.md`, the measurements the `frontend-build` browser legs promised in a dated
  page the tree never held. It names the versions the leg installs (`@playwright/test`
  1.64.0, chromium v1248 / Chrome for Testing 156.0.8078.4), the download it is sized for,
  the 98 tests in the 19 named spec files with the measured run and each of the 31 skips
  traced to the guard that decides it, the theme leg with its 163-row baseline and the six
  rows above zero, and a chapter of what was never measured. Three stale counts in the
  workflow comments it replaces -- 91 specs, ~150 MB, a 1400-test vitest suite -- are
  corrected to what the commands print today.
- scripts: `env_lock_agreement.py` compares the environment that is running against the lock it is
  pointed at and refuses the difference. It found what no leg could see: the interpreter every gate and
  every suite run on this machine uses had `wasmtime` 47.0.1 installed while uv.lock pins 50.0.1,
  forty-three crates.io advisories behind and including the sandbox escape the engine floor exists for,
  while the advisory legs scored the pinned version and the wheel's own database record read clean. The
  suite's own tools (`dev`, `bench`) are reported in a column that prints without refusing; every other
  extra counts as product, so an unclassified one is held to the lock. 22 tests cover it, one of them a
  planted deviation that has to be caught (`658cd90`).
- ci: `scripts/citation_check.py`, a gate over what a comment claims. Six comments in the suite
  cited pages this repository never contained — `git log --diff-filter=A` finds no commit that ever
  wrote any of them — and a reader trusts a pointer and stops reading the code. The instrument reads
  comments and docstrings under `scripts/`, `tests/` and `.github/` through `tokenize` and `ast`, so a
  fixture path a test invents in a string stays the test's own business, and refuses a path with no
  file behind it, a `path:line` or `path:first-last` pointer landing past the end of a real file, and
  the dated, `PLAN` or `DRAFT` naming style a working note takes before it is deleted. One grep-able
  exemption, `# citation:absent <path> - reason`, for a removal fence that has to name the path it
  forbids; it exempts that one path inside its own comment block and buys nothing against a stamped
  name. It ships at zero findings over 1020 files, and 48 files carry the corrections that got it
  there (`5a5e24a`).
- dev: `make hooks` points a checkout's git at the hook this repository already ships.
  `.husky/pre-commit` was tracked, executable and complete, and nothing set `core.hooksPath`, so git
  never ran it and every fresh clone committed unchecked while `AGENTS.md` said in the present tense
  that hooks stay on. The target refuses without the executable bit, copies nothing into `.git/hooks`,
  and `make doctor` now prints the configured path or `OFF — no hook runs on commit; run make hooks`.
  Measured in a second worktree of the same repository after one run: a staged file carrying a German
  identifier was refused with `language gate: FAIL` naming the file and its `0 -> 1 (+1)` delta, and a
  ratchet-clean file was accepted by the hook itself (`3c3d937`).
- ci: the registry guard runs where a clone cannot skip it. `scripts/registry_guard.py`
  refuses a remote script handed to a shell in every file under `packaging/`, `scripts/`,
  `server/`, `core/` and `.github/`, and until now it ran only in the pre-commit hook and in
  `make verify` — a clone without hooks installed never saw it. It is a step of its own in the
  repository gates now, the same call the hook makes, line for line, pinned by
  `tests/test_registry_guard_in_ci.py` (12 passed with the docs test, exit 0; cutting the step
  out of the workflow turns `5 failed`, exit 1). Measured here: `registry-guard: PASS 558
  file(s)`, exit 0 (`7875447`).
- docs: `NPM_PUBLISHING.md`, the publish path written against what exists rather than against
  intention. Nothing is published to the registry; a future publish job needs the release
  environment with a human in front of it and a short-lived OIDC credential minted for one job,
  and neither exists today — `gh api repos/bemlerlabs/ephe/environments` answers
  `total_count: 0`, and GitHub refuses the required-reviewer rule on this plan. The page says so,
  names the dry run a first upload must pass, and holds the revocation order (`7875447`).

- install: an artifact is signed before it is trusted. `core/plugin_signing.py` verifies a detached
  record against keys under `~/.ephe/trusted-keys/`, `core/plugin_install.py` quarantines what fails,
  and a permission delta that changed against the installed state stops the install until its digest
  is named back with `--approve-permissions`. A local unsigned folder installs only under
  `--trust-local`, which says in the answer that no key spoke for it (`03791b1`).
- settings: a row names its copy instead of carrying it. `core/settings_schema.py` emits `labelKey`
  and `optionKeys`, `core/settings_hints.py` holds the key table in English, and the German and English
  leaves travel in `app/src/lib/settingsCopy.{de,en}.json` — 131 each, loaded lazily, one leaf per key,
  so a hint that exists nowhere is a failing register test rather than a blank line under a control
  (`6bdb3f0`).
- brand: the thinking state has a mark of its own. `ThinkingMark.tsx` turns the `E` at
  `--ephe-think-cycle: calc(var(--ephe-scene-beat) * 6)`, and under `prefers-reduced-motion` or
  `html.no-motion` it is painted still — asserted against `getComputedStyle().animationName`, not
  against a class name (`b5e95e3`).

### Fixed

- A bundle's identity no longer follows the interpreter's bytecode cache: importing a plugin
  handler in a test run moved the digest the catalogue and the signature are computed over, so a
  fresh checkout and a warm working tree disagreed and the freshness gate failed on the two new
  bundles. The catalogue now carries the hashes a clean checkout computes.
- frontend: three specs that answered for nothing. The slash-command cases polled up to 5000 ms for
  a reply a mock had already produced, and one of them asserted that the mock returned what it was
  told to return — the `any`-typed pair behind it is what held the frontend leg red, two
  `@typescript-eslint/no-explicit-any` errors, not the timing it looked like. They now assert what the
  client did with the text and take one scheduler tick inside `act`; the keyboard walk checks its own
  stop list after the walk instead of trusting the one read before it; and the restored-session cases
  ask the list what it does when a row is inserted ahead of another, which is the behaviour the earlier
  source-reading case only pretended to cover. An earlier attempt at the same three cases (`61b2063`)
  settled the mock and left the leg red on the lint errors named above; `b528e9e` is what closed it.
- plugins: the nineteen tools of the two studio bundles reached the engine without a single
  parameter. Their manifests carried no `properties`, so the served schema listed none while the
  handler behind `ephe_motion_add_caption` hard-required five (`project_id`, `text`, `start`,
  `duration`, `expected_revision`) and the path-form check read `target_dir` as an empty string.
  Each now carries its type, its bounds and a sentence the engine reads, and the three contract
  tests that judged the surface against names typed beside them read the manifests instead, so
  adding a bundle is a fact and a bundle claiming another's tool is a failure.
- docs: the Chinese and Spanish READMEs and `docs/PLUGINS_OVERVIEW.md` state nineteen bundles,
  twelve plugins and seven presets, the numbers `marketplace/index.json` reports; the English
  README already did.
- licence: the Licensed Work parameter named `Ephe, version 0.1.0-beta.2 or later`, a string from the
  pre-release line, while the tree carries 0.1.0 — so a reader could not tell whether the copy in
  front of them was the Licensed Work. Only the version text moved; the Additional Use Grant stays
  `None` (`62e66cb`).
- supply-chain: the desktop shell's lock pinned `url` 2.5.8, which carries an advisory with a fix in
  2.5.9, and our own advisory leg refused the tree over the missing decision. Bumped to 2.5.9 with
  its `form_urlencoded` 1.2.3 dependency rather than writing an ignore row for a crate that was simply
  one patch behind; 133 shell tests pass (`24c6a10`).
- supply-chain: the same leg's crates.io probe found `cookie` 0.18.1 in the shell's dependency graph, a
  published advisory (RUSTSEC-2026-0594, GHSA-8wcq-xq25-7fhm) with 0.18.3 as its fix. Bumped by
  `cargo update -p cookie@0.18.1 --precise 0.18.3` over 147 unchanged dependencies, with the advisory
  leg, the resolver check and 133 shell tests green (`8cf3a58`).
- supply-chain: nine advisories the databases report for the locked engine version — wasmtime 50.0.1,
  the sandbox the Cell runs foreign code in — carried no line in the register, which is the record the
  leg that refuses an undecided advisory reads. Each record now carries the reachability measured from
  the shipped configuration (threads and gc off in the wheel's own engine config, `wasi:http` never
  linked, no network in the sandbox, memory64 never passed by either product seam) and the reason the
  published fix cannot be taken today: crates.io fixed eight at 50.0.2 and the wasmtime-wasi one at
  50.0.3, and PyPI publishes neither. The recommendation the rows carry is the move to 51.0.0, which
  those databases report clean. Two justifications had gone stale with their subject and were rewritten
  against new measurements, and the pip row is held by a fence test over the hash-pinned bootstrap wheel
  in `install.sh` and the `Dockerfile` where prose carried it before (`7d1d4f0`).
- hooks: `scripts/ci_local.sh`, the pre-commit script that runs the CI legs locally, did not run the
  New-file rule over paths no committed baseline covers, so six prose tells on a new test file reached
  CI before anything read them. The hook now runs that instrument over the staged scope, proven with a
  planted German developer line that makes it exit 1 naming the file (`35c26a0`).
- scripts, hooks: the two defects the first suite run in the public tree's own environment named in
  the commits above — a direct stdlib `tomllib` read where the tree's own parity rule asks for the
  3.10-capable shape, and a hook that called the New-file instrument even where no checkout carries it,
  which turned a clean commit into a refusal. Both now read the way the tree does it: the sanctioned
  try/except for the reader, and a named skip line for the leg that could not run. 32 tests across the
  two instruments' own suites pass (`ae95e10`).
- scripts: the same instrument judged a package by whichever lock edge its walk happened to pop first.
  `uv.lock` writes one requirement once per resolution environment, so a product dependency carried two
  edges with the same name and different markers; the seen-set dismissed the second as already asked, and
  on the py3.11 leg that meant `numpy` was reported as conditional and excused. The walk key now carries
  the marker, and marker evaluation takes a named PEP 508 environment, so a claim about a lock says the
  same thing on every interpreter while the shipped check still judges the one it is comparing. 24 tests
  pass on 3.11 and on 3.13, and dropping the marker from the key fails the new case by name (`a6e42bd`).
- frontend: the restored-session projection case failed under load and passed on a quiet machine.
  `chat/index.tsx:88` loads the message bubble lazily and the file's row-count waits pass on that
  Suspense skeleton, so the compared rows carried three empty `textContent` values from a cold
  transform. Measured 2026-11-23 with 30 competing vitest workers: four of four fail unwarmed with the
  line CI reported, four of four pass once the chunk is imported in `beforeAll`. The duplicate-key
  reading is refuted by the runner, which builds a fresh `knownKeys` set per children pass
  (`react-dom-client.development.js:6949`, `:6957`) and warns without a guard (`:28755`), so a repeated
  key warns every render. No assertion was loosened, and a planted constant key source turns five of the
  six cases red (`f082e09`).
- supply-chain: four register rationales cited a home directory on one development machine where they
  should have cited a measurement. Each now names what was run and when. The certifi and pip rows
  restate their numbers against this tree's own venv — `uv sync --frozen` holds certifi 2026.10.19 and
  writes it without pip (importlib.metadata, 2026-11-23) — which leaves the pip row standing on the
  hash-pinned 26.2.2 wheel its fence test already asserts (`a8323ea`).
- frontend: closing the settings sheet dropped the keyboard on the floor. Focus went to a
  `stableFocusTarget()` chosen by panel rather than back to the element that opened the sheet, and a
  hidden or detached invoker was accepted without a check. `useFocusReturn.ts` now carries
  `usableInvoker()` — rejecting a disconnected node, `document.body` and anything inside `[inert]` —
  `handFocusBack()` with a bounded rAF retry, and `invokerFromFocus()` recorded before the first
  focus; the recorder survives a panel switch because it is keyed on the invoker, not the panel.
  Five cases in `SettingsPanel.focusReturn.test.tsx` hold it: dropping `usableInvoker` fails three of
  them, ignoring the invoker fails one (`b93d5b8`).
- landing: the page installed and linked from a tag that has never existed. Every outward URL and
  both install commands were built from `__APP_VERSION__`, so a visitor got
  `raw.githubusercontent.com/…/v0.1.0/install.sh` — measured 404, as were
  `blob/v0.1.0/docs/SWITCHING.md`, `blob/v0.1.0/core/engine_config.py` and `v0.1.0/install.ps1`,
  while every `main` twin answered 200. The page now derives from the rolling ref the README and
  `install.sh` default to, states its version as a version rather than as a ref, and says what
  `--tag` does (`d957311`).
- scripts: `scripts/rss_profile_1000.py` could not run at all. It posts to an authority-spending
  route, and `LocalRequestGuardMiddleware` refuses a client naming neither a loopback Host nor a
  matching Origin — the `testserver` admission holds only while `PYTEST_CURRENT_TEST` is set, which a
  standalone run never has. The script sends the pair the guard already trusts; the guard is
  untouched. Two passes produced +0.0155 MB/turn each, a third on another day +0.0156 with a
  least-squares +0.0158 (136.4 MB → 152.0 MB over 1000 turns, 2000 messages, 5.8 ms/turn), no engine
  — the script stubs `server.routes.chat.react_loop` — on Darwin arm64 with Python 3.13.18, and
  `RSS_PROFILE_1000_MB_PER_TURN` now carries a number that run produced (`d313509`).
- hooks: the local type leg asked for `mypy` on `PATH` only, while the ruff leg reads the
  repository's own `.venv` first because `scripts/lint_policy.sh` counts its rules against one pinned
  release. On a machine with the venv populated and no PATH binary, every local verdict printed
  `SKIP mypy: not on PATH` for a check that had been available all along; the leg now resolves
  `.venv/bin/mypy` first, prints the version against the pin, and names both places it looked when it
  finds neither. Advisory stays advisory, as `lint.yml` has it (`fae0b95`).
- tools: `scripts/env_lock_agreement.py` reported `evaluated=True` from the moment `packaging`
  imported, so a lock whose markers the installed library cannot parse printed "markers evaluated"
  while every one of them had raised and the conservative fallback had answered in its place. The
  field is now a property over `asked`, `decided` and `errored` — an account that was never asked may
  not claim evaluation — and the report line distinguishes five states, with the counts in `--json`.
  Measured on this lock with CPython 3.13.18 (uv-managed, arm64) on macOS 26.6: 12 of 12 markers
  decided, the number the bool was hiding. Seven cases plant unreadable marker text rather than
  mocking the library (`0c27499`).
- tests: the advisory register's `state=fixed` rows were held by a fence that asked `uv.lock` whether
  the package *name* appears, while its own docstring promised "at or above the `fixed_in` the row
  names" — a resolve walking aiohttp back to the vulnerable 3.14.4 kept it green, and the npm sibling
  had the comparison all along. The comparison is now made, and a second fence asks
  `importlib.metadata.version()` for every fixed row: aiohttp 3.14.5, certifi 2026.10.19,
  multidict 6.9.1, each at or above its floor, nothing relaxed. A planted
  `aiohttp-3.14.4.dist-info` in front of `sys.path` is seen and refused, a planted lock at 3.14.4
  raises, and with the comparison disabled inside the guard the file reports 1 failed / 37 passed
  where the old fence stayed green (`0c27499`).
- tests: the retired vector store was kept out by reading files, which is a claim about text rather
  than about the environment that ships. Absence is now asked of the interpreter — `find_spec`, which
  answers without importing, which matters because that library starts a server on import — beside
  the distribution scan. Measured here: `find_spec("chromadb")` is `None`, 0 of 119 distributions
  carry the name; a planted real `chromadb/__init__.py` on `sys.path` is refused by path while every
  file fence in the same file stays green (`0c27499`).
- tests: the CPython floor was a string a test read out of a file, so the file stayed green on an
  interpreter that fails it. The running interpreter is now compared against `FIXED_FLOOR`. Measured
  twice on this machine, byte-identical file: Homebrew CPython 3.12.13, below the 3.12.16 floor,
  gives 8 failed / 2 passed with the new case refusing by name alongside the six tarfile cases and
  the SPKI case, while `test_the_pin_names_a_release...` passes on an interpreter that cannot pass
  its own tarfile cases and still trusts the eMudhra keys; CPython 3.13.18 gives 10 passed. A minor
  with no measured floor makes no claim, pinned as a decision instead of left silent (`0c27499`).
- docs: the release runbook described a job that has never run. It promised that "the publish job
  measures the released DMG and source archive, refuses a template hash that matches neither,
  renders the tap and bucket manifests, and then publishes them and the npm wrapper" —
  `.github/workflows/release.yml` defines four jobs (version guard, test gate, frontend gate,
  Tauri bundles) and uploads nothing to any registry, and no tap or bucket manifest exists in the
  tree. The section now names the steps that are there: the draft bundle build, the macOS seal
  audit that reports `state=adhoc-not-notarized` instead of claiming notarisation, and the
  updater-feed decision (`3a99e87`).
- docs: `DEMO_VIDEO.md` pointed at a README that never carried the film. The page called
  `docs/media/ephe-film-studio.mp4` "the README's film block"; no README names the file in any of
  the three languages, measured with `git grep -n` over `README.md`, `README.es.md` and
  `README.zh-CN.md`, and the same page listed a checksum for a render under `renders/` that no
  clone contains. Both are gone, and the two gallery pages describe what a reader can open today
  (`f2e0366`).
- scripts: `record_demo.py` stopped reading its own arguments as case names. `--help` reached the
  browser as a case and failed there with an error naming neither the flag nor the choices; now
  `.venv/bin/python scripts/record_demo.py --help` prints the usage and exits 0, and an unknown
  case prints it on stderr and exits 2, both measured on this machine (`f2e0366`).

- security: the glib `VariantStrIter` UB is answered with a patched copy instead of an ignore.
  `app/src-tauri/vendor/glib-0.18.5/` carries the one-line upstream fix (`variant_iter.rs:120` starts
  the iterator pointer at null) behind a `[patch.crates-io]` row, `scripts/lockfile_check.py` refuses a
  patched crate outside its allowlist, and `.github/advisories-ignore.txt` holds exactly one line:
  `GHSA-wrw7-89jp-8q8g` with the document that justifies it, its sha256, both owner rulings and a
  recheck date. Built and measured in Docker on both arches: `Checking glib v0.18.5
  (/tree/app/src-tauri/vendor/glib-0.18.5)` then `Finished dev profile` in 17.80 s and 51.58 s,
  rc=0 (`94f9f3c`).
- chat: a tool round answers to one name whichever renderer drew it. `tool-stream-rows` existed only in
  the expanded bubble, so the calm renderer's rounds were invisible to every reader of that name and
  QG2 counted two rows where three belong. The wrapper now appears with the round that carries a call,
  and a thought-only round stays unwrapped, which is the other half of the same rule (`a79d16b`).
- gates: `language_gate.py --staged` measured through the inventory instead of `measure()`, so a commit
  adding German developer prose passed the hook while the tree run flagged the identical lines. Both
  passes go through one `measure()` now, with cases naming the difference (`6bdb3f0`).

### Changed

- ci: the workflow auditor moved from 1.30.1 to 1.33.1 on a measured parity. The job's own invocation
  (`--offline --persona=auditor --min-severity=medium .github/workflows/`) exits 0 on both versions
  with no `warning[` or `error[` line, and run without the severity floor both print
  `19 findings: 4 informational, 15 low, 0 medium, 0 high` with the version banner as the only
  differing line in the two logs (measured 2026-11-24 with `uvx --from zizmor==<v>` on Darwin arm64).
  What the releases in between add costs this tree nothing: 1.32's two template-injection classes
  find no new hit and its root-aware input collection is inert because the step names
  `.github/workflows/` explicitly; 1.33's `dangerous-checkout` flags an opt-out no workflow here
  writes, with all 33 checkout steps SHA-pinned. The reason to take a two-day-old release is 1.33.1's
  crash fixes — a scanner that crashes is a red gate here — and the note that the hosted leg cannot
  confirm it yet, because the account is billing-locked (`fc4f912`).
- brand: the page title, the social card fields, the install manifest and the terminal's start
  banner open with the two lines the READMEs carry under the mark, instead of a descriptor built
  from the project name.
- dependencies: `cryptography` is declared. The first-party signature over the marketplace index is
  made and checked in `core/plugin_signing.py` and nowhere else, and the library arrived only through
  another package's requirements — one removal by that package away from a signing check that raises
  `ModuleNotFoundError` at import and is skipped instead of refused. Declared with the floor this
  tree's lock resolves and the signing tests pass against; nothing lower was run here, so nothing
  lower is claimed (`389b474`).
- model-provider: every request names the program that sent it — `User-Agent: Ephe/<version>` — and the
  one OpenAI-compatible endpoint that answers only the program shipping it is turned away in
  `ensure_provider_ready` before a connection is made, with the reason and the way out in the message.
  Reaching it had meant sending that program's User-Agent, a session header in its own format and two of
  its tool names. An endpoint that requires a borrowed identity is no integration: when the other side
  changes its mind the key is gone and no diagnostic says why. The setup screen stopped offering it as a
  quick pick and stopped linking its key page, so a first run cannot be sold a path ending in a refusal
  (`aa5edf0`, owner decision 2026-11-23).
- sandbox: the cell engine moved to wasmtime 51.0.0 and nine advisories in
  `.github/engine-advisories.txt` closed with it. Eight (RUSTSEC-2026-0566..0573) were fixed on
  crates.io in 50.0.2 and one (RUSTSEC-2026-0587) in 50.0.3, and PyPI published neither: that line
  carries only 50.0.1 there, so no 50.x lock could take a fix that exists upstream. The nine rows
  carried `state=accepted` with that block named in `blocked_by`; they read `state=fixed` now, and
  the uv override, `uv.lock`, the pip path in `install.sh` and the floor in
  `tests/test_cell_runtime_floor.py` moved together to `>=51.0.0,<52`. What a fuel unit costs was
  re-measured on both engines in the same hour on one arm64 box before the move: 14.6G fuel per
  guest CPU second on 51.0.0 against 14.3G on 50.0.1, boot 1,430,900,530 fuel against
  1,431,060,603, the 20,000,000,000 leash tripping identically and the guest answering on the next
  run. The caps in `core/cpython_cell.py` and `core/cpython_guest.manifest.json` are therefore the
  numbers this engine produced, with the older series kept beside them, and
  `docs/SANDBOX_EXECUTION.md` holds the table.

- chat: the thinking state says `ephe grübelt` in German and `ephe is flying` in English — the owner's
  own wording for the English surface, not a translation of the German, and no trailing ellipsis
  (`dada84e`).
- settings: `fire_bee` is no longer offered as a companion form. The three that remain are the folded
  paper moth, the golden spark with ghost eyes and a calm emblem. A stored `fire_bee` normalises to
  `paper_moth` on read; nothing on disk is rewritten (`6bdb3f0`).
- docs: `ephe plugin install` is documented with the flags its parser defines, including what each one
  refuses, and `docs/PLUGIN_EXPORT.md` now names the two plugin commands this build does not have
  instead of printing them beside the ones it has (`ef3abdf`, `7db99ba`, `00e0311`).
- tests: walkthrough captures are run output. The specs and `walkthrough-out.ts` no longer describe a
  dated set under `docs/media/` as tracked evidence, and every run writes to the scratch root unless
  `EPHE_WALKTHROUGH_OUT` names another (`b5e95e3`).
- gates: both copy ratchets moved down to what the tree measures — 723 German lines to 715, 379 prose
  tells to 368 — written by the instruments' own lowering pass, verified against the copies taken
  before it: no entry raised, none added (`00819f3`).

### Removed

- docs: the media tree carries only what is current for the brand, by owner decision. Twelve
  files left `docs/media/` — the ten WebP clips `docs/DEMOS.md` tabulated and the Film Studio
  film with its poster — taking the directory from 29 407 597 bytes in 15 files to 1 149 659
  bytes in 3: `paper-moth-master.png`, the mark every README renders and the social preview drawn
  from it. Nothing was recorded or generated in their place, `docs/screenshots/` and the first-run
  film under `app/public/onboarding/` are untouched, and `git grep -n` finds no reference to any
  deleted name (`f2e0366`). The bytes are out of the working tree, not out of the repository's
  history: a clone still carries them until the history is rewritten, which is an owner decision
  and has not been done.

- onboarding: the companion no one can choose is gone. Fourteen `bee-3d-*` files, the three
  fire-spirit SVGs, `FireSpirit.tsx`, `BeeEyelids.tsx` and `TypingIndicator.tsx` leave the tree;
  `app/public/onboarding` goes from 27 files and 19 266 939 bytes to 13 files and 970 523 bytes,
  and the guide figure is the paper moth (`b5e95e3`).
- brand: fourteen figure roles fell with the body they named — soot, fur, mou, ember, shine, the two
  head tones, two honey tones, an iris, a plate whose own comment said what it painted, and three
  glass-wing stops. Six remain, and each of those names the file that carries it (`b5e95e3`).
- scripts: the two sprite generators no caller had (`c1a6db4`).

## [0.1.0] - prepared 2026-11-21, not published

The version this tree carries — `pyproject.toml`, `app/package.json`,
`app/src-tauri/tauri.conf.json` and `app/src-tauri/Cargo.toml` all read 0.1.0 —
prepared on 2026-11-21 and never published. `git ls-remote --tags origin` returns
nothing and `https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.0/install.sh`
answers 404, both measured on 2026-11-24. The first tag arrives with the first run
of `scripts/release_cut.sh`, which needs the release environment's signing key pair
(`docs/RELEASE_POLICY.md`); the cut writes the release date it records into this header.
Every entry below names a surface this repository
contains, and the counts are taken from this tree on the date it was prepared.

### Added

- **Product server.** A FastAPI backend on `127.0.0.1:8765` (`run_server.py`, `server/`) with the `/api` routes, serving the built PWA. With no engine chosen it starts in setup mode and the chat stays closed: there is no silent engine default.
- **Installable web app.** The React PWA (`app/src`, built into `app/dist`) with a web manifest and service worker, opened by `ephe start --open` or at `http://127.0.0.1:8765`.
- **Desktop shell.** A Tauri shell around the same PWA (`app/src-tauri`); `ephe desktop` builds it and installs it to `/Applications`.
- **Terminal app and CLI.** The Textual TUI (`ui/`, launched by `ephe` or `ephe tui`) over the same backend, and the `ephe` command (`ephe_cli.py`): `configure`, `start`, `stop`, `status`, `doctor`, `update`, `desktop`, `bench`, headless `ephe code "<task>"` with stdin via `-` (reference: `docs/CLI.md`).
- **Explicit engine choice.** Ephe ships no weights and selects no model. A local Ollama model or any OpenAI-compatible endpoint is configured once through the Setup page or `ephe configure` into `~/.ephe/engine.json`. The key comes from the OS keychain, `EPHE_OPENAI_COMPAT_API_KEY`, or the owner-only `~/.ephe/engine.key`, and a stored key must carry the engine-binding sidecar or it is refused.
- **Approval profile and response modes.** The default strict profile asks before file edits and shell commands; the composer header chooses between Analyst, Architect, Operator and Creator (`docs/COMPOSER_MODES.md`). The session cell is disposable; saved artifacts and settings stay on disk.
- **Film Studio.** The agent's own cutting tools — `film_card`, `film_music`, `film_sound`, `film_clip`, `film_status` (`core/tools/film_tools.py`) — and an ffmpeg cut into an mp4 (`core/film_cut.py`), with a local voice rung for speech (`docs/VOICE.md`). Its provenance page is `docs/DEMO_VIDEO.md`.
- **Phone pairing over the LAN.** `ephe start --lan --open`, Settings → Mobile → Connect mobile, and the QR endpoint `server/routes/mobile.py` (`/api/mobile/qr`); public access is a separate opt-in (`docs/MOBILE.md`).
- **Plugin surface.** Seventeen first-party bundles under `plugins/` with `ephe-plugin.json` manifests and sha256 hashing: ten first-party plugins and seven capability presets, the `countdown` widget among the ten doubling as the reference surface. One hundred fifty-three golden prompt cases across the seventeen bundles back the `ephe bench` verify gate. A plugin tool that carries its own code runs in a separate process with no Ephe credential (`docs/PLUGINS.md`).
- **Plugin Store and a bundled third-party pack.** The Discover shelf (`server/routes/discover.py`) offers the first-party entries and the bundled Superpowers skill pack (MIT, `marketplace/sources/superpowers`); an install lands in the user's own profile only after a confirmation.
- **Skills and personas.** Built-in skill packs (`skills/`, `docs/SKILLS.md`) and versioned persona packs behind `~/.ephe/persona.md` (`docs/PERSONA_PACKS.md`).
- **Long-term memory.** The Kepta store with embeddings and its re-embed path (`core/memory_kepta*.py`, `docs/MEMORY.md`); the memory plugin saves, recalls and deletes only after confirmation.
- **Opt-in web research.** The `web-research` plugin and the `web_research` kernel tool keep an evidence store with direct URLs, dates and quoted passages (`core/web_intake/`, bounds in `policy.py`, operator model in `docs/WEB_INTAKE.md`); browser automation (`plugins/browser-use`) runs behind the approval gate.
- **Workbench artifacts.** Files and charts from a turn land in the artifact library to open, download or adopt; a recorded number names the engine that produced it (`docs/OPERATIONS.md`).
- **One-command install and Docker.** `install.sh` and `install.ps1` are the product install paths; `--tag`/`-Ref` checks a release tag out detached, and the uv bootstrap is hash-pinned. `Dockerfile` and `docker-compose.yml` publish both ports on the host's loopback only and name no engine (`docs/INSTALL_OPTIONS.md`). The npm, Homebrew and Scoop channels are retired and their repositories deleted.
- **Update paths.** Desktop app, PWA and terminal each update from their own channel; the release channel checks GitHub's newest release and the commit channel is opt-in (`docs/UPDATES.md`).
- **Offline evaluation harness.** The `evals/` harnesses with their run receipts, `ephe bench` as a structural verify gate that needs no engine, why Ephe measures its own harness is `docs/benchmark-mapping.md`. No board surface and no published pass-rate figures ship with this release.
- **Voice.** The offline Piper loop and a configurable second local voice rung (`docs/VOICE.md`).
- **Image generation.** `plugins/image-studio` calls the image endpoint the user names and writes the file; local image generation options are in `docs/LOCAL_IMAGE_ENGINE.md`. MCP servers are added by hand in Settings → MCP servers.
- **Security stance.** Loopback binding by default, zero telemetry in the tree, per-segment shell whitelisting, path guard with refused directories, plugin confinement with mount trust classes, and an opt-in OS sandbox (`sandbox-exec` on macOS, `bwrap` on Linux): `SECURITY.md`, `docs/SECURITY_AND_PRIVACY.md`, `docs/SANDBOX_EXECUTION.md`.
- **English tree, German product surface.** Developer prose is English throughout; German lives in `app/src/locales/de.json` and German-targeted content (`docs/AI_CONTRIBUTION_POLICY.md`).
- **Gates in the repository.** CI and contributors run the same files: the language ratchet, the prose ratchet, the architecture check, the supply-chain audit and the release gates (`scripts/`, `.github/workflows`).
- **Licence.** Business Source License 1.1, source-available, each version falling to Apache 2.0 four years after its first public release (`LICENSE`, `COMMERCIAL.md`).
