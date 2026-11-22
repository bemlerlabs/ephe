# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

Nothing yet. Changes land here between releases and move down with the next tag.

### Added

- plugins: Bring the two real studio bundles into the public tree (`6ce3c6d`)

### Fixed

- Make ChatLayout slash tests settle the streamChat mock (`61b2063`)
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
