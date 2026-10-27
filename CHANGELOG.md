# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

The 0.1.12 changes are named below (`1f823cb`, `3374a70`, `105700d`, `8a5d3a6`,
`8935b9f`): a settings write merges instead of replacing a section and refuses
unknown keys, the co-pilot reads a workspace and can be taught a command shape,
git runs inside the shell sandbox, the installer ships the cell runtime, and
/api/health names the commit the backend runs.
The 0.1.11 changes are named below (`337903e`, `0f02bc6`, `043ee1e`, `976ee78`,
`2aa10a5`, `fef5644`, `38923b9`, `c4550c2`, `5af85c2`, `fb8593e`, `721fe91`,
`3902468`, `ede0927`, `3ad5cd6`, `0968644`).
The 0.1.10 changes are named below (`f16963e`, `278d717`, `7c468f3`,
`e629e6c`, `afadd56`, `0d251e2`, `c9f0591`, `fb85bb9`, `9242ba4`, `38a9640`).
The 0.1.8 fixes are named below (`999d75c`, `ece2522`, `6dce8df`, `c2f49ab`,
and the packaging gate's `6d0d7ba`).
The 0.1.7 changes are on main as `a6c97fc`, `8f86bfe`, `f4415e9`, `6869f8c`,
`7f793d0` and `5d67f19`; the tag names the same work as `a02adcf`, `b831014`,
`36640f5` and `8e0b7a1`, because v0.1.7 was cut from a rebased copy of main.
The six 0.1.6 fixes are folded into their own section (`408d1e2`, `be4f90f`,
`4c85103`, `c8476be`, `a7930fa`, `86d933b`).

## [0.1.11] - 2026-10-27

### Added
- The setup screen repairs a stored key that belongs to another engine: it
  names the active engine, the engine the key is bound to and where the key
  came from, and offers keep, re-enter the key, pick another engine or cancel.
  A loopback start enters setup mode instead of exiting, and chat answers 409
  until the binding is rewritten (`337903e`, `0f02bc6`).
- The desktop bundle declares the six privacy purposes it can request
  (microphone, Desktop, Documents, Downloads, removable and network volumes),
  and `docs/TCC.md` records the signing identity, the TCC diagnosis and the
  rebuild test (`043ee1e`).
- A boundary test keeps `core/` and `server/` free of AppKit, Cocoa,
  Foundation, Quartz, WebKit, objc and pyobjc imports and dependencies
  (`e0ce875`, `a9392e9`).
- The README contract runs as a CI Gates step and as a dedicated offline job,
  so a stale install tag or a dropped section fails a check (`fef5644`).
- The desktop shell carries the menu bar macOS users look for: Ephe, File, Edit,
  View, Window and Help, with New Session (⌘N), Settings… (⌘,), Check for
  Updates…, Close Window (⌘W), Quit Ephe (⌘Q) and the standard Edit entries. The
  tray menu and the bar share one route table, and the surface answers Settings
  and Documentation (`721fe91`).
- The companion works as a co-pilot over five surface targets: a waiting tool
  approval, an open question, a context past 90 %, files a turn just wrote, and
  a failed call. Three modes choose how much it does (`perch`, `scout`,
  `copilot`), a visible 2.5 s countdown precedes every act it takes by itself,
  Escape or Cancel stops it, and the last ten acts stay readable in its popover
  with the reason each one was taken. Risky commands are never approved for the
  user, and the crawl costs no engine tokens (`3902468`).
- The companion can be summoned from anywhere: the header switch, the
  `/companion` command and ⌘⇧C flip the same register key (`3902468`).

### Fixed
- A key file replaced without re-binding no longer offers "keep the key": that
  repair requires a key whose fingerprint matches `engine.key.binding.json`
  (`976ee78`).
- The e2e boot set closes at the panel-ready boundary, so a polling tick that
  fires while a slow runner reads the DOM no longer counts as a boot request
  (`04048ba`).
- ⌘W and the red button hide the main window instead of destroying it, so a Dock
  click or the tray icon can bring it back; a quit that ends through the run loop
  now stops `caffeinate` too (`721fe91`).
- The timing report reads the workflow matrix before judging a leg, so a dropped
  Python version is named by the offline test that guards it rather than by the
  nightly report that noticed it first (`5af85c2`).
- A co-pilot countdown the user stopped stays stopped: the dismissal is recorded
  against the prompt token it was counting for, so a re-render of the same
  waiting approval cannot offer the act again, while the next run of the same
  command — a new token — is still served (`ede0927`).
- Only `run_shell` can earn an automatic approval now, and a command that names
  an absolute or home path, expands `${VAR}`, or passes a writing or
  reconfiguring flag to an allowlisted program (`--output`, `--config`, `-c`,
  `-o`, `--rootdir`, `--override-ini`) stays a warning (`ede0927`).
- The setup repair becomes a target the companion can actually see: the setup
  screen announces the card while it is up, and pointing at a repair the chat
  cannot show marks the setup intent and takes the user to the screen that can
  (`ede0927`).
- The way out names the way back in: `uninstall.sh` closed with a reinstall URL
  pinned to `v0.1.3`, eight releases behind the product it had just removed, and
  now names the tag this tree ships — the same answer `scripts/readme_check.py`
  gives, so a release bump that forgets the script fails a test (`0968644`).
- A mobile host that names another protocol is refused instead of fetched:
  `EPHE_MOBILE_HOST=ftp://…` or `gopher://…` reached the LAN probe's
  `urlopen` with that scheme, and a scheme without an authority came back as a
  malformed http URL. Only `http` and `https` with a host answer now
  (`0968644`).
- The memory ranking's full-text leg binds its row limit as a parameter rather
  than writing the number into the SQL (`0968644`).

### Changed
- The header perch carries the co-pilot as the composer does — mode row,
  finding, countdown, cancel and receipts — and the loop runs in whichever
  surface the behavior chose, so a prompt is never approved twice and the
  dormant surface no longer sweeps the highlight the live one set (`ede0927`,
  `3ad5cd6`).
- CI: PR-only `cancel-in-progress` across the dual-trigger workflows, bounded
  `verify.yml` timeouts, and a concurrency group on `bench-trend.yml`
  (`2aa10a5`).
- The READMEs and the start docs name `v0.1.11`, drop the stale `v0.1.3`
  prose, document the engine-key binding sidecar, and name the tested Node
  runtime (`38923b9`).
- The README contract reads every release tag named in prose, so a stale
  `v0.1.x` fails the same way a stale install URL does (`c4550c2`).
- CI installs Python 3.13.18 where the interpreter comes from `actions/setup-python`,
  while the matrix keeps naming the leg `py3.13` so the required check names and
  the timing budgets stay what they are (`fb8593e`).
- A fresh install starts without the companion (`appearance.companion_enabled`
  defaults to false), and when it is summoned it parks in the right outer gutter
  instead of leaning into the reading column while the engine writes
  (`3902468`).

## [0.1.10] - 2026-10-26

### Added
- An attachment picked through the desktop's native dialog arrives as a data
  URL or text and never as a path, so the composer shows its thumbnail, its
  name and its lightbox again (`0d251e2`, `c9f0591`).
- A release gate refuses a tag that does not sit on `main`: every `v*` tag is
  checked for ancestry against the trunk, and the pre-publication tags that
  cannot carry one are recorded in a baseline (`e629e6c`, `afadd56`,
  `fb85bb9`).
- `docs/BACKEND_PATH.md` names the backend root this machine configured, the
  `current` symlink and the versioned sidecar that replaces it (`60ce39e`).

### Fixed
- The desktop version check waits for a cold backend instead of reading
  "unknown" from its first empty answer, and the refresh runs off the UI thread
  with an 8 s deadline (`f16963e`, `278d717`).
- The e2e boot set counts the health heartbeat once, so a late poll no longer
  reads as a second boot request (`9242ba4`).
- The provenance gate answers "cannot decide" in a shallow checkout instead of
  reading older tags as diverged, and the release test gate fetches the full
  history (`38a9640`). The v0.1.9 run failed on exactly that shallow read.

### Changed
- The Rust shell job bounds each apt acquire and retries the install once,
  instead of hanging for up to 19 minutes on an unresponsive mirror (`7c468f3`).

## [0.1.9] - 2026-10-26

Tagged on `main` as `4c76d46` and never published: its release test gate
checked out a shallow clone, read every older tag as diverged and failed the
suite, so no artifact was served. The work above ships in 0.1.10 with that gate
fixed (`38a9640`).

## [0.1.8] - 2026-10-26

### Fixed
- After the desktop app itself is replaced, the shell compares its own version
  with the backend's, updates the backend along the root this machine
  configured, and re-reads it. A version that still differs is named with both
  figures, so the two halves cannot sit on different releases unnoticed
  (`999d75c`, `ece2522`).
- A `tool_done` frame that names no call id keeps its result and its reader
  reason, so a failed tool shows its reason line again (`c2f49ab`).

## [0.1.7] - 2026-10-26

### Fixed
- `fetch_url` returns the page text and no longer answers a prompt through a
  local model, so a hosted engine no longer fails a fetch behind a card that
  said Completed (`a02adcf`).
- A tool call the backend marks failed is shown as Failed with its reason; an
  approval refusal keeps `denied`, and the card no longer turns one into the
  other (`b831014`).
- Tool names and statuses wrap instead of clipping, and the family hint lives
  in the card body instead of a hover popup over it (`b831014`).
- An attached image shows a thumbnail that opens a lightbox; text and binary
  files show their name and size, removal names the file, and a file that is
  being read or cannot be read says so (`b831014`).
- Fetch failures and refusals carry reader codes in both languages, and the
  English line of every code is the engine-facing entry (`36640f5`).

### Added
- `docs/WORKING_BACKWARDS.md`, `docs/COMPETITIVE_MATRIX.md` and
  `docs/AGENTS_PROPOSAL.md` (`8e0b7a1`).

### Security
- The `pnpm` pin moves to 11.11.0 (`GHSA-vx52-2968-3vc6` covers 11.10.0). The
  lockfile is byte-identical after `pnpm install --frozen-lockfile`, the audit
  answers "No known vulnerabilities found", and `lockfile_check.py` passes.
- The advisory note for `zip` now states what was measured: the macOS and Linux
  targets do not carry the crate, the Windows target does, and no Windows asset
  has been published. The three RustSec lines and their recheck date stand.

## [0.1.6] - 2026-10-25

### Fixed
- On macOS the header menu no longer offers minimize and maximize over the
  native traffic lights, so the window has exactly one button group; the
  Windows and Linux menus are unchanged (`408d1e2`).
- A restored transcript with no messages no longer appears as a sidebar row
  (`be4f90f`).
- A stored assistant row that opens with the working-memory preamble is shown
  as context; it can no longer read as an answer (`4c85103`).
- The side conversation has one name in each language: `Seitengespräch` in
  German, `Side conversation` in English (`c8476be`).
- The setup page announces progress in a status region and failures in an
  alert region; the tools page labels its fields visibly and announces results.
  Both pages carry axe checks (`a7930fa`).
- A skill that can write files now declares a read tool: `api-tester` gains
  `read_file`, and a contract test holds every skill to the rule (`86d933b`).

## [0.1.5] - 2026-10-25

### Fixed
- A turn whose stream loses its terminal frame keeps its partial answer, names
  a stable reason code, and the next message goes out without a reload.
- The artifact route serves the screenshots the product writes under
  `~/.ephe/sessions/images`; a file card that cannot render names the concrete
  cause and states it once.
- The run ledger writes one terminal line per turn, carrying the failure class
  when the turn failed.
- The "Set up engine" action no longer appears on a turn that failed after the
  engine answered; the composer chip already offers setup when no engine is
  configured.

All four in `cbd5e7e`.

## [0.1.4] - 2026-10-25

### Added
- Chat artifacts render inline: images with a lightbox, PDF in a frame, video and
  audio with controls, tables and Mermaid fences, and a file card for the rest.
  A missing image now says so and offers a retry instead of leaving alt text.
- A running turn reports its tool, round and search query, with a heartbeat;
  the search call is bounded to four calls or 60 s and ends with an answer.
- The marketplace card carries the on/off switch. A package that needs consent
  shows one inline consent block instead of a modal.
- A remote image in an answer is fetched through the guarded proxy and stored.

### Security
- The artifact route refuses deny roots and credential-shaped names, decides
  inline media from an allowlist and supports range requests.
- Skill archive paths go through `path_guard.within` instead of a string prefix.

### Fixed
- The hosted macOS runner's uv interpreter is recognised under the Seatbelt
  profile, and `ephe_cli.py` reaches its coverage floor; the PR gate no longer
  skips the required macOS check.
- A failed search reaches the engine fenced as untrusted data like a successful
  one, and an all-refused search is reported as a failure instead of "No results
  found".
- The cask, scoop and npm manifests name 0.1.4, so the release gate judges them
  against the release it ships.
- `generate_image` and `take_screenshot` say when they produced nothing, so the
  answer cannot claim an image the turn never registered.

### Removed
- `plugin_store.install_package` and its tests; the live path is
  `plugin_install._safe_extract`.

### Dependencies
- lucide-react 1.60, framer-motion 14.5.

## [0.1.3] - 2026-10-22

The marketplace and its Extension Center, on top of the 0.1.2 security and
interpreter fixes.

### Added
- Marketplace v2: a canonical bundled index of the first-party plugins, local
  and signed HTTPS sources, exact-version resolution, compatibility and
  revocation checks, and a plan that pins version, hash, trust and the
  permission delta before anything is downloaded.
- Install, update, rollback and remove with a one-slot previous version. An
  update keeps the switch state, a rollback restores the previous version and
  its state, and enabled dependents block a removal.
- The Extension Center: Installed, Discover and Updates views, source
  management, signed/unsigned/bundled trust states, plugin detail, and an
  explicit review for an unsigned artifact or a permission-adding update.
- Local Agent Center and Agent Teams: per-agent model, read-only tool grants,
  instructions and limits; one leader with up to four members, four
  orchestration modes, budgets and cancellation.
- Route-backed settings (`#/settings/<section>`) and desktop window-state
  persistence.

### Security
- A remote index needs a trusted signature, a remote artifact needs a signed
  directory, an unsigned local artifact needs explicit trust, and a revoked
  version is refused at install, update and enable time.
- Remote index and artifact fetches pin the checked public address, keep the
  host in the TLS SNI, refuse redirects and trust no proxy environment.
- Closed local web-surface issues: foreign-origin terminal access, file-route
  access to protected credential paths, child-process credential inheritance,
  and lifecycle state write failures.

## [0.1.2] - 2026-10-22

A security and interpreter release.

### Changed
- Python 3.10 is no longer supported; `requires-python` is `>=3.11`.
- wasmtime moves to 48.0.0.

### Added
- The plugin platform: registry, lifecycle state machine, switch contract,
  signature, package, dependency, secret, network-guard and audit gates.
- The CPython WASI guest and the cell runtime with fuel, memory, disk and
  network limits.

### Security
- Dependency and TLS updates close the open audit advisories for this line.
- A signed artifact older than the installed one is refused instead of
  replacing it.
- The interactive terminal, file routes, child-process environment and plugin
  state writes were hardened.

Earlier release notes are available in the GitHub release history.
