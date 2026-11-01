# Install

Use the installer or Docker. Windows PowerShell installation is documented but has not been
verified end to end for this revision. The engine is chosen after install; the installer neither
installs Ollama nor pulls a model. Node 22.23.4 is the tested build runtime; the minimum below is
the installer's accepted floor, not evidence of a Node 20 build.

## Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | macOS 13+ · Ubuntu 22+ · Windows with PowerShell | macOS 14+ or a recent Linux |
| Python | 3.11 | 3.12+ |
| Node.js | 20 LTS with `npm` — **desktop/PWA mode only**, see the table below | 22 LTS |
| Ollama | User-managed; the installer only detects it | Latest stable |
| RAM | 8 GB for a small local tag | 16 GB+ for a local 12B-class tag, or a remote endpoint |
| Storage | 12 GB free | 20 GB+ |

What each mode needs, beyond the OS:

| Mode | Python | Node.js | What the installer installs |
|---|---|---|---|
| CLI (`--cli`, `EPHE_MODE=cli`) | 3.11+ — uv provides one if the machine has none, otherwise the distro package | not needed; the TUI has no frontend build | `.[tui]` only |
| Desktop / PWA (default) | 3.11+ | **20 LTS with `npm` (or `pnpm`)** — the PWA is built with it, and the installer does not install Node.js for you | `.[gui,voice]` plus the built PWA |

Desktop is the default, and a piped `curl … | bash` has no terminal, so it never asks: it takes
Desktop and therefore needs Node.js. On a box without Node.js the install stops at
`npm is missing — Node.js/npm is required for the PWA build`. Install Node.js first, or pass
`--cli` / `EPHE_MODE=cli` on a machine that is only meant to run the terminal UI.

## One-command installer

### macOS and Linux

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.5.2/install.sh | bash
```

From a checkout you already have:

```bash
./install.sh
```

The one-liner fetches `install.sh` from the public `v0.5.2` tag. The fetch answers HTTP 200; the
checkout path above is the alternative for reading the script before it runs.

For the end-to-end first-run walkthrough — install, the engine choice (hosted API key or local
Ollama runtime), and the first answer — see [FIRST_RUN.md](FIRST_RUN.md).

A piped run has no TTY, so it cannot ask for a mode and takes Desktop — which needs Node.js (see
[Requirements](#requirements)). For a CLI-only install from the one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.5.2/install.sh | bash -s -- --cli
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/bemlerlabs/ephe/v0.5.2/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
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

`install.ps1` defaults to `~/Documents/Ephe/.venv` and edits no PowerShell profile, so `ephe` is
not on your `PATH` in a fresh window. Activate the environment first. For a checkout or custom
installation, use that folder's `.venv` instead of the default below:

```powershell
& "$HOME\Documents\Ephe\.venv\Scripts\Activate.ps1"
ephe configure    # choose the engine once (saved to ~/.ephe/engine.json)
ephe doctor       # check Ollama, model and server state
ephe tui          # CLI mode: start the terminal UI
ephe start --open # desktop mode: start the local app, then open http://127.0.0.1:8765
```

## Installer options

### Modes

| Mode | Flag | Needs | Installs | Starts |
|---|---|---|---|---|
| Desktop / PWA (default) | `--desktop` (`--gui`, `--web`, `--pwa`) | Python 3.11+ and Node.js 20+ with `npm` (or `pnpm`) | `.[gui,voice]` plus the built PWA | `ephe start --open` |
| CLI | `--cli` (`--headless`, `--tui`) | Python 3.11+ only | `.[tui]` only | `ephe tui` |

`--no-start` installs without launching anything. `--dry-run` prints the plan without changing
anything. The Bash installer defaults to Desktop; choose `--cli` or `EPHE_MODE=cli` for
terminal-only use. The default piped installation needs Node.js.
Windows uses `-Cli` and `-Desktop` for these modes.

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
| `EPHE_UV_INSTALL_SHA256` | the pinned hash | Override only with an independently verified checksum; the mismatch warning alone is not a trusted source |

Windows equivalents: the same `EPHE_*` variables, or the switches `-InstallDir`, `-Port`, `-Cli`,
`-Desktop`, `-NoStart`, `-DryRun`.

### Supply-chain integrity

`install.sh` checks the downloaded uv installer against a pinned SHA256 before execution.
A mismatch leaves that script unexecuted and continues on the distro interpreter path.
Keep this fallback unless you independently verify an updated checksum from a trusted source.
Do not copy the mismatching download's own hash into the trusted pin.

This check covers the uv installer, not every downstream download. Windows can install Python
through winget and resolves packages through pip. Both installers pin the pip bootstrap wheel
by version and hash.

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

`install.sh` puts one launcher on your `PATH` (`~/.local/bin/ephe`) and replaces an older
launcher at the same path, so a fresh terminal answers `ephe` directly:

```bash
ephe configure    # choose the engine from the shell (optional: the app asks on first run)
ephe doctor       # check engine, model and server state
ephe tui          # CLI mode: the terminal app
ephe start --open # desktop mode: start the local app, then open http://127.0.0.1:8765
```

No engine is needed for the first start: the terminal app opens its own setup (provider,
endpoint, API key, model) and sends nothing until you choose one.

If `~/.local/bin` is not on your `PATH`, the installer prints the one `export` line. If no
launcher could be placed at all, it prints the activation line instead:

```bash
source ~/Documents/Ephe/.venv/bin/activate
```

Without either, a bare `ephe` answers `command not found`.

```bash
ephe doctor --fix      # apply safe local repairs
ephe update            # repo pull and dependencies; models stay your choice
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
`engine.key` (the engine choice and its key, bound by `engine.key.binding.json`), `memory/`, `sessions/`, `artifacts/`, `changesets/`,
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
the dated host-exec boundary review.

