# Ephe CLI — `ephe` Reference

All subcommands of the local CLI (entry point `ephe`). Global flags: `--help` and `--version`. Every other flag belongs to the subcommand that declares it: `--model <name>` (the model **inside** the chosen engine — a model name is not an engine choice) is a flag of `start`, `web`, `tui`, `doctor`, `code`, `run`, `goal` and `serve`, and `--port <n>` is a flag of `start`, `web`, `doctor` (default 8765) and `serve` (default 8766).

Engine resolution applies to every model run and has no silent default: the persisted
`~/.ephe/engine.json` → an explicit engine env (`EPHE_MODEL_PROVIDER` + endpoint) →
interactive onboarding (only on a TTY) → abort with instructions (`ephe configure`). This
covers the headless runs `ephe code`, `ephe goal` and `ephe serve` and `ephe start`:
without a chosen engine it spawns the server with **no engine env**, so `run_server.py`
enters setup mode, `EPHE_SETUP_MODE` is set and the chat stays closed until the Setup page
persists a choice.

The model tag follows the same rule: no `--model` flag, no `EPHE_MODEL` and no persisted
choice means **no tag**, and onboarding asks instead of pre-filling one. `ephe doctor`
without a tag reports `no model chosen` rather than probing a model that was never named,
and `ephe update` without one pulls nothing.

An endpoint that needs an access token reads one variable, `EPHE_OPENAI_COMPAT_API_KEY`, and
the surface decides how it gets filled: exported in the shell that runs `ephe start`, typed into
the engine form in the app (that server process only, gone at the next start), or stored by the
user in `~/.ephe/engine.key` for an app opened from the Dock — which inherits no shell
environment. `docs/SECURITY_THREAT_MODEL.md` §1a holds the three lifetimes and the file rules.

## `ephe start`
Starts backend + PWA locally (backend :8765, PWA build). Loads `engine.json`, starts the scheduler and makes sure the model is loaded. `--model <tag>` overrides the model inside the chosen engine and picks no engine itself; with no engine chosen it names nothing, so the PWA starts in setup mode and takes over the selection in the browser.

The port is inspected first. A backend from this installation is reused; one from another checkout, another version, or without a matching pidfile is named and the start exits 1 instead of moving to the next port. `--takeover` is the explicit permission to stop such an Ephe backend first. A listener that is not Ephe is never killed. See `docs/OPERATIONS.md`.

## `ephe stop [--port <p>] [--timeout <s>] [--json]`
Stops the backend that `~/.ephe/run/backend-<port>.json` and `/api/health` agree is this installation's: `SIGTERM`, wait, `SIGKILL`, then verify the port has no listener. Exit 0 when nothing was running; a process the record does not prove is named, never killed.

## `ephe status [--json]`
Prints pid, version, root and owner of the backend on the port, and whether the pidfile proves ownership. Exit 0 when an Ephe backend answers, 1 when nothing does.

## `ephe doctor [--fix] [--json]`
Diagnoses the local setup: Python, project files, the engine (chosen, reachable, key bound), model (installed + load test), the **context files** the workspace contributes, the **image endpoint** (informational) and **voice (TTS)** (informational).

The last line is the one to act on: `Next: <command>   # <why>` names the single step that
moves this setup forward — the engine setup, a model pull, a safe repair, or the app.

States the app resolves by itself do not fail the run: no engine chosen yet, a server that
is not running, and the optional rows are reported and keep the exit code at 0. A broken
setup does fail it — a half-written engine config, a configured engine that does not answer,
a missing model of the chosen engine, a skills-lock mismatch.

The model line covers a tag that exists: `--model`, else `EPHE_MODEL`, else the persisted
local-Ollama choice. `--fix` repairs the safe drift: release-tag fast-forward, dependencies
(`.[gui,voice]`), Ollama service + model, PWA build. With no tag there is nothing to pull,
so the repair is skipped instead of turning the run red.

The `Context files` row counts what the workspace contributed (loaded, capped, refused) and
points at `ephe context` for the files themselves. It reports a state, so it never moves the
exit code.

## `ephe context [--json]`
The files the workspace contributes to the prompt, one row per file: the layer it belongs
to, its character count, the status the reader gave it (`included`, `truncated`, `denied`,
`empty`, `unreadable`, `skipped`) with the reason a file stayed out, and the caps in force.
The header names the workspace root that was read.

