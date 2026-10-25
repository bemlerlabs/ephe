# Ephe CLI — `ephe` Reference

All subcommands of the local CLI (entry point `ephe`, alias `ephe`). Global flags: `--help` and `--version`. Every other flag belongs to the subcommand that declares it: `--model <name>` (the model **inside** the chosen engine — a model name is not an engine choice) is a flag of `start`, `web`, `tui`, `doctor`, `code`, `run`, `goal` and `serve`, and `--port <n>` is a flag of `start`, `web`, `doctor` (default 8765) and `serve` (default 8766).

Engine resolution applies to every model run and has no silent default: the persisted
`~/.ephe/engine.json` → an explicit engine env (`EPHE_MODEL_PROVIDER` + endpoint) →
interactive onboarding (only on a TTY) → abort with instructions (`ephe configure`). This
also covers the headless runs `ephe code`, `ephe goal` and `ephe serve` (I2-2), and since
2026-10-11 `ephe start` too: without a chosen engine it spawns the server with **no engine
env**, so `run_server.py` enters setup mode, `EPHE_SETUP_MODE` is set and the chat stays
closed until the Setup page persists a choice. It used to apply a placeholder
`local_ollama` engine with a tag taken from the code (`ephe_cli.py:606-611`), which made
the server look configured, left the chat's fail-closed gate disarmed and answered a first
turn for a model the user never picked — closed defect.

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

## `ephe doctor [--fix] [--json]`
Diagnoses the local setup: Python, project files, Ollama CLI/service, model (installed + load test), server health, the **image endpoint** (R16, informational) and **voice (TTS)** (R18, informational).
The model line covers a tag that exists: `--model`, else `EPHE_MODEL`, else the persisted local-Ollama choice. With none of them it reports `no model chosen` and names the way out instead of probing a model nobody picked.
`--fix` repairs the safe drift: repo fast-forward, dependencies (`.[gui,voice]`), Ollama service + model, PWA build. The model repair follows the same rule — no tag, nothing pulled.

## `ephe update [--model <name>] [--json]`
Repo fast-forward, dependencies, model pull (ollama), installer invocation. Without `--model` and without `EPHE_MODEL` no model is passed to the installer: `ephe update` names no tag on the user's behalf.
`--json` writes one document to stdout (`{"ok": bool, "exit_code": n}`); the prose `git pull` and the installer print goes to stderr, so a consumer can pipe the output straight into a parser.

## `ephe voice list | install <voice>...`
R18 — manage local Piper voices:
- `list`: binary status (`brew install piper`) + installed voices (`~/.ephe/voices/`)
- `install en_US-amy-medium`: downloads the `.onnx` + `.onnx.json` from HuggingFace (opt-in, 200-MB cap)

## `ephe tui`
Textual TUI (terminal mode, extra `.[tui]`). Engine resolution as above. `--model <tag>` overrides the model inside the chosen engine — a model name is not an engine choice. `--api-url <url>` picks an OpenAI-compatible engine explicitly and needs a tag from `--model` or `EPHE_OPENAI_COMPAT_MODEL`; with neither it fails closed and names that variable.

## `ephe configure [--force]`
Store the engine choice once (a preset or your own endpoint). The choice lands in
`~/.ephe/engine.json`; API keys are **never** persisted, only set as session env.
`--force` re-selects even when a config already exists.

## `ephe code "<task>"`
Coding agent in the workspace: read → edit → verify with `run_tests`, every
mutating step behind an approval gate and in the audit. Needs a chosen engine (I2-2).
Batch: the answer is printed at the end and an optional `--json` / `--run-record <path>`
carries exactly one machine-readable run record.

## `ephe run "<task>"`
The interactive sibling of `ephe code`: the same coding loop, but every phase, tool call
and answer token **streams to the terminal as it happens**. The turn is kept in a session
(printed at the end), so `--resume <session>` continues the same thread, and the
workspace's diff is recorded as a change set whose id the printout hands to
`ephe show` / `ephe review` / `ephe publish`. Needs a chosen engine (I2-2).
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

## `ephe serve [--host <h>] [--port <p>] [--lan] [--token <t>]`
OpenAI-compatible engine (`/v1/chat/completions`, `/v1/models`) for other coding CLIs.
Binds only to localhost by default; `--lan` generates an auth token. The engine it passes
through is the chosen one — without a choice the server does not start (I2-2).

