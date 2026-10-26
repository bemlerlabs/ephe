<p align="center"><a href="README.md">English</a> | <a href="README.zh-CN.md">中文</a> | <a href="README.es.md">Español</a></p>

<div align="center">
<img src="docs/media/ephe-bee-512.png" alt="Ephe bee mark" width="88">

# Ephe

**Ephe is a local-first workspace for an AI agent on your own computer. You choose the engine and the model, approve the tools, and keep the files. There is no account and no hidden model default.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License BUSL-1.1](https://img.shields.io/badge/License-BUSL%201.1-2d6a4f?style=flat-square)](LICENSE)
[![Tests](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml)
[![Frontend Build](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml)

</div>

![The Ephe workspace at 1280 px: a task list on the left, the agent's empty chat in the middle, the workspace switcher and the composer.](docs/screenshots/readme-chat-1280.png)

- **Private by default.** A local engine keeps your prompts on your machine. Online paths are opt-in.
- **Your model.** Pick a local Ollama model or an OpenAI-compatible endpoint. Ephe never picks one for you.
- **Your files.** Work in the folder you choose. The agent's artifacts are saved on your machine.

## What Ephe is

Ephe is a workspace for an AI agent on your computer. You give the agent a task. It plans, uses tools, and shows the work while it runs. In the default strict profile, file edits and shell commands ask for your approval.

The engine answers with a model. A local engine such as Ollama runs the model on your hardware. An OpenAI-compatible endpoint runs it at a provider you choose. Ephe ships no weights and selects no default model.

A plugin bundles commands and a skill pack. A skill is a reusable set of instructions the agent can follow. A connector links an external tool. You can configure MCP servers manually today. The bundled Superpowers skill pack installs into your own profile from the Extension Center after a confirmation.

Ephe calls one run a cell. The cell is a disposable workspace for the session. The files you keep and the settings you save stay on disk. Ephe uses SI as shorthand for a personal super-intelligence: an agent that can plan and use tools under your approval.

The workbench keeps the files the agent produced. You can open, download or adopt them; the source stays in the workspace.

## What you can do

These workflows ship as first-party plugins. The chat names the tool result behind each step.

1. **Write a document from a source pack.** The [documents](plugins/documents) and [local-document-factory](plugins/local-document-factory) plugins produce PDF or DOCX files with sources and a verification step.
2. **Build a deck or a spreadsheet.** [presentations](plugins/presentations) writes PPTX decks with evidence and speaker notes; [spreadsheets](plugins/spreadsheets) builds XLSX models with separated inputs and assumptions.
3. **Research with dated sources.** [web-research](plugins/web-research) keeps direct URLs, dates and quoted evidence. Web access is an opt-in path.
4. **Reproduce a bug and prove the fix.** [code-shell](plugins/code-shell) reproduces a defect, applies the smallest fix and proves it with a test run.
5. **Keep notes you can recall.** [memory](plugins/memory) stores, recalls and deletes durable facts after confirmation; [private-research-notebook](plugins/private-research-notebook) builds cited answers and briefs from local sources.

Choose the engine that fits your machine:

![Ephe settings at 1280 px: an OpenAI-compatible engine, a model picker and the endpoint.](docs/screenshots/readme-settings-1280.png)

Work in a phone-sized window over your own network:

![Ephe at a 390 px phone viewport: the agent workspace, the engine state and the composer.](docs/screenshots/readme-chat-390.png)

## What happens in a task

1. You type a task in the composer. The agent turns it into a plan.
2. It uses a tool, such as reading a file or running a command. The strict profile requires approval for file edits and shell commands.
3. The result appears in the chat. Files and charts land in the workbench, where you can open or adopt them.
4. The session cell ends. The artifacts and settings you saved stay on disk.

Every tool result stays attached to the turn that produced it. A claim about a file comes from a real tool result, not from the model's memory.

## Desktop, terminal, phone

The desktop and browser share an installable web app (PWA) and one Python backend. `ephe desktop` builds and installs the desktop shell; `ephe start --open` opens the browser app. A build writes `Ephe.app` under `app/src-tauri/target/`; that copy is not an install. `ephe desktop` puts the app in `/Applications` and removes the build copy, and the update button rewrites the installed bundle.

The terminal (`ephe tui`) uses the engine choice from `~/.ephe/engine.json`. A phone on your local network can open the PWA after `ephe start --lan --open`; public access is a separate opt-in path.

## Quick start

### 1. Install

#### macOS and Linux

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.11/install.sh | bash
```

To read the script before it runs, use the checkout:

```bash
git clone https://github.com/bemlerlabs/ephe.git
cd ephe
./install.sh
```

The installer prepares Python and the local environment, builds the web app, and starts it at `http://127.0.0.1:8765`. If macOS asks whether to open the app, use System Settings → Privacy & Security → Open Anyway.

#### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.11/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

From a local checkout, run the same `powershell -ExecutionPolicy Bypass -File .\install.ps1` after opening PowerShell in that folder.

Windows installation is not yet verified end to end for this revision. The commands are documented, but a Windows runner or VM check is still pending.

#### Docker

Docker and every installer flag are described in [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md).

The command points to the current public release, `v0.1.11`. The Bash installer defaults to `--desktop`; pass `--cli` or set `EPHE_MODE=cli` for the terminal-only install.

Before using `ephe` in a new terminal, activate the installed environment.
For the default installation on macOS or Linux:

```bash
source "$HOME/Documents/Ephe/.venv/bin/activate"
```

For the default Windows installation:

```powershell
& "$HOME\Documents\Ephe\.venv\Scripts\Activate.ps1"
```

For a checkout or custom location, use the `.venv` inside that folder instead.

### 2. Choose the engine

The app opens the Setup page. Pick a local Ollama model, a remote Ollama, or an OpenAI-compatible endpoint. For the terminal, `ephe configure` writes the same choice to `~/.ephe/engine.json`. Ephe refuses to start without a choice; there is no hidden default.

For a hosted endpoint, enter its key on the same page. The app keeps it in the OS keychain or in `~/.ephe/engine.key` with owner-only permissions. It is never written to `engine.json` or printed in the chat. The stored key is bound to this engine in a sidecar, `~/.ephe/engine.key.binding.json`, which carries a SHA-256 of the key, not the key. The app refuses a stored key without that binding.

### 3. Ask

Open `http://127.0.0.1:8765` or run `ephe start --open`. The desktop shell is built from the same app; `ephe desktop` installs it. From the terminal, `ephe tui` opens the text interface. Type a task. The strict profile asks before file edits or shell commands.

To use the same workspace from a phone on your network, start with `ephe start --lan --open`, open Settings → Mobile. Click **Connect mobile**. Scan the QR code, then open the PWA on the phone. Public access is a separate opt-in path; the walkthrough is in [docs/MOBILE.md](docs/MOBILE.md).

## What you need

| Need | Detail |
|---|---|
| Computer | macOS 13+ or Ubuntu 22+; a current browser; Windows PowerShell instructions remain unverified end to end |
| RAM | 8 GB free for a small local model; 16 GB or more for a 12B-class model; a remote engine needs less |
| Disk | 12 GB free; more for the model you choose |
| Build tools | Node.js 22.23.4 is the tested build runtime; use it with npm/pnpm. Python supports 3.11 or newer; `.python-version` pins the 3.13 series |
| Engine | A local Ollama model or an OpenAI-compatible endpoint and key; no Ephe account |

A local model uses the RAM and disk of the machine that runs it. A hosted endpoint needs a network connection, an endpoint URL and an API key. A local engine needs no API key. Ephe ships no model and asks for no account. For a local model, pull a tag first: `ollama pull <tag>`.

## What it costs

Ephe has no subscription and no account. A local model uses your hardware. A hosted engine bills you directly under its own terms. The source is available under BUSL-1.1; production use needs a commercial licence, described in [COMMERCIAL.md](COMMERCIAL.md).

Local inference has no provider fee. Non-production use is free; production use requires a commercial licence regardless of engine. A hosted provider sets its own price.

## Private and in control

A local engine keeps the prompt on your machine. A remote engine, web search, public mobile access and cloud text-to-speech send what you ask to that service; each one is opt-in.

The engine key stays in the OS keychain or in `~/.ephe/engine.key` with owner-only permissions. The settings page and `ephe configure` write it; Ephe does not print it.

The default strict profile asks before file edits and shell commands. Opt-in modes and remembered approvals can allow execution without another prompt. Check the approval profile in the composer. The session cell is destroyed when the session ends; saved artifacts and settings remain on disk.

There is no account and no sign-up. The update check asks GitHub for the newest release; every other network path waits for your action. The optional online features are listed in Setup and Settings. The details are in [docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md) and [SECURITY.md](SECURITY.md).

## Plugins, skills, and connectors

Ephe ships nine first-party plugins, seven capability presets, five first-party skill packs and one bundled third-party skill pack (Superpowers, MIT). A plugin adds commands and a skill pack; a skill is a reusable instruction set; a preset is a capability without a plugin quality claim. The app also ships its built-in skills; see [docs/SKILLS.md](docs/SKILLS.md).

The plugin set covers documents, presentations, spreadsheets, code-shell, browser-use, web-research, memory, local-document-factory and private-research-notebook. The presets cover image work, Model Context Protocol (MCP) tools, vision, voice, guides, plugin creation and skill creation.

The nine first-party plugins and the five first-party skill packs ship with the app. The Extension Center shows what each entry can do. The Superpowers pack ships as bundled third-party content and installs into your own profile after a confirmation, because it is not signed. A public catalogue for external publishers is planned.

You can add MCP servers manually in Settings → Connectors. Its catalogue provides setup hints and documentation links; it does not install those external servers.

## What is not there yet

- No iOS or Android app. The phone surface is the PWA over your own network.
- No model weights. You choose an engine and a model.
- No crawler by default. Web research is opt-in.
- No one-click installation of external MCP servers. MCP connections require manual setup.
- No multi-user server. One instance serves one person on one machine.
- No public catalogue for third-party publishers. One bundled third-party pack (Superpowers, MIT) ships with the app; the other entries are first-party.
- Windows installation and browser startup still need an end-to-end check on Windows.
- No public plugin marketplace. The bundled pack is installable; a marketplace with external entries is planned.

## If something goes wrong

- **Your saved install command names an older release.** Compare it with the Quick start command above before installing.
- **The app opens Setup and will not chat.** Choose an engine there, or run `ephe configure`. A local model and a hosted endpoint are both valid.
- **macOS says the app is not notarized.** Open System Settings → Privacy & Security and choose Open Anyway.
- **PowerShell blocks the script.** Use `powershell -ExecutionPolicy Bypass -File .\install.ps1` in the folder where you downloaded the script.
- **A local model feels slow.** Check free RAM first; a smaller model uses less. A hosted endpoint moves the work off this machine.
- **Where are my data and key?** `~/.ephe` holds settings, sessions, artifacts and logs; the OS keychain (preferred) or `~/.ephe/engine.key` (0600) holds the engine key. `./uninstall.sh --dry-run` prints the plan and touches nothing; `./uninstall.sh --keep-data` removes the checkout and keeps `~/.ephe`; `./uninstall.sh --yes` removes both.

## Docs, contributing, and license

The index is [docs/README.md](docs/README.md). Start with the [quickstart](docs/QUICKSTART.md), the [install guide](docs/INSTALL.md), [first run](docs/FIRST_RUN.md), the [CLI reference](docs/CLI.md), [plugins](docs/PLUGINS_OVERVIEW.md), [skills](docs/SKILLS.md) and [security and privacy](docs/SECURITY_AND_PRIVACY.md).

- Bugs and feature requests: the [issue tracker](https://github.com/bemlerlabs/ephe/issues).
- Security reports: the private channel in [SECURITY.md](SECURITY.md).
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
- Licence: Business Source License 1.1 (BUSL-1.1), source-available. The terms are in [LICENSE](LICENSE); production use is described in [COMMERCIAL.md](COMMERCIAL.md). Each version falls to Apache 2.0 four years after its first public release.
