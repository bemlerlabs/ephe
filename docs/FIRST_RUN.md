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
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

That is the command Ephe is designed around, and it is the one the README shows. The
repository is public, so the fetch answers HTTP 200 and the installer runs; nothing else
has to happen first. The package route is wired but not yet live: the Homebrew cask
(`packaging/homebrew/ephe.rb`) and the Scoop manifest (`packaging/scoop/ephe.json`) name
the published `v0.1.0-beta.3` release with hashes measured from its assets, but the tap and
bucket they land in are not created yet, and the npm wrapper (`packaging/npm/`) is
unpublished. See [The step that still needs the owner](#the-step-that-still-needs-the-owner).

### The path that works today

Run the installer from a checkout you have access to. It installs in place:

```bash
git clone https://github.com/bemlerlabs/ephe.git
cd ephe
./install.sh
```

On Windows the equivalent is `install.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## 2. Install

Requirements, all of them ordinary:

| Component | Needed for | Minimum |
|---|---|---|
| Python | everything | 3.10 (the installer will provision one via `uv` if the machine has none) |
| Node.js + npm/pnpm | the desktop/PWA build | 20 LTS |
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

```bash
source .venv/bin/activate
ephe start --open
```

With no `~/.ephe/engine.json`, the app opens the **setup screen** instead of an
empty chat (the chat fails closed with an honest hint until an engine is chosen).
The screen offers three classes of engine. Two of them are the realistic first
run, and each has its own next step.

### Path A — a hosted API you already have a key for

This is the fastest first answer: nothing to install, nothing to run locally.

1. Create a key at the provider. Ephe registers no account for you and resells
   nothing — the key is the provider's own. The setup screen links the common
   ones: **OpenRouter** (`https://openrouter.ai/keys`) and **OpenCode Zen**
   (`https://opencode.ai/zen`).
2. On the setup screen, pick **OpenAI-compatible API** and use the matching quick
   pick (OpenRouter, OpenCode Zen), or type your endpoint under "Endpoint URL"
   (for example a vLLM or SGLang host you already run).
3. Paste the key into **API key**. It stays on this device: the desktop app writes
   it owner-only to `~/.ephe/engine.key`, and in a browser it lives only in the
   running server process.
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

## The step that still needs the owner

Everything above a stranger can do alone **except the package installs**. The `curl … | bash`
one-liner and the checkout both work today: the repository is public and `v0.1.0-beta.3` is
published with its desktop bundles, so `install.sh` and the `Ephe.app` download it pulls are
reachable. What is not live yet is the package route, and it needs four things only the owner can
create:

- the repositories `bemlerlabs/homebrew-tap` and `bemlerlabs/scoop-bucket`, and
- the secrets `NPM_TOKEN` and `PACKAGES_TOKEN`.

Until those exist, `brew install --cask` and `scoop install` have no tap or bucket to read, and the
npm wrapper is unpublished. The exact names and scopes are pinned in the manifests under
`packaging/`.
Nothing after the install reads the owner's personal `~/.ephe` — a machine with no `~/.ephe` at all
reaches the setup screen and a first answer by following the steps above.

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