## `ephe tool <name> [--arg k=v ...] [--dry-run]`
Run a single tool directly (e.g. `ephe tool generate_image --arg prompt="…" --dry-run`). `generate_image` ships in the **image-studio** plugin: with that switch off (Settings → Plugins) the tool is not offered at all, `ephe tool generate_image` fails naming the tools that are, and `ephe tool --help` prints that same list.

## `ephe session`
Manage sessions (list/show the local `~/.ephe/sessions/`). Creating one takes a flag: `ephe session new --title "My project"` — the parser accepts no positional title, and the hint an empty list prints names that form.

## `ephe plugin list [--json] | enable <id> | disable <id> | install <id>`
`ephe plugin list` prints the table of known plugins; `--json` emits `{"plugins": [{"name", "enabled", "version"}]}` instead, sorted by name.

## `ephe completion <shell>`
Shell completion (bash/zsh/fish).

## Command map

Three entry points, one codebase:

```bash
ephe --version                 # the version of this checkout (pyproject [project].version)
ephe --help                    # all subcommands, examples, exit codes
ephe start --open              # start the local web app + open browser (port 8765)
ephe desktop                   # build, install to /Applications and open (Tauri); --dev = live shell, --no-install = keep the build copy
ephe configure                 # choose the engine once (saved to ~/.ephe/engine.json)
ephe configure --force         # change the engine later
ephe start --lan               # LAN binding for QR mobile pairing
ephe start --model <tag>       # name the tag your engine serves
ephe doctor                    # setup check (Ollama, model, server)
ephe doctor --fix              # safe local repairs (repo, deps, Ollama, model)
ephe doctor --json             # machine-readable health report
ephe update                    # repo pull + dependencies + model
ephe tui                       # terminal UI (Textual) — uses the configured engine
ephe tui --model <tag>         # TUI on a tag you named yourself
ephe tui --configure           # force the engine selection dialog
ephe serve                     # OpenAI-compatible engine (/v1/chat/completions)
ephe memory-mcp                # serve this workspace's memory over MCP on stdio (read-only)
ephe memory-mcp --allow-write  # …and let the connected agent correct facts
ephe tool <name> --dry-run     # run a tool deterministically (approval gate)
ephe run "fix the failing test" # agent run in the terminal — streams live, resumable
ephe run --resume <session> "…" # continue a saved run where it stopped
ephe show <change-set>         # print a change set's diff, file by file
ephe session list|new|switch|rm|rename
ephe completion                # shell completion
```

A build writes `app/src-tauri/target/release/bundle/macos/Ephe.app`. That copy is not an install. `ephe desktop` moves the bundle to `/Applications` and deletes the build copy, and the update button rewrites the installed bundle in place. Start the app from `/Applications`; a copy under `target/` is build output.

## Engine choice (no silent default)

`ephe configure` asks once which engine to use and stores the answer in `~/.ephe/engine.json`. `ephe start`, `ephe tui`, `ephe code`, `ephe goal`, `ephe run`, `ephe serve` and the server (`run_server.py`) all read that same choice — one source of truth. Without a saved choice and without an explicit engine env they never pick an engine in silence: the CLI paths stop with an actionable hint, the server starts in **setup mode on loopback** with the chat closed until a choice exists, and a LAN bind refuses to start outright. For scripted or headless setups use `EPHE_MODEL_PROVIDER=local_ollama|custom_ollama|openai_compatible` plus the matching `EPHE_LOCAL_OLLAMA_BASE_URL` / `EPHE_CUSTOM_OLLAMA_BASE_URL` / `EPHE_OPENAI_COMPAT_BASE_URL` (+ model); an explicit `EPHE_MODEL_PROVIDER` without `EPHE_MODEL` is a configuration error that names the missing variable, not a request to fill one in. Explicit `--api-url` selects the engine; `--model` names the tag inside the chosen engine and never selects one — `ephe start --model <tag>` without a saved engine still opens in setup mode. API keys are never stored; a key is only read from `EPHE_OPENAI_COMPAT_API_KEY`. Template for an OpenAI-compatible / vLLM endpoint: `engine.example.json`, `.env.example`.

## Connection test

the Settings → Engine tab and the first-run screen show the active engine and probe it through the health endpoint, which distinguishes `ok` / `busy` (engine answers slowly — model loading, GPU busy) / `unreachable` (engine is down).

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
