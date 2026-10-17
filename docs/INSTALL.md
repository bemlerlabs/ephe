# Install

Two supported paths: the one-command installer (macOS, Linux, Windows) and Docker. The AI engine is
chosen in the app after install — the installer does not install Ollama and does not pull any model.

## Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | macOS 13+ · Ubuntu 22+ · Windows with PowerShell | macOS 14+ or a recent Linux |
| Python | 3.10 | 3.12+ |
| Node.js | 20 LTS with `npm` — **desktop/PWA mode only**, see the table below | 22 LTS |
| Ollama | User-managed; the installer only detects it | Latest stable |
| RAM | 8 GB for a small local tag | 16 GB+ for a local 12B-class tag, or a remote endpoint |
| Storage | 12 GB free | 20 GB+ |

What each mode needs, beyond the OS:

| Mode | Python | Node.js | What the installer installs |
|---|---|---|---|
| CLI (`--cli`, `EPHE_MODE=cli`) | 3.10+ — uv provides one if the machine has none, otherwise the distro package | not needed; the TUI has no frontend build | `.[tui]` only |
| Desktop / PWA (default) | 3.10+ | **20 LTS with `npm` (or `pnpm`)** — the PWA is built with it, and the installer does not install Node.js for you | `.[gui,voice]` plus the built PWA |

Desktop is the default, and a piped `curl … | bash` has no terminal, so it never asks: it takes
Desktop and therefore needs Node.js. On a box without Node.js the install stops at
`npm is missing — Node.js/npm is required for the PWA build`. Install Node.js first, or pass
`--cli` / `EPHE_MODE=cli` on a machine that is only meant to run the terminal UI.

## One-command installer

### macOS and Linux

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

From a checkout you already have:

```bash
./install.sh
```

The one-liner fetches `install.sh` from the published repository. While the repository is not yet
public an anonymous fetch answers HTTP 404, so install from a checkout you have access to instead.

For the end-to-end first-run walkthrough — install, the engine choice (hosted API key or local
Ollama runtime), and the first answer — see [FIRST_RUN.md](FIRST_RUN.md).

