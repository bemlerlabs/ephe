# First run: from zero to a first answer

This page is for someone who has never seen Ephe before and wants to end up
typing a question and reading an answer. It is written from the actual walk on a
clean macOS machine (2026-10-14), so every command and every screen here is one
that really exists — the measured sequence is repeated at the bottom.

Ephe is local-first: it is a FastAPI backend plus a web app (PWA) that also ships
inside a Tauri desktop shell. It installs **no AI of its own**. The engine is
chosen once, in the app, and it can be a hosted API you already pay for or a
runtime already running on a machine you control.

There are five steps:

1. get the code,
2. run the installer,
3. activate the environment,
4. choose an engine (one of two paths),
5. ask your first question.

---

## 1. Get the app

### The one-command install

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.4.0/install.sh | bash
```

That is the command Ephe is designed around, and it is the one the README shows. The
repository is public, so the fetch answers HTTP 200 and the installer runs. The
package-manager routes are not published; use this one-liner or the checkout below.

### The path that works today

Run the installer from a checkout you have access to. It installs in place:

```bash
git clone https://github.com/bemlerlabs/ephe.git
cd ephe
./install.sh
```

On Windows, download and run `install.ps1`. This path is not yet verified end to end on Windows for this revision:

```powershell
irm https://raw.githubusercontent.com/bemlerlabs/ephe/v0.4.0/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## 2. Install

Requirements, all of them ordinary:

| Component | Needed for | Minimum |
|---|---|---|
| Python | everything | 3.11 (the installer will provision one via `uv` if the machine has none) |
| Node.js + npm/pnpm | the desktop/PWA build | 20+; 22.23.4 is the tested build runtime |
| Ollama | only the local-runtime engine path | any recent version, installed by you |

Disk: the install wants roughly 4 GB (product, dependencies, PWA build). A model
is **not** downloaded here.

What the installer does: prepares Python, creates `.venv`, installs the Python
dependencies, builds the web app into `app/dist/`, creates `~/.ephe/`, and then
prints how to start. What it does **not** do: it does not install Ollama, it does
not pull any model, and it does not write an engine choice — there is no silent
default engine, by design.

A piped run has no terminal, so it cannot ask and takes the desktop mode, which
is why Node.js is required. On a machine meant only for the terminal UI:

```bash
./install.sh --cli
```

When it finishes it prints exactly these lines — the `ephe` command is not on
`PATH` yet, so activate the environment first:

```text
source "…/ephe/.venv/bin/activate"

Then, in that same shell:
  ephe configure    # choose the engine once (saved to ~/.ephe/engine.json)
  ephe doctor       # check Ollama, model and server state
  ephe start --open # start the local app, then open http://127.0.0.1:8765
```

## 3. Choose an engine

If the installer opened the setup screen, choose an engine there. For terminal use,
activate the default macOS/Linux installation and configure the engine before starting:

```bash
source "$HOME/Documents/Ephe/.venv/bin/activate"
ephe configure
ephe start --open
```

For a checkout installation, run `source .venv/bin/activate` from that checkout instead.
For Windows, activate the default installation with PowerShell:

```powershell
& "$HOME\Documents\Ephe\.venv\Scripts\Activate.ps1"
ephe configure
ephe start --open
```

Use that installation's `.venv` for a custom location. Without an engine choice,
the terminal start refuses with a setup hint. The setup screen offers three engine
classes; the paths below describe hosted and local engines.

### Path A — a hosted API you already have a key for

This is the fastest first answer: nothing to install, nothing to run locally.

1. Create a key at the provider. Ephe registers no account for you and resells
   nothing — the key is the provider's own. The setup screen links the common
   ones: **OpenRouter** (`https://openrouter.ai/keys`) and **OpenCode Zen**
   (`https://opencode.ai/zen`).
2. On the setup screen, pick **OpenAI-compatible API** and use the matching quick
   pick (OpenRouter, OpenCode Zen), or type your endpoint under "Endpoint URL"
   (for example a vLLM or SGLang host you already run).
3. Paste the key into **API key**. The settings page stores it in the OS keychain
   or in `~/.ephe/engine.key` with owner-only permissions; a shell export stays in
   the running process. Ephe never writes the key to `engine.json` or the chat.
   The stored key is bound to this engine in `~/.ephe/engine.key.binding.json`;
   the sidecar carries a SHA-256 of the key, not the key.
4. Click **Probe endpoint**. The screen lists the models the endpoint reports;
   pick one and click **Save**.

Free model tags (suffixed `-free` or `:free`) are marked in the list.

### Path B — a local runtime (Ollama on this machine)

Nothing is bundled and nothing is pulled for you, so this path is three commands
on your side and then the same probe:

1. Install Ollama: `https://ollama.com/download`. The setup screen links this
   directly when no local engine is answering.
2. Start it. Ephe expects the default `http://127.0.0.1:11434`.
3. Pull a model you have the memory for — Ephe will not size one for you:

   ```bash
   ollama pull <tag>
   ```

4. Back on the setup screen, pick **Local Ollama (this device)**, click **Probe
   endpoint**, choose the tag, and **Save**.

A 12-billion-parameter tag wants roughly 16 GB of unified memory to run well;
smaller tags need less. A remote or hosted endpoint needs none of that locally.

## 4. First answer

Once the engine is saved you land in the chat. Open:

```text
http://127.0.0.1:8765
```

Type a question and press Enter. The first reply streams back from the engine you
chose. If you skipped setup, the chat stays read-only and the engine chip in the
composer brings you back to this screen.

That is the whole path. No wiki, no configuration file to write by hand.

---

## Package-manager routes

The Homebrew cask and Scoop manifest are prepared under `packaging/`, but the tap and
bucket are not published; the npm wrapper is unpublished too. Use the one-liner or the
checkout until those routes exist.

## Measured sequence

The walk this page describes, run on macOS 26.6 (2026-10-14) against the
worktree that carries these changes, on port 9228:

```text
1. ./install.sh                       # desktop mode, no start
   → Python 3.12.15 found, .venv created, [gui,voice] installed,
     PWA built → app/dist, ~/.ephe created
2. source .venv/bin/activate
3. ephe start --open                  # server on 127.0.0.1:9228
4. open http://127.0.0.1:9228         # setup screen (no engine.json)
5. choose a path (A or B) → Probe → model → Save
6. type a question → first answer
```

Step 4 is the state a stranger sees: the setup screen, with the local-runtime
hint and the key help visible, before any engine has been chosen.
