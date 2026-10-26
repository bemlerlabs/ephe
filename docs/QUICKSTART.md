# Quickstart — from nothing to a first answer

Five minutes, one path. The long version, with the screens and the measured sequence on a
clean machine, is [FIRST_RUN.md](FIRST_RUN.md).

## 1 · Install

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.9/install.sh | bash
```

On Windows, use PowerShell. This installation path is not yet verified end to end for this revision:

```powershell
irm https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.9/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

macOS asks once about an unnotarized app: **System Settings → Privacy & Security → Open Anyway**.
Docker and every installer flag are in [INSTALL_OPTIONS.md](INSTALL_OPTIONS.md).

## 2 · Start

Activate the environment in each new terminal. For the default macOS/Linux installation:

```bash
source "$HOME/Documents/Ephe/.venv/bin/activate"
ephe configure      # choose the engine before starting from the terminal
ephe start --open   # backend on :8765 plus the web app
ephe tui            # alternatively, use the terminal interface
```

For the default Windows installation:

```powershell
& "$HOME\Documents\Ephe\.venv\Scripts\Activate.ps1"
ephe configure
ephe start --open
```

For a checkout or custom location, activate the `.venv` inside that folder instead.

## 3 · Choose the engine

Ephe installs no AI of its own and picks none for you. With nothing stored, the app opens its
setup page and waits rather than answering with a model you never named.

| What you have | What to choose | What it needs |
|---|---|---|
| Ollama on this machine | local Ollama | the tag you pulled (`ollama pull <tag>`) |
| Ollama on a machine you control | custom Ollama | its base URL, e.g. `http://host:11434` |
| A hosted or OpenAI-compatible endpoint | OpenAI-compatible | base URL and a key saved through Setup/Settings or `ephe configure`; alternatively, export `EPHE_OPENAI_COMPAT_API_KEY` in the launching shell |

Setup/Settings and `ephe configure` save the key with its engine binding; writing the key
file alone is insufficient. The engine choice is stored in `~/.ephe/engine.json`; the key
never lands in that file. A model name is not an engine choice — `--model <tag>` picks the tag
inside the engine you already chose, and with none named the app asks.

## 4 · Ask

Type a question and read the answer. If something is off, `ephe doctor` names what it found,
and `ephe doctor --fix` repairs the safe drift.

## When it does not work

| Symptom | Why | Way out |
|---|---|---|
| The chat stays closed | no engine is chosen — that gate is deliberate | finish the setup page, or run `ephe configure` |
| `no model chosen` | no `--model`, no `EPHE_MODEL` and no stored tag | name one: `ephe start --model <tag>` |
| Port 8765 is taken | another process (or a second Ephe) holds it | `ephe start --port 8766` |
| The endpoint answers 401 | the key is missing, invalid or belongs to another provider | save the matching key through Setup/Settings or `ephe configure`, or export `EPHE_OPENAI_COMPAT_API_KEY` in the launching shell |
| An engine change is not picked up | the server reads the choice at start | restart `ephe start` |

Next: [CLI.md](CLI.md) for every subcommand, [MOBILE.md](MOBILE.md) to pair a phone over
your LAN, [SWITCHING.md](SWITCHING.md) to bring an existing local-agent setup across.