## MCP server boundary

A stdio MCP server is a child process the model can choose. Ephe starts it only under an
OS filesystem boundary:

- **macOS**: a Seatbelt profile denies reads of the user's whole home, re-opens only the
  child's own home, and allows writes only in that home and the temp directory. The
  interpreter prefixes (the running Ephe venv and the command's resolved install prefix)
  are the measured read exceptions; without them the deny also refuses the interpreter
  that runs the child.
- **Linux**: bubblewrap (`bwrap`) with a read-only root, the user's home, `/run/user/<uid>`
  and a config root outside the home replaced by empty tmpfs mounts, and only the child
  home bound back in.
- **Windows**: this build provides no filesystem boundary, so a stdio MCP server is
  refused with `-32006` and is not started.

Without a boundary there is no child, and the two failure shapes are distinguishable:

- **`bwrap` missing** (or no Seatbelt): the call returns `-32006`, "MCP server needs a
  filesystem boundary", and the audit says `mcp_child decision=refused
  os_boundary=unavailable`. Install `bubblewrap`.
- **`bwrap` installed but the kernel refuses user namespaces**: the spawn raises and the
  call returns `-32005`, "stdio spawn failed", with `decision=spawn_failed
  os_boundary=bubblewrap`. Ubuntu 24.04 ships
  `kernel.apparmor_restrict_unprivileged_userns=1` and no bwrap profile, so this is the
  state to expect there. Check it with `bwrap --dev-bind / / true`; `setting up uid map:
  Permission denied` means namespaces are denied. Permit them for the bwrap binary (an
  AppArmor profile) or run Ephe where Seatbelt is available.

A connector marked trusted in code is the one exception to the boundary; the spawn writes
an `mcp_child` line with `decision=trusted`. There is no user-facing switch for it today:
every connector configured through `mcp.json` or `EPHE_MCP_SERVERS` is subject to the rules
above, and nothing falls back to a raw spawn.