The files, the caps and the status words come from `core/workspace_rules.py`, the same
resolver the system prompt is built from, so this report and what the model received cannot
drift. `--json` prints `{workspace, layers, caps, total_chars, counts, source}`, where each
layer carries `{name, file, chars, status, reason, scope}`.

## `ephe update [--model <name>] [--channel release|commit]`
Release-tag fast-forward, dependencies, installer invocation. The default channel is
`release`: `ephe update` asks the release feed, moves the checkout to that tag and runs the
installer. It never follows `main`'s tip and never asks for an untagged merge; between
releases it is a no-op. If a newer release exists but the checkout already contains it, the
command refuses rather than rewriting the tree backwards. `--channel commit` is the explicit
exception for a checkout that serves
the desktop/PWA backend: it follows `main` and says so. Without `--model` and without
`EPHE_MODEL` no model is passed to the installer: `ephe update` names no tag on the user's
behalf. See [UPDATES.md](UPDATES.md) for the three surfaces.

## `ephe voice list | install <voice>...`
Manage local Piper voices:
- `list`: binary status (`brew install piper`) + installed voices (`~/.ephe/voices/`)
- `install en_US-amy-medium`: downloads the `.onnx` + `.onnx.json` from HuggingFace (opt-in, 200-MB cap)

## `ephe` / `ephe tui`
Textual TUI (terminal mode, extra `.[tui]`). The bare `ephe` opens it too; without a
terminal (pipe, CI) it prints the usage page and exits 2.

Engine resolution as above, with one difference: **no chosen engine is no abort here**.
The app opens and offers its own setup (provider list, endpoint, API key, model) —
`F10` or `/setup` reopens it. Nothing is sent until a choice exists, and a config that
names a remote provider without an endpoint counts as none. `--model <tag>` overrides
the model inside the chosen engine — a model name is not an engine choice. `--api-url
<url>` picks an OpenAI-compatible engine explicitly and needs a tag from `--model` or
`EPHE_OPENAI_COMPAT_MODEL`; with neither it fails closed and names that variable.

One update check at start: when a newer release tag exists, the app shows the update after
the greeting, runs the release-tag fast-forward plus the installer on request, and closes so
the next start carries the new build. The terminal does not follow `main` between releases;
a stored `commit` channel belongs to the desktop/PWA and is ignored here.
`EPHE_NO_UPDATE_CHECK=1` turns the check off.

## `ephe configure [--force]`
Store the engine choice once (a preset or your own endpoint). The choice lands in
`~/.ephe/engine.json`; a key typed here goes to the OS keychain or `~/.ephe/engine.key`,
never into that file. `--force` re-selects even when a config already exists.

## `ephe code "<task>"`
Coding agent in the workspace: read → edit → verify with `run_tests`, every
mutating step behind an approval gate and in the audit. Needs a chosen engine.
Batch: the answer is printed at the end and an optional `--json` / `--run-record <path>`
carries exactly one machine-readable run record.

## `ephe run "<task>"`
The interactive sibling of `ephe code`: the same coding loop, but every phase, tool call
and answer token **streams to the terminal as it happens**. The turn is kept in a session
(printed at the end), so `--resume <session>` continues the same thread, and the
workspace's diff is recorded as a change set whose id the printout hands to
`ephe show` / `ephe review` / `ephe publish`. Needs a chosen engine.
- `--workspace <path>`: the tree the run edits and records a change set from (default: cwd)
- `--resume <session>`: continue a saved session; an unknown id is refused before the loop
- `--no-stream`: buffer the answer and print it once at the end
- `--verify "<cmd>"`: verifier command run after the loop
- `--dry-run`: print the plan (engine, tree, resume target) and spend no turn
- `--json` / `--run-record <path>`: one machine-readable record on stdout; the stream goes
  to stderr, so a pipe stays parseable

## `ephe show <change-set>`
Print one stored change set's unified diff, file by file — the read half of the accept
loop. The diff is regenerated from the worktree, so a path that moved since the set was
built is flagged as drifted rather than shown as if it still matched. `ephe changes
<workspace>` lists the ids (newest first); `ephe review <id> approve --reviewer R --reason
PATH:LINE:WHY` accepts a set and `ephe publish <id>` lands it.

## `ephe goal "<goal>" [--check "pytest -q"] [--max-turns 10]`
Autonomous goal loop: goal → agent (tools included) → fixed check command → automatic
re-turn on failure. The exit code follows success. Needs a chosen engine.

