# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

The desktop version-parity check is `7ae19bd`; it rides the next patch.
The 0.1.7 fixes are named below (`a02adcf`, `b831014`, `36640f5`, `8e0b7a1`).
The six 0.1.6 fixes are folded into their own section (`408d1e2`, `be4f90f`,
`4c85103`, `c8476be`, `a7930fa`, `86d933b`).

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
