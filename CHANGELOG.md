# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

### Added
- A stream that closes now writes one content-free `stream_closed` ledger line
  with the close code, last frame type, elapsed and heartbeat ages and the
  provider; the client writes the matching diagnostic with the turn id, so the
  two can be joined (`13780f3`).
- The marketplace catalogs merge into one index with a field contract
  (publisher, licence, version, SHA-256, source, content), an alias map and a
  verification record; the third-party Superpowers pack is complete with its
  upstream MIT licence, German copy and an icon (`2b48a3f`).
- A local decision layer reads a decision's distribution from one decoder
  position, off by default, with a 60-case measurement harness (`f2fcea1`).

### Changed
- `ephe update --json` writes one document and sends the children's prose to
  stderr; `ephe plugin list --json` is new; the empty-session hint names a
  command the parser accepts (`a0a0e90`).

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
