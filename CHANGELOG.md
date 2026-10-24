# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

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
