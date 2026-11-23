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
- scripts: `env_lock_agreement.py` compares the environment that is running against the lock it is
  pointed at and refuses the difference. It found what no leg could see: the interpreter every gate and
  every suite run on this machine uses had `wasmtime` 47.0.1 installed while uv.lock pins 50.0.1,
  forty-three crates.io advisories behind and including the sandbox escape the engine floor exists for,
  while the advisory legs scored the pinned version and the wheel's own database record read clean. The
  suite's own tools (`dev`, `bench`) are reported in a column that prints without refusing; every other
  extra counts as product, so an unclassified one is held to the lock. 22 tests cover it, one of them a
  planted deviation that has to be caught (`658cd90`).

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

### Changed

- brand: the page title, the social card fields, the install manifest and the terminal's start
  banner open with the two lines the READMEs carry under the mark, instead of a descriptor built
  from the project name.
- dependencies: `cryptography` is declared. The first-party signature over the marketplace index is
  made and checked in `core/plugin_signing.py` and nowhere else, and the library arrived only through
  another package's requirements — one removal by that package away from a signing check that raises
  `ModuleNotFoundError` at import and is skipped instead of refused. Declared with the floor this
  tree's lock resolves and the signing tests pass against; nothing lower was run here, so nothing
  lower is claimed (`389b474`).
## [0.1.0] - 2026-11-21

The first public release. Every entry below names a surface this repository
contains, and the counts are taken from this tree on the release date.

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
