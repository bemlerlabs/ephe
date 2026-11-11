# Install Options

Every install path the project ships, the flags and environment variables that steer it, and the way
back out. Sibling reference: [`INSTALL.md`](INSTALL.md).

| Path | Command | For |
|---|---|---|
| Existing checkout | `./install.sh` | the default first run, macOS and Linux |
| macOS app (DMG) | the `.dmg` from the GitHub release, then right-click → Open | a prebuilt app, no toolchain |
| Windows (PowerShell) | the one-liner under [Windows PowerShell](#windows-powershell-one-liner) | Windows, with or without a checkout |
| Docker | `docker compose up` | development and advanced setups |

## Existing Checkout

```bash
./install.sh
```

## macOS App (DMG)

The packaged `.app` is released as `Ephe_<version>_aarch64.dmg` on the
[GitHub releases page](https://github.com/bemlerlabs/ephe/releases). It is ad-hoc signed and Apple
has not notarized it, which is the normal state for a build anyone can reproduce from source, so
the first launch is right-click → Open, System Settings → Privacy & Security → **Open Anyway**, or
the scripted `xattr -d com.apple.quarantine` — all three are in
[`INSTALL.md`](INSTALL.md#the-macos-app-dmg) together with the reason macOS asks. The Homebrew
cask applies the `xattr` line in its postflight, so `brew install --cask` opens without a prompt.

No Apple account and no notarization step is involved in this path; that is the default and a
supported one.

## Windows PowerShell (One-Liner)

This path has not been verified end to end on Windows for this revision.

```powershell
irm https://raw.githubusercontent.com/bemlerlabs/ephe/v0.6.4/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Or run it straight from a local checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

A release ships no Windows binary — macOS and Linux artifacts only — so this source install is the
only Windows path: it fetches the tag archive and builds on the machine, and the gate is
PowerShell's execution policy rather than a code signature (see the artifact list in
[`INSTALL.md`](INSTALL.md#windows-powershell)).

On Windows, choose `-Cli` for the terminal interface or `-Desktop` for the web app and voice.
On macOS and Linux, Bash defaults to Desktop; choose `--cli` or `EPHE_MODE=cli` for terminal-only use.

## Docker

```bash
docker compose up          # then open http://localhost:8765
```

Docker is available for development and advanced users; the primary first-run path is the
one-command installer above. **Both ports are published on the host's loopback interface only**
(`127.0.0.1:8765` and `127.0.0.1:11434`), so nothing on your network can reach the container until
you decide otherwise.

Without Compose, keep the same posture explicitly:

```bash
docker run --rm -p 127.0.0.1:8765:8765 ephe:latest
```

Mobile or LAN access is an opt-in; it is off by default. To open it, publish on all interfaces and let the
pairing token guard the API — `EPHE_LAN` is already set in the Compose file, and any non-loopback
bind forces it:

```bash
EPHE_PUBLISH_HOST=0.0.0.0 docker compose up   # then scan the in-app QR code
```

## Uninstall

`uninstall.sh` is the way back out. It removes the checkout in `EPHE_INSTALL_DIR` (default
`$HOME/Documents/Ephe`), the state tree in `~/.ephe` — sessions, memory, artifacts, change sets and
the engine key — and the desktop app's own state under `$HOME/Library` (`Application Support`,
`WebKit` and `Caches`, each under the bundle identifier `com.ephe.ephe`). It refuses when a path is
a filesystem root, your home directory or an ancestor of it, a top-level directory, not an Ephe
checkout, or a bundle identifier that is not one, so an `EPHE_INSTALL_DIR=/` cannot reach `rm -rf
/`:

```bash
./uninstall.sh --dry-run     # list what would go, remove nothing
./uninstall.sh --keep-data   # drop the checkout, keep the state tree and the Library state
./uninstall.sh --yes         # remove all of it, the state tree and the Library state included
```

The checkout is reconstructible from git, the state tree is not: without `--yes` the data tree and
the `~/Library` state go only after a prompt, and a non-interactive run keeps them and prints the
one command that removes them. Nothing outside those paths is touched, Ollama and its models
included, and the run ends by naming what it left behind.

## What the installer does

The installer targets `~/Documents/Ephe`, prepares Python, builds the PWA, checks whether a local
Ollama is already available (informational only — it never installs or pulls anything), starts the
local server, and opens:

```text
http://127.0.0.1:8765
```

On first run you pick the engine in the app: local Ollama (bring your own models), remote Ollama, or
an OpenAI-compatible endpoint (e.g. a DGX Spark — no download, no install). Which tag runs inside the
engine is your choice and Ephe never makes it: nothing is sized from this machine's RAM, nothing is
pulled for you, and no model is treated as the default. A local Ollama tag needs the memory its own
size asks for — around 16 GB unified memory for a 12-billion-parameter model, less for a smaller one,
none for a remote endpoint.

**Installer checks:** the Bash installer checks the downloaded uv installer against a pinned SHA256.
A mismatch leaves it unexecuted and selects the distro interpreter fallback. Change
`EPHE_UV_INSTALL_SHA256` only after independent verification; the observed hash alone is not trusted.
This check does not cover every downstream download. Windows uses winget/pip; both installers
separately hash-pin the pip bootstrap wheel.

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | macOS 13+, Ubuntu 22+, Windows with the PowerShell path | macOS 14+ or recent Linux |
| Python | 3.11 | 3.12+ |
| Ollama | User-managed (the installer only detects it) | Latest stable |
| RAM | 8 GB for a small local tag | 16 GB+ for a local 12B-class tag — or a remote endpoint, which needs none |
| Storage | 12 GB free | 20 GB+ |

<!-- Declared source of truth for the interpreter version: `.python-version` (value: 3.13). -->
