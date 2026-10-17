# Quickstart — from nothing to a first answer

Five minutes, one path. The long version, with the screens and the measured sequence on a
clean machine, is [FIRST_RUN.md](FIRST_RUN.md).

## 1 · Install

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

macOS asks once about an unnotarized app: **System Settings → Privacy & Security → Still
Open**. Windows takes [install.ps1](../install.ps1); Docker and every installer flag are in
[INSTALL_OPTIONS.md](INSTALL_OPTIONS.md).

## 2 · Start

```bash
ephe start          # backend on :8765 plus the PWA in your browser
ephe tui            # the same agent in a terminal UI
```

## 3 · Choose the engine

Ephe installs no AI of its own and picks none for you. With nothing stored, the app opens its
setup page and waits rather than answering with a model you never named.

| What you have | What to choose | What it needs |
|---|---|---|
| Ollama on this machine | local Ollama | the tag you pulled (`ollama pull <tag>`) |
| Ollama on a machine you control | custom Ollama | its base URL, e.g. `http://host:11434` |
| A hosted or OpenAI-compatible endpoint | OpenAI-compatible | base URL, plus `EPHE_OPENAI_COMPAT_API_KEY` in the shell that starts `ephe`, or `~/.ephe/engine.key` for an app opened from the Dock |

The choice is what `ephe configure` stores in `~/.ephe/engine.json`; an access key never
lands in that file. A model name is not an engine choice — `--model <tag>` picks the tag
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
| The endpoint answers 401 | the key is not visible to the process that runs the turn | export `EPHE_OPENAI_COMPAT_API_KEY` where you start `ephe`, or store it in `~/.ephe/engine.key` |
| An engine change is not picked up | the server reads the choice at start | restart `ephe start` |

Next: [CLI.md](CLI.md) for every subcommand, [MOBILE.md](MOBILE.md) to pair a phone over
your LAN, [SWITCHING.md](SWITCHING.md) to bring an existing local-agent setup across.
