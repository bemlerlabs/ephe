<p align="center"><a href="README.zh-CN.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a></p>

<div align="center">

<img src="docs/media/ephe-bee-512.png" alt="Ephe — the fire-spirit bee" width="88">

# Ephe

**Ephe is a local-first agentic workspace that runs on your machine — an ephemeral SI agent you drive from a CLI (`ephe tui`) or a desktop app (`ephe start`) over one Python backend. You pick the engine: local Ollama, a remote Ollama, or any OpenAI-compatible endpoint, and there is no silent default. Optional online/API features are always opt-in.**

<img src="docs/screenshots/hero-banner.png" alt="Ephe's chat workbench in the forest register: an assistant reading pane with a completed tool row nested inside it as a control pane, the sidebar's task list, and the composer above the status bar" width="100%">

One command installs the app; the engine is chosen inside it afterwards, from local Ollama, a remote Ollama, or an OpenAI-compatible endpoint such as a DGX Spark. The installer does not install Ollama and does not pull a model. Until an engine is chosen the app says so and waits, with no hidden fallback; once it is chosen, a fully offline local setup and a remote high-throughput setup run as peers. Custom Ollama servers, public mobile access, web research, text-to-speech services, and OpenAI-compatible APIs are optional opt-in paths.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org) [![Engine chosen in-app](https://img.shields.io/badge/Engine-chosen%20in%20app-8250df?style=for-the-badge)](https://ollama.com)
[![License](https://img.shields.io/badge/License-BUSL%201.1-2d6a4f?style=for-the-badge)](LICENSE) [![Tests](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml) [![Frontend Build](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml)
[![Lang-中文](https://img.shields.io/badge/Lang-中文-red?style=for-the-badge)](README.zh-CN.md) [![Lang-Español](https://img.shields.io/badge/Lang-Español-orange?style=for-the-badge)](README.es.md)

</div>

<div align="center">

**Stars help other people find Ephe.**

</div>

<details>
<summary>Contents</summary>

- [Quick Start](#-quick-start)
- [The First Two Minutes](#the-first-two-minutes)
- [What You Can Do Next](#what-you-can-do-next)
- [What Ephe Is, And What It Is Not](#what-ephe-is-and-what-it-is-not)
- [The Desktop Shell](#the-desktop-shell)
- [Getting Help](#getting-help)
- [License](#license)

- [Quickstart](docs/QUICKSTART.md) · [At a Glance](docs/AT_A_GLANCE.md) · [Feature Status](docs/FEATURE_STATUS.md) · [Skills](docs/SKILLS.md) · [Plugins](docs/PLUGINS_OVERVIEW.md) · [Benchmarks](docs/BENCHMARKS.md) · [Demos](docs/DEMOS.md)
- [Install Options](docs/INSTALL_OPTIONS.md) · [CLI](docs/CLI.md) · [Architecture](docs/ARCHITECTURE.md) · [Development](docs/DEVELOPMENT.md) · [Mobile](docs/MOBILE.md) · [Telegram](docs/TELEGRAM.md) · [Security And Privacy](docs/SECURITY_AND_PRIVACY.md) · [Docs index](docs/README.md)

</details>

## ⚡ Quick Start

Install with the repository's own installer — the route that exists today:

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

The app is not notarized yet: on macOS the first start asks once, and you open it from
System Settings → Privacy & Security → Still Open.

A package-manager route (`@ephemora/ephe` on npm, a Homebrew cask, a Scoop manifest)
arrives once a release publishes it automatically; until then the command above is the
one that works; the unscoped name on npm is taken by an unrelated package, so ours carries the scope.

The one-liner fetches `./install.sh` from the published repository and runs it. To read the script before it runs, take the same script from a checkout:

```bash
git clone https://github.com/bemlerlabs/ephe.git && cd ephe && ./install.sh
```

Where the installer puts things, what it checks, and how the uv download is hashed: [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md#what-the-installer-does). A step-by-step walkthrough of the install, both ways to choose an engine, and where an API key actually comes from: [docs/FIRST_RUN.md](docs/FIRST_RUN.md).

### Windows (PowerShell)

```powershell
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.ps1 -o install.ps1; powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1   # from a local checkout instead
```

Install mode is selectable: `--cli` (TUI/Textual only, minimal dependencies) or `--desktop`/`--gui` (default, PWA plus gui/voice). Without a flag the installer asks interactively.

The way out ships with the checkout: `./uninstall.sh --dry-run` prints the plan and changes nothing, `./uninstall.sh --keep-data` removes the checkout while `~/.ephe` stays. Docker, the installer's environment variables, and the supply-chain checks are in [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md) and [docs/INSTALL.md](docs/INSTALL.md).

### System Requirements

| Component | Minimum | Notes |
|---|---|---|
| OS | macOS 13+, Ubuntu 22+, or Windows with the PowerShell path | a current browser |
| Python | 3.10 or newer | `.python-version` pins 3.13 for this checkout |
| RAM | 8 GB free for a small local tag | 16 GB+ for a local 12B-class tag; a remote endpoint needs none |
| Storage | 12 GB free | 20 GB+ recommended |

The full table is in [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md#system-requirements).

### Command map

```bash
ephe start --open          # local web app + browser (port 8765)
ephe tui                   # terminal UI (Textual) on the configured engine
ephe desktop               # build the Tauri shell, install to /Applications, open it
ephe configure             # choose the engine once (saved to ~/.ephe/engine.json)
ephe doctor                # setup check; `ephe doctor --fix` for safe local repairs
ephe update                # repo pull + dependencies + model
ephe serve                 # OpenAI-compatible engine (/v1/chat/completions)
ephe session list|new|switch|rm|rename
```

Every flag, the approval gates, and the exit codes are in [docs/CLI.md](docs/CLI.md).

## The First Two Minutes

From a checkout, five steps to a working session. Each numbered step is one command, and the block under it is what this machine printed while the section was written; long absolute paths are elided as `…`.

1. **Install.** `./install.sh` prepares Python, builds the PWA, creates the data folders under
   `~/.ephe/`, and starts the local server on `http://127.0.0.1:8765`. Add `--dry-run` to print that
   plan and touch nothing:

   ```text
   ▶ Checking the system
     ✓ Darwin supported
     ✓ Disk space OK
   ▶ Checking Python 3.10+
     ✓ 3.12.15 found
   ▶ Setting up the local Python environment
     DRY-RUN: pnpm --dir …/app install --frozen-lockfile
     DRY-RUN: pnpm --dir …/app run build
     ✓ PWA built → app/dist
   Setup complete.
   ```

   The same script is the one-liner in [Quick Start](#-quick-start).

2. **Choose the engine, once.** `ephe configure` saves the choice to `~/.ephe/engine.json`. Until
   something is saved there, the app and `ephe start` refuse to start and name both ways out:

   ```text
   $ ephe start
   Error: No engine configured.
     Fix: Run `ephe configure` and pick your engine (saved to ~/.ephe/engine.json), or set it
     explicitly via env: EPHE_MODEL_PROVIDER=local_ollama|custom_ollama|openai_compatible ...
   ```

3. **Check it.** `ephe doctor` prints one line per check and exits non-zero while anything is
   missing:

   ```text
   OK      Python - 3.13.5
   OK      Engine openai_compatible - deepseek-v4-pro @ https://api.deepseek.com/v1 — engine up
   OK      Ephe server - http://127.0.0.1:8765
   OK      skills-lock.json - 51 packs match
   MISSING Voice (TTS) - piper not found — setup: 'brew install piper' ...
   Summary: 10/12 checks OK
   ```

4. **Start it.** `ephe start --open` for the app; `ephe tui` for the terminal. `ephe start --lan
   --open` also exposes it on your network for phone pairing.

5. **Ask.** This is the call the app makes, against the engine step 2 saved — the request below
   returned in 4.7 s:

   ```text
   $ curl -s -X POST http://127.0.0.1:8765/api/chat -H 'Content-Type: application/json' \
       -d '{"message":"Answer in one short sentence: what is 17 * 3?","mode":"ask"}'
   {"response": "17 × 3 is **51**.", "model": "deepseek-v4-pro"}
   ```

Screenshots and clips live in `docs/screenshots/` (the banner above) and `docs/media/` (the clips under
[Demos](docs/DEMOS.md)).

## What You Can Do Next

Five things this product does that a chat window does not.

1. **Pick the engine and watch it refuse to guess.** `ephe configure` writes the choice once; a
   machine with no choice made fails closed with the way out instead of falling back to a hidden
   default ([step 2 above](#the-first-two-minutes)).
2. **Watch a fleet work in parallel worktrees.** `ephe agents` prints every live run with its state
   and age, then `ephe changes <workspace>` prints what each run built — path by path, with the
   digest of each diff:

   ```text
   $ ephe agents
   1 live workspace (register ~/.ephe/workspaces/register.json)
   cb9f70d9  probe-n1  dirty  age 8s
   $ ephe changes cb9f70d9
   1 change set for /…/workspaces/cb9f70d9 (newest first)
   cs-20261014T141323Z-b519db23  draft  1 file  2026-10-14T14:13:23  probe: one file …
       create  docs/n1-probe.txt  sha256:8031de4f05e6
   ```

3. **Put a review gate between an agent and your trunk.** `ephe review` files a verdict; approving
   your own work is refused, and so is publishing without one:

   ```text
   $ ephe review cs-20261014T141323Z-b519db23 approve --reviewer probe-n1 --reason "docs/n1-probe.txt:1:the author cannot approve its own set"
   Error: probe-n1 authored cs-20261014T141323Z-b519db23 and cannot approve it
     Fix: nothing was recorded: a verdict needs a reason inside the change set and a reviewer other than its author
   $ ephe publish cs-20261014T141344Z-f40dcdf2 --dry-run
   Error: cs-20261014T141344Z-f40dcdf2 may not publish: no verdict is recorded
     Fix: ephe review cs-20261014T141344Z-f40dcdf2 approve --reviewer <reviewer> --reason <path:line:why>
   ```

   With a verdict from a reviewer who is not the author, the same verb records it and moves the set
   to `review`; `ephe publish --target <branch>` then lands every file of the set or none.
4. **Bound the session store.** `ephe prune` reports what it would free and changes nothing; the
   same verb with `--apply` does it:

   ```text
   $ ephe prune
   Session store: ~/.ephe/sessions
   Holds 8942 files (3.9 MB): 2666 tasks a list shows, 6276 files no list reaches.
   Dry run: would delete 2079 files, freeing 2.1 MB. Nothing was changed — repeat with --apply.
   ```

5. **Use it from your phone.** Start with `ephe start --lan --open`, open **Settings → Mobile** in
   the app and follow the three steps the panel shows: Click **Connect mobile**, scan the QR
   code with a phone on the same network, then chat from the mobile PWA. Public access is a separate
   opt-in; the walkthrough is in [docs/MOBILE.md](docs/MOBILE.md).

## What Ephe Is, And What It Is Not

Ephe is a local web app and Python backend for a personal SI agent — SI here means *super-intelligence*. The unit of work is the cell: it runs on your machine, every tool call and approval decision is written to the record, and the cell is destroyed when the session ends. Nothing is kept unless you keep it:

| Capability | Default behavior | Network behavior |
|---|---|---|
| Chat with the chosen model | Chosen by you in the app — no silent default | No internet required for a local engine once its model is installed |
| Image understanding / OCR | Chosen by you in the app (local Ollama works offline) | No internet required once model is installed |
| Files, PDFs, profile, memory | Local disk | No internet required |
| QR phone access | Local network | Public mobile tunnel is Optional Online |
| Shell and desktop actions | Approval required | Local only unless a tool explicitly uses the internet |
| `/research` | Disabled until confirmed | Optional Online Web search |
| TTS service integrations | Optional | Internet, provider-dependent — [Piper TTS](docs/VOICE.md) locally when it is installed; the cloud service is opt-in |
| Custom Ollama server | Advanced Opt-in | Localhost or LAN endpoint |
| OpenAI-compatible API | Advanced Opt-in | Your configured API provider |
| Sandboxed code execution (`run_sandboxed_code`) | Advanced Opt-in | `pip install 'ephe[sandbox]'` — local WASI sandbox (Ephemora Cell), no network, no host access |

Offline-first here means the core product works locally once you have picked an engine in the app (Ollama or OpenAI-compatible), and that a local engine is a peer of the remote ones. It does not mean every optional integration is offline, and it does not mean a silently pre-selected engine.

The engine choice is the boundary that decides what Ephe is and is not. The default build, with a chosen engine:

- **No cloud service, no account.** The local path runs on your machine and asks for no sign-up; there is no telemetry endpoint: the one call that leaves the machine is the update check, which asks GitHub for the newest release.
- **No model and no model bundle.** Ephe ships no weights. The installer detects a running Ollama and stops there; it never installs Ollama and never pulls a tag. Without a chosen engine the app waits and names both ways out.
- **No multi-user server.** One instance serves one person on one machine.
- **No app-store app.** The phone surface is the same PWA over your network; there is no iOS or Android build.
- **No crawler by default.** `/research`, remote engines, public mobile access, and external TTS are opt-in paths; an offline engine is enough for everything else.
- **No second native app.** The Tauri desktop shell is a thin wrapper around the PWA; the `docs/` v2 experiments are not the shipping surface.

## The Desktop Shell

`ephe desktop` builds the Tauri shell, installs it to `/Applications`, and opens it. The window frames the same PWA and the same Python backend; the native layer underneath adds the platform features below:

```bash
ephe desktop               # build, install to /Applications, open
ephe desktop --dev         # run the live shell against the dev URL
ephe desktop --no-install  # keep the build copy instead of installing
```

| Capability | Implementation |
|---|---|
| Tray icon with show / hide / quit / new session, native notifications, and a native file dialog instead of a typed path | `app/src-tauri/src/lib.rs` (`tray-icon`), `tauri-plugin-notification`, `tauri-plugin-dialog` |
| Backend supervision: starts and stops the Python backend recorded in `~/.ephe/desktop.json`, and names the missing record instead of guessing an interpreter | `app/src-tauri/src/backend.rs` |
| Engine key in the OS keychain (macOS Keychain / Linux SecretService), with a `0600` key file as fallback | `core/engine_config.py` |
| Keep-awake during a run (`caffeinate` on macOS) | `app/src-tauri/src/lib.rs` (`set_keep_awake`) |
| Browser pane: a child WebView, so a page sending `X-Frame-Options` loads where an `<iframe>` painted white | `app/src-tauri/src/browser.rs` |
| Single instance: a socket in the configuration directory fronts the running app, with `tauri-plugin-single-instance` as the cross-platform backstop | `app/src-tauri/src/instance.rs` |
| Signed auto-updater wired to the app's own update check | `tauri-plugin-updater`, `tauri-plugin-process` |

## Getting Help

The index is [`docs/`](docs/README.md): the [quickstart](docs/QUICKSTART.md), the [install guide](docs/INSTALL.md), [architecture](docs/ARCHITECTURE.md), the [CLI reference](docs/CLI.md), the benchmark methodology ([benchmark-mapping.md](docs/benchmark-mapping.md)), the plugin format spec ([PLUGINS.md](docs/PLUGINS.md)), the switcher guide ([SWITCHING.md](docs/SWITCHING.md)) and the demo media.

- Bugs and feature requests: the GitHub [issue tracker](https://github.com/bemlerlabs/ephe/issues) — the `bug_report` and `feature_request` templates are in the repo.
- Questions and release notes: the [Telegram channel](docs/TELEGRAM.md).
- Security reports: the private channel in [SECURITY.md](SECURITY.md), never a public issue.
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) — fork, branch, add or update Given-When-Then tests, run the narrowest relevant checks first, open a pull request with the template.

## Who this is for

**At home, for yourself.** Ephe runs on your machine and keeps its state on your machine.
No account, no telemetry, no server of ours in the path. Install it, use it, keep it.

**Learning, testing, contributing.** Welcome. The tests are in this repository, the
architecture is documented, and a pull request that fixes a bug or sharpens a sentence is
worth more than a star. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Production use.** Needs a commercial licence. That is the whole of it: running Ephe for
real work, at work or inside a company, or as part of a product or a service you offer. The
grant is `None`, so nothing else in the licence covers it. Ask us; the tiers and the process
are in [COMMERCIAL.md](COMMERCIAL.md).

## License

Business Source License 1.1 (BUSL-1.1) — source-available, and free for non-production
use: read it, run it, modify it, build on it, evaluate it, contribute to it. **Production use
needs a commercial licence**, which means running Ephe for real work, at work or inside a
company, or as part of a product or service you offer. See [COMMERCIAL.md](COMMERCIAL.md).

Each version falls to the Apache License 2.0 on the fourth anniversary of its first
public release, so everything published here becomes plain open source four years
later. The operative terms are in [LICENSE](LICENSE); what you grant us by sending a
contribution is in [CONTRIBUTING.md](CONTRIBUTING.md).