A piped run has no TTY, so it cannot ask for a mode and takes Desktop — which needs Node.js (see
[Requirements](#requirements)). For a CLI-only install from the one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash -s -- --cli
```

### Windows (PowerShell)

```powershell
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.ps1 -o install.ps1; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

From a checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Switches mirror the environment: `-InstallDir`, `-Port`, `-Cli`, `-Desktop`, `-NoStart`, `-DryRun`,
`-Help`. `-DryRun` (or `EPHE_DRY_RUN=1`) prints the plan and changes nothing, `EPHE_MODE` selects the
mode from the environment, and a bad `EPHE_PORT` or `EPHE_MODE` is refused with exit 2 before the
first step — the same pre-flight `install.sh` runs. Without a mode switch the installer asks
interactively when a console is available (Desktop is the default).

The installer targets `~/Documents/Ephe`, prepares Python, builds the PWA (desktop mode only — that
step needs Node.js, which the installer does not install), reports whether a local Ollama is already
available (informational only), starts the local server, and opens:

```text
http://127.0.0.1:8765
```

On first run you pick the engine in the app: local Ollama (bring your own models), remote Ollama, or
an OpenAI-compatible endpoint. Nothing is sized from this machine's RAM, nothing is pulled for you,
and no model is treated as a default.

`install.ps1` installs into `~/Documents/Ephe/.venv` and edits no PowerShell profile, so `ephe` is
not on your `PATH` in a fresh window. Activate the environment first — the installer prints exactly
these lines when it finishes:

```powershell
.\.venv\Scripts\Activate.ps1
ephe configure    # choose the engine once (saved to ~/.ephe/engine.json)
ephe doctor       # check Ollama, model and server state
ephe tui          # CLI mode: start the terminal UI
ephe start --open # desktop mode: start the local app, then open http://127.0.0.1:8765
```

## Installer options

### Modes

| Mode | Flag | Needs | Installs | Starts |
|---|---|---|---|---|
| Desktop / PWA (default) | `--desktop` (`--gui`, `--web`, `--pwa`) | Python 3.10+ and Node.js 20+ with `npm` (or `pnpm`) | `.[gui,voice]` plus the built PWA | `ephe start --open` |
| CLI | `--cli` (`--headless`, `--tui`) | Python 3.10+ only | `.[tui]` only | `ephe tui` |

`--no-start` installs without launching anything. `--dry-run` prints the plan without changing
anything. With no flag, the installer asks interactively (Desktop is the default) when a terminal is
available — without a terminal it does not ask at all and simply takes Desktop, so a piped
`curl … | bash` needs Node.js.

### Environment variables

| Variable | Default | Effect |
|---|---|---|
| `EPHE_INSTALL_DIR` | `~/Documents/Ephe` | Target directory |
| `EPHE_PORT` | `8765` | Server port |
| `EPHE_MODE` | `desktop` | `cli` or `desktop`, the env form of the mode flags |
| `EPHE_NO_START` | `0` | `1` installs without starting |
| `EPHE_DRY_RUN` | `0` | `1` prints the plan, changes nothing |
| `EPHE_REPO_URL` | the project Git URL | Clone source |
| `EPHE_OLLAMA_HOST` | `127.0.0.1:11434` | Where a local Ollama is detected |
| `EPHE_UV_INSTALL_SHA256` | the pinned hash | Override the pinned uv installer hash — set it to the live hash the mismatch warning prints |

Windows equivalents: the same `EPHE_*` variables, or the switches `-InstallDir`, `-Port`, `-Cli`,
`-Desktop`, `-NoStart`, `-DryRun`.

### Supply-chain integrity

Every vendor download (uv) is verified against a pinned SHA256 hash before execution, so a
compromised vendor script is never run. A mismatch does **not** abort the install: `install.sh`
prints the pinned hash and the live hash, does not execute the fetched script, and continues on the
distro interpreter path — so a bare box (no Python, no uv) still reaches an interpreter instead of
stopping at the gate. The uv installer is rotated often enough that the old hard abort was a launch
blocker. If you see the warning, set `EPHE_UV_INSTALL_SHA256` to the live hash it printed and re-run
`./install.sh` to use uv again.

### When a step fails

`install.sh` refuses a bad environment before the first step: an `EPHE_PORT` outside 1–65535 or an
`EPHE_MODE` other than `cli`/`desktop` prints the offending value and exits 2. Any later failing
command prints `install.sh failed at line N: <command>` before the shell stops, so a first run is
diagnosable from its own output. A `--dry-run` from outside a checkout reports the clone it would
run and creates nothing. A failed update of an existing checkout warns and continues on the version
on disk instead of aborting. A uv installer whose pinned hash no longer matches is reported with both
hashes and does not stop the install (see [Supply-chain integrity](#supply-chain-integrity)) — a
vendor rotation is not a failure of the install.

`install.ps1` runs the same `EPHE_PORT`/`EPHE_MODE` pre-flight (exit 2, naming the offending value)
and reports the failing step; a failed update of an existing checkout warns and continues, as above.

## Docker

```bash
docker compose up          # then open http://localhost:8765
```

Both ports are published on the host loopback only (`127.0.0.1:8765` and `127.0.0.1:11434`), so
nothing on your network can reach the container until you decide otherwise. The image brings its own
Python and Node.js, so the mode-specific requirements above do not apply to the host. Without
Compose, keep the same posture explicitly:

```bash
docker run --rm -p 127.0.0.1:8765:8765 ephe:latest
```

LAN or mobile access is an opt-in: `EPHE_LAN` is set in the Compose file, and any non-loopback bind
forces it, so the pairing token guards the API:

```bash
EPHE_PUBLISH_HOST=0.0.0.0 docker compose up   # then scan the in-app QR code
```

## After install

`install.sh` installs into `~/Documents/Ephe/.venv` and edits no shell rc, so `ephe` is not on your
`PATH` in a fresh terminal. Activate the environment first — the installer prints exactly these
lines when it finishes:

```bash
source ~/Documents/Ephe/.venv/bin/activate
ephe configure    # choose the engine once (saved to ~/.ephe/engine.json)
ephe doctor       # check Ollama, model and server state
ephe tui          # CLI mode: start the terminal UI
ephe start --open # desktop mode: start the local app, then open http://127.0.0.1:8765
```

`source` applies to the shell it runs in, so repeat it in every new terminal (or put
`~/Documents/Ephe/.venv/bin` on your `PATH` yourself). Without it a bare `ephe` answers
`command not found` — the commands below all assume the environment is active:

```bash
ephe doctor --fix      # apply safe local repairs
ephe update            # repo pull, dependencies, and model
```

Explicit `--model` and `--api-url` flags always override the persisted choice. See the
[README](../README.md) for the full CLI reference and Docker/desktop notes.

## Uninstall

`uninstall.sh` in the repository root is the way back out. It removes two trees and nothing else:
the checkout in `EPHE_INSTALL_DIR` (default `~/Documents/Ephe`) and the state tree in
`EPHE_CONFIG_DIR` (default `~/.ephe`).

```bash
./uninstall.sh --dry-run     # list both trees with size and file count, remove nothing
./uninstall.sh --keep-data   # remove the checkout, keep ~/.ephe
./uninstall.sh --yes         # remove both without asking about the data tree
```

The checkout is reconstructible from git; `~/.ephe` is not. It holds `engine.json` and
`engine.key` (the engine choice and its key), `memory/`, `sessions/`, `artifacts/`, `changesets/`,
`workspaces/` and `bench/`, so without `--yes` the data tree is removed only after a prompt, and a
non-interactive run without `--yes` keeps it and prints the command that removes it. A run always
ends by naming what it left behind, the engine key inside the OS keychain and an `ephe` that came
from somewhere else included.

The script refuses — exit 2, nothing removed — when either path is a filesystem root, your home
directory or an ancestor of it, a top-level directory such as `/tmp`, a path the other tree sits
inside, or a directory that carries no Ephe markers (`pyproject.toml`, `app/src`,
`run_server.py`). `--force` overrides the marker check for a damaged checkout; it does not override
the path guards. Ollama and its models are never touched, because `install.sh` never installed
them.

## Host shell sandbox

Confirmed shell commands run under an OS sandbox only where one exists.

On macOS the opt-in Seatbelt sandbox (Settings → Security) wraps them in `sandbox-exec`:
writes are limited to the workspace, the system temp directory and `$HOME`, and the network
is denied.

On Linux there is no OS wrapper. The toggle has no effect and the command runs with your
user's rights; the shell audit line records it as `sandbox-unavailable`. If you want
isolation, start the server with `EPHE_SHELL_BACKEND=docker` — confirmed commands then run
inside a container that mounts only your workspace at `/workspace`. Two limits apply: the
container keeps the Docker daemon's default network and user, and the interactive terminal
panel still runs on the host. The boundary review is
[HOST_EXEC_BOUNDARY_REVIEW_2026-10-11.md](HOST_EXEC_BOUNDARY_REVIEW_2026-10-11.md).