## `ephe serve [--host <h>] [--port <p>] [--lan] [--token <t>] [--takeover]`
OpenAI-compatible engine (`/v1/chat/completions`, `/v1/models`) for other coding CLIs.
Binds only to localhost by default; `--lan` generates an auth token. With `--token` a
client sends that token as `X-Auth-Token` or as `Authorization: Bearer <token>`, so an
OpenAI SDK reaches the engine with `api_key=` alone. The engine it passes through is the
chosen one — without a choice the server does not start.

## `ephe tool <name> [--arg k=v ...] [--dry-run]`
Run a single tool directly (e.g. `ephe tool generate_image --arg prompt="…" --dry-run`). `generate_image` ships in the **image-studio** plugin: with that switch off (Settings → Plugins) the tool is not offered at all, `ephe tool generate_image` fails naming the tools that are, and `ephe tool --help` prints that same list.

## `ephe session list | new | switch <id> | rm <id> | rename <id> <title> [--json]`
Manage the local sessions under `~/.ephe/sessions/`. `list` prints them; `new` starts one;
`switch` and `rm` address one by id; `rename` sets its title.

## `ephe plugin list [--json] | enable <id> | disable <id> | install <id> | remove <id> [--yes] [--keep-data] [--dry-run]`
`list` prints the installed bundles first — name, version, switch state and the tools they
contribute — then the catalogue with an `installed` column. A bundle Creator Mode made on
this machine is an installed row even when the catalogue has no line for it. `--json`
carries `{installed, catalog}` with the same facts.

`enable`/`disable` toggle one bundle (the next agent turn follows). `install` fetches a
marketplace artifact: sha256-verified, manifest-validated, quarantined on error so a refused
artifact leaves nothing enabled.

`remove` previews by default: the folder, the `plugins.json` row, the lockfile entry, the
mount record and the stored files it would delete, plus what stays (the lifecycle state row,
the creator draft). `--yes` commits through the same service path as
`POST /api/market/remove`; an enabled bundle is switched off first and the answer names it.
`--keep-data` keeps `plugin-data/<id>` and the bundle's state folder, `--dry-run` names the
preview. Exit 0 for a preview or a removal, 1 for a bundle that is not installed, one that
ships with Ephe, or one an enabled dependent still needs.

## `ephe import <dir> [--apply] [--dry-run]`
Read a reference client's directory — persona files, `SKILL.md` trees, tool-server configs
and settings keys — and map it onto Ephe's formats. Without `--apply` the run is a plan and
writes nothing. Imported skills land disabled, and existing Ephe state is never overwritten.

## `ephe agents [--json]`, `ephe changes <workspace>`, `ephe review`, `ephe publish`
The workspace-change loop. `agents` lists every live workspace with its id, owner, state and
age; `changes` lists one workspace's change sets newest first; `review` files a verdict
(`approve`, `request-changes`, `reject`) with a located reason and refuses a self-approval;
`publish` lands one approved set on a branch by compare-and-swap, or nothing at all.

## `ephe reap`, `ephe prune`, `ephe device`
Housekeeping, each a dry run unless `--apply` is passed. `reap` removes registered workspace
trees whose owning process is gone; `prune` bounds the session stores by keeping the newest N
per group; `device` lists what the device folder holds and removes only the declared,
forgettable entries.

## `ephe sky`, `ephe amber`, `ephe bench`, `ephe project`
The extras. `sky` prints the Ephemerides (a day per line, `--days`); `amber` crystallises one
month into `~/.ephe/amber/<month>.json`; `bench` runs the plugin verify gate, and with `--run`
the pass³ measurement; `project` runs a Markdown phase plan, resuming from the boxes on disk.

## `ephe completion <shell>`
Shell completion (bash/zsh/fish).

## Command map

Three entry points, one codebase:

```bash
ephe --version                 # the version of this checkout (pyproject [project].version)
ephe --help                    # all subcommands, examples, exit codes
ephe start --open              # start the local web app + open browser (port 8765)
ephe stop                      # stop the backend this installation started, verify the port
ephe status                    # running? which pid, version and owner?
ephe desktop                   # build, install to /Applications and open (Tauri); --dev = live shell, --no-install = keep the build copy
ephe configure                 # choose the engine once (saved to ~/.ephe/engine.json)
ephe configure --force         # change the engine later
ephe start --lan               # LAN binding for QR mobile pairing
ephe start --model <tag>       # name the tag your engine serves
ephe doctor                    # setup check (Ollama, model, server)
ephe doctor --fix              # safe local repairs (repo, deps, Ollama, model)
ephe doctor --json             # machine-readable health report
ephe context                   # the workspace context files, caps and status
ephe update                    # newest release tag + dependencies + model
ephe                           # terminal UI (Textual); opens its setup if no engine is chosen
ephe tui                       # same surface, named
ephe tui --model <tag>         # TUI on a tag you named yourself
ephe tui --configure           # force the engine selection dialog
ephe serve                     # OpenAI-compatible engine (/v1/chat/completions)
ephe memory-mcp                # serve this workspace's memory over MCP on stdio (read-only)
ephe memory-mcp --allow-write  # …and let the connected agent correct facts
ephe tool <name> --dry-run     # run a tool deterministically (approval gate)
ephe run "fix the failing test" # agent run in the terminal — streams live, resumable
ephe run --resume <session> "…" # continue a saved run where it stopped
ephe show <change-set>         # print a change set's diff, file by file
ephe agents                    # live workspaces, their owner and state
ephe plugin list               # installed bundles first, then the catalogue
ephe plugin remove <id>        # preview; --yes removes, --keep-data keeps the files
ephe import ~/.other-client    # plan a settings/skills import (--apply writes it)
ephe session list|new|switch|rm|rename
ephe completion                # shell completion
```

A build writes `app/src-tauri/target/release/bundle/macos/Ephe.app`. That copy is not an install. `ephe desktop` moves the bundle to `/Applications` and deletes the build copy, and the update button rewrites the installed bundle in place. Start the app from `/Applications`; a copy under `target/` is build output.

## Engine choice (no silent default)

`ephe configure` asks once which engine to use and stores the answer in `~/.ephe/engine.json`. `ephe start`, `ephe tui`, `ephe code`, `ephe goal`, `ephe run`, `ephe serve` and the server (`run_server.py`) all read that same choice — one source of truth. Without a saved choice and without an explicit engine env they never pick an engine in silence: the terminal app opens its own provider setup, the remaining CLI paths stop with an actionable hint, the server starts in **setup mode on loopback** with the chat closed until a choice exists, and a LAN bind refuses to start outright. For scripted or headless setups use `EPHE_MODEL_PROVIDER=local_ollama|custom_ollama|openai_compatible` plus the matching `EPHE_LOCAL_OLLAMA_BASE_URL` / `EPHE_CUSTOM_OLLAMA_BASE_URL` / `EPHE_OPENAI_COMPAT_BASE_URL` (+ model); an explicit `EPHE_MODEL_PROVIDER` without `EPHE_MODEL` is a configuration error that names the missing variable, not a request to fill one in. Explicit `--api-url` selects the engine; `--model` names the tag inside the chosen engine and never selects one — `ephe start --model <tag>` without a saved engine still opens in setup mode. A key is never written to `engine.json`. `ephe configure` and the app keep it in the OS keychain, with `~/.ephe/engine.key` (0600) as the fallback, and bind it to the engine through `engine.key.binding.json`; an exported `EPHE_OPENAI_COMPAT_API_KEY` stays the caller's own choice for that process. Template for an OpenAI-compatible / vLLM endpoint: `engine.example.json`, `.env.example`.

## Connection test

The Settings → Engine tab and the first-run screen show the active engine and probe it through the health endpoint, which distinguishes `ok` / `busy` (engine answers slowly — model loading, GPU busy) / `unreachable` (engine is down).

## Approval gates

`ephe tool <name>` runs a single tool deterministically (no LLM loop) with conservative approval defaults:

- `SAFE` tools (read-only) → always allowed
- `MUTATING` / `NETWORK` tools → require explicit approval
- `--dry-run` → preview without execution (file stays untouched)
- `--yes` → explicit approval
- `--no` → explicit denial (tool will not run)
- `--json` → machine-readable JSON output

## Exit codes

Exit codes: `0` success · `1` runtime/repair error, including a tool the approval policy blocks · `2` usage error.

---

Setup guides: [Local Image Engine](LOCAL_IMAGE_ENGINE.md) · [Offline Voice](VOICE.md) · [Skill Packs](SKILL_PACKS.md) · [Sandbox](SANDBOX_EXECUTION.md)
