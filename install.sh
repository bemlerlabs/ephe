#!/usr/bin/env bash
set -euo pipefail
# `-E` (errtrace): the ERR trap installed below is NOT inherited by shell
# functions without it, and nearly every step runs through `run()`. Without
# `-E` a failing dependency install printed only the tool's own error and no
# "failed at line N" line, while docs/INSTALL.md promises exactly that line.
set -E

GREEN='\033[0;32m'
DIM='\033[2m'
BOLD='\033[1m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

REPO_URL="${EPHE_REPO_URL:-https://github.com/bemlerlabs/ephe.git}"
INSTALL_DIR="${EPHE_INSTALL_DIR:-$HOME/Documents/Ephe}"
PORT="${EPHE_PORT:-8765}"
LOCAL_OLLAMA_HOST="${EPHE_OLLAMA_HOST:-127.0.0.1:11434}"
LOCAL_OLLAMA_URL="$LOCAL_OLLAMA_HOST"
if [[ "$LOCAL_OLLAMA_URL" != http://* && "$LOCAL_OLLAMA_URL" != https://* ]]; then
  LOCAL_OLLAMA_URL="http://${LOCAL_OLLAMA_URL}"
fi
NO_START="${EPHE_NO_START:-0}"
DRY_RUN="${EPHE_DRY_RUN:-0}"

# --- Download integrity (supply-chain gate) ---------------------------------
# Piped `curl | sh` is a classic supply-chain attack point: a compromised vendor
# script would be executed unchecked. So we first download the uv installer
# (Python runtime), verify its SHA256 against the pinned hash, and only then run
# it. On a mismatch the fetched script is NOT run — but the install does not
# abort: uv rotates this script often, and a hard abort here used to strand a
# bare box (no Python, no uv) before the distro interpreter branch below it. The
# caller reports both hashes and falls through to that branch instead.
# Hash as of: 2026-10-12 (captured live, stable across two fetches). Rotation via
# the env override.
# Note: the installer does NOT install Ollama (mandate 2026-08-21) — that is why
# this script deliberately has no Ollama download/hash anymore.
UV_INSTALL_SHA256="${EPHE_UV_INSTALL_SHA256:-283cbef4bdaca819bd896b0dacb8a085c4c05dbc880642aa5001d97bc4db74ba}"

for arg in "$@"; do
  case "$arg" in
    --no-start) NO_START=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --cli|--headless|--tui) INSTALL_MODE="cli" ;;
    --desktop|--gui|--web|--pwa) INSTALL_MODE="desktop" ;;
    --help|-h)
      echo "Usage: ./install.sh [--no-start] [--dry-run] [--cli|--desktop]"
      echo "Env: EPHE_INSTALL_DIR, EPHE_PORT, EPHE_NO_START, EPHE_DRY_RUN"
      echo ""
      echo "Ephe — one-command install. The AI engine is chosen in the app"
      echo "(local Ollama or an external endpoint such as DGX)."
      echo "Ollama is NOT installed and NO models are downloaded."
      echo ""
      echo "Modes:"
      echo "  --cli      Minimal CLI path: installs only the TUI (textual), starts 'ephe tui'"
      echo "  --desktop  (default) Desktop/PWA: installs gui+voice, starts 'ephe start --open'"
      echo ""
      echo "Without a flag the installer asks interactively when a terminal is available."
      exit 0
      ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# Mode selection: flag > env > interactive > default(desktop)
if [[ -z "${INSTALL_MODE:-}" ]]; then
  if [[ -n "${EPHE_MODE:-}" ]]; then
    INSTALL_MODE="$EPHE_MODE"
  elif [[ -t 0 && -z "${NO_START:-}" && -z "${DRY_RUN:-}" ]]; then
    read -r -p "How do you want to use Ephe? [D]esktop/PWA, [C]li (TUI), or [S]kip start: " choice
    choice="${choice:-D}"
    case "$choice" in
      [Cc]) INSTALL_MODE="cli" ;;
      [Ss]) NO_START=1; INSTALL_MODE="desktop" ;;
      *) INSTALL_MODE="desktop" ;;
    esac
  else
    INSTALL_MODE="desktop"
  fi
fi

# --- Refuse a bad environment before any step runs --------------------------
# A wrong EPHE_PORT used to reach the app's own argument parser and an unknown
# EPHE_MODE used to fall through to the desktop branch, so both are checked here,
# where the message can still name the variable that was wrong.
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( 10#$PORT < 1 || 10#$PORT > 65535 )); then
  echo "EPHE_PORT must be a port number between 1 and 65535, got '${PORT}'." >&2
  exit 2
fi
case "${INSTALL_MODE:-desktop}" in
  cli|desktop) ;;
  *) echo "EPHE_MODE must be 'cli' or 'desktop', got '${INSTALL_MODE}'." >&2; exit 2 ;;
esac

step() { echo -e "${GREEN}▶${NC} ${BOLD}$1${NC}"; }
info() { echo -e "  ${DIM}$1${NC}"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
ok() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1" >&2; exit 1; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "  DRY-RUN: $*"
  else
    "$@"
  fi
}

# Package managers are called as root only when the shell is not already root: a
# stock `ubuntu:24.04` (and any minimal image) ships no `sudo` binary, so
# `sudo apt-get …` answered "command not found" and `set -e` stopped a bare box
# that was already root — which is exactly the clean-room shape.
as_root() {
  if [[ "$(id -u)" == "0" ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

# --- First-run diagnosability -----------------------------------------------
# `set -e` stops on the first failing command but names neither the line nor the
# command, so a failed one-command install ended in silence. The ERR trap prints
# both before the shell exits; the EXIT trap removes a vendor temp file even when
# the run is interrupted between its download and its cleanup.
#
# The line it prints is the CALL SITE, not the line inside the helper that
# stopped. Nearly every step runs through `run()`/`as_root()`, so the trap's own
# `$LINENO` named the helper's body instead of the step: every failure in this
# script pointed at run()'s `"$@"` — measured 2026-10-15, a failed
# `run git clone …` reported run()'s own line while the clone sits ~100 lines
# away. BASH_LINENO[i] holds the line where FUNCNAME[i] was called and FUNCNAME's
# last entry is always `main`, so BASH_LINENO's outermost non-zero entry is the
# top-level line that started the failing chain — the line the reader wants; a
# failure with no helper frames falls back to `$LINENO`, which then names the
# command itself. `cmd`/`own` are captured in the trap's FIRST commands because a
# command after them resets `$BASH_COMMAND` (measured on bash 3.2, the macOS
# default), and `$LINENO` inside a function is the helper's definition line —
# hence the parenthetical naming the helper instead of a second line number.
# `n` is the plain array length, and the default the length used to carry is not
# missed: a length is never unset, so `:-1` never applied, while bash 4 and newer
# reject that spelling outright as a bad substitution — on the Ubuntu 24.04 leg the
# trap printed `bad substitution` and no diagnostic line at all.
EPHE_VENDOR_TMP=""
cleanup_temp() {
  if [[ -n "$EPHE_VENDOR_TMP" ]]; then
    rm -f "$EPHE_VENDOR_TMP"
  fi
}
# shellcheck disable=SC2154  # the ERR trap assigns cmd, own, line and note before reading them
trap 'cmd=$BASH_COMMAND; own=$LINENO; n=${#BASH_LINENO[@]}; i=$(( n > 2 ? n - 2 : 0 )); line=$(( ${BASH_LINENO[$i]:-0} ? ${BASH_LINENO[$i]} : own )); note=""; if (( line != own )); then note=" (inside ${FUNCNAME[0]}())"; fi; echo -e "  ${RED}✗${NC} install.sh failed at line $line: $cmd$note" >&2' ERR
trap cleanup_temp EXIT

# portable sha256 sum (macOS shasum / Linux sha256sum)
sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

# Downloads a vendor script, verifies the pinned SHA256 and then runs it.
# A mismatching hash => the script is NOT run and the function returns 3; the
# caller decides how to continue (the uv caller falls back to the distro
# interpreter, so a rolled vendor hash cannot strand a bare box). No blind
# `curl | sh` either way.
# $1=URL  $2=pinned_SHA256  $3=label  $4=env override name (for rotation)
fetch_verify_run() {
  local url="$1" expected="$2" label="$3" override_env="$4"
  local tmp got exp rc
  local tmpdir="${TMPDIR:-/tmp}"
  # The vendor script's exit status must reach the caller and the temp file must
  # go on every path: `sh "$tmp"` under `set -e` used to abort the shell before
  # the old cleanup line ran, leaving the download behind on the failing path.
  tmp="$(mktemp "$tmpdir/ephe-vendor-XXXXXX")" || fail "No temporary file for the ${label} installer."
  EPHE_VENDOR_TMP="$tmp"
  if [[ "$DRY_RUN" == "1" ]]; then
    info "DRY-RUN: loading+verifying ${label} from ${url} (SHA256=${expected})"
    rm -f "$tmp"; EPHE_VENDOR_TMP=""
    return 0
  fi
  info "Loading the ${label} installer …"
  curl -fsSL "$url" -o "$tmp" || { rm -f "$tmp"; EPHE_VENDOR_TMP=""; fail "Download failed: ${url}"; }
  if ! command -v shasum >/dev/null 2>&1 && ! command -v sha256sum >/dev/null 2>&1; then
    rm -f "$tmp"; EPHE_VENDOR_TMP=""
    fail "Neither shasum nor sha256sum is on PATH, so the ${label} download cannot be verified and will not be run."
  fi
  got="$(sha256_of "$tmp")"
  got="$(printf '%s' "$got" | tr 'ABCDEF' 'abcdef')"
  exp="$(printf '%s' "$expected" | tr 'ABCDEF' 'abcdef')"
  if [[ "$got" != "$exp" ]]; then
    rm -f "$tmp"; EPHE_VENDOR_TMP=""
    # Reported, not fatal. A rotated vendor hash must not strand a bare box
    # before it has any interpreter; both hashes are named so the pin can be
    # rotated straight from the output. Raw echo (no helper) so the message also
    # works when this function is extracted and run on its own.
    {
      echo -e "  ${YELLOW}⚠${NC} SHA256 integrity check FAILED for ${label} — the fetched script was NOT run."
      echo -e "      pinned: ${expected}"
      echo -e "      live:   ${got}"
      echo -e "      The vendor has probably rotated the script: set ${override_env} to the live sha256 and run ./install.sh again."
    } >&2
    return 3
  fi
  ok "Integrity of ${label} confirmed (SHA256 ${got:0:16}…)"
  if sh "$tmp"; then rc=0; else rc=$?; fi
  rm -f "$tmp"; EPHE_VENDOR_TMP=""
  return "$rc"
}

is_project_root() {
  [[ -f "pyproject.toml" && -d "app/src" && -f "run_server.py" ]]
}

echo ""
echo -e "${GREEN}${BOLD}Ephe offline-first installer${NC}"
echo -e "${DIM}One-command install. The AI engine is chosen in the app (local Ollama or an external endpoint).${NC}"
echo ""

if ! is_project_root; then
  step "Preparing the install folder"
  command -v git >/dev/null 2>&1 || fail "Git is missing. Install Git and run the command again."
  # An unauthenticated clone must fail here with a readable reason, not sit on a
  # username prompt nobody can answer: the documented one-liner points at a
  # repository a stranger has no access to, and the raw git error is
  # `fatal: could not read Username for 'https://github.com'` — no cause, no next
  # step. GIT_TERMINAL_PROMPT=0 makes the failure immediate in a terminal too.
  export GIT_TERMINAL_PROMPT=0
  # A dry run reports the clone it would run instead of creating folders for it.
  [[ "$DRY_RUN" == "1" ]] || mkdir -p "$(dirname "$INSTALL_DIR")"
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    ok "Existing repository found: $INSTALL_DIR"
    cd "$INSTALL_DIR"
    run git pull --ff-only || warn "Could not update the existing checkout (local changes or offline). Continuing with the version on disk."
  elif [[ -e "$INSTALL_DIR" ]]; then
    fail "$INSTALL_DIR already exists but is not a Git repository. Set EPHE_INSTALL_DIR to a different path."
  else
    if ! run git clone "$REPO_URL" "$INSTALL_DIR"; then
      echo "" >&2
      echo -e "  ${RED}✗${NC} Could not clone $REPO_URL" >&2
      echo -e "  ${DIM}The repository is private (or renamed), or this machine has no access to it.${NC}" >&2
      echo -e "  ${DIM}Next step: ask the repository owner for access, or point the installer at a checkout${NC}" >&2
      echo "  Licence: Business Source License 1.1 (BUSL-1.1) — see LICENSE in $INSTALL_DIR"
      echo -e "  ${DIM}you can reach: EPHE_REPO_URL=<clone URL> ./install.sh (a local path or file:// URL works).${NC}" >&2
      exit 1
    fi
    if [[ "$DRY_RUN" == "1" ]]; then
      ok "Dry run stops here: the clone was not created."
      exit 0
    fi
    cd "$INSTALL_DIR"
  fi
  exec bash ./install.sh "$@"
fi

PROJECT_DIR="$(pwd)"
OS_NAME="$(uname -s)"

step "Checking the system"
case "$OS_NAME" in
  Darwin|Linux) ok "$OS_NAME supported" ;;
  *) fail "The automatic installer supports macOS and Linux. For Windows: curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.ps1 -o install.ps1; powershell -ExecutionPolicy Bypass -File .\\install.ps1" ;;
esac
command -v curl >/dev/null 2>&1 || fail "curl is missing. Install curl and run the installer again."

# Disk space: ~4 GB for product/dependencies/PWA build. Model downloads do NOT
# happen here (the engine is chosen in the app) → warning, no abort.
FREE_KB=$(df -Pk "$PROJECT_DIR" | awk 'NR==2 {print $4}')
if [[ "${FREE_KB:-0}" -lt 4096000 ]]; then
  warn "Less than ~4 GB free disk (current: $((FREE_KB / 1024 / 1024)) GB). The installation is attempted anyway."
else
  ok "Disk space OK"
fi

step "Checking Python 3.11+"
find_uv() {
  for candidate in \
    "$(command -v uv 2>/dev/null || true)" \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv"; do
    [[ -n "$candidate" && -x "$candidate" ]] && { echo "$candidate"; return 0; }
  done
  return 1
}

find_python() {
  local uv_bin uv_python bin
  uv_bin="$(find_uv || true)"
  if [[ -n "$uv_bin" ]]; then
    uv_python="$("$uv_bin" python find 3.12 2>/dev/null || true)"
    if [[ -n "$uv_python" && -x "$uv_python" ]]; then
      echo "$uv_python"
      return 0
    fi
  fi

  for candidate in \
    python3.13 python3.12 python3.11 python3 python \
    /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 \
    /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3; do
    if [[ "$candidate" == */* ]]; then
      [[ -x "$candidate" ]] || continue
      bin="$candidate"
    else
      command -v "$candidate" >/dev/null 2>&1 || continue
      bin="$(command -v "$candidate")"
    fi
    if "$bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      echo "$bin"
      return 0
    fi
  done
  return 1
}

install_uv_python() {
  local uv_bin rc=0
  info "Installing a local Python runtime via uv."
  uv_bin="$(find_uv || true)"
  if [[ -z "$uv_bin" ]]; then
    # A rotated vendor hash must not abort here: this returns non-zero and
    # install_python() falls through to the distro interpreter branch, so a bare
    # box (no Python, no uv) still reaches an interpreter instead of stopping at
    # the uv supply-chain gate.
    fetch_verify_run "https://astral.sh/uv/install.sh" "$UV_INSTALL_SHA256" "uv" "EPHE_UV_INSTALL_SHA256" || rc=$?
    uv_bin="$(find_uv || true)"
    if [[ -z "$uv_bin" ]]; then
      if [[ "$DRY_RUN" == "1" ]]; then
        uv_bin="$HOME/.local/bin/uv"
      else
        [[ "$rc" == "0" ]] || warn "No uv runtime after the vendor step (see the message above) — falling back to the system interpreter."
        return 1
      fi
    fi
  fi
  [[ -n "$uv_bin" ]] || return 1
  run "$uv_bin" python install 3.12
}

install_python() {
  info "Python 3.11+ is missing. Starting the installation."
  if [[ "$OS_NAME" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      run brew install python@3.12 || run brew install python
    else
      install_uv_python || fail "Python 3.11+ could not be installed automatically."
    fi
  elif install_uv_python; then
    return 0
  elif command -v apt-get >/dev/null 2>&1; then
    run as_root apt-get update
    run as_root apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    run as_root dnf install -y python3 python3-pip
  elif command -v yum >/dev/null 2>&1; then
    run as_root yum install -y python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    run as_root pacman -Sy --noconfirm python python-pip
  else
    fail "Python 3.11+ is missing. Install Python and python3-venv with your package manager and run ./install.sh again."
  fi
}

PYTHON="$(find_python || true)"
if [[ -z "$PYTHON" ]]; then
  install_python
  PYTHON="$(find_python || true)"
fi
if [[ -z "$PYTHON" && "$DRY_RUN" == "1" ]]; then
  PYTHON="python3"
  ok "Python 3.11+ would be installed"
else
  [[ -n "$PYTHON" ]] || fail "Python 3.11+ is missing. Install Python and run the installer again."
  ok "$("$PYTHON" -c 'import sys; print(sys.version.split()[0])') found"
fi

# ── AI engine (info step, never blocking) ───────────────────────────────────
# Mandate 2026-08-21: Ollama is NOT installed, NO models are pulled.
# This step only checks whether Ollama is ready locally and shows a hint.
# Missing Ollama → warning (no abort); the engine is chosen in the app
# (SetupPage: local Ollama / remote Ollama / OpenAI-compatible).
step "Checking the AI engine (info)"
OLLAMA_BIN="$(command -v ollama 2>/dev/null || true)"
OLLAMA_SERVICE_OK=0
if [[ -n "$OLLAMA_BIN" ]]; then
  if curl -fsS --max-time 3 "${LOCAL_OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    OLLAMA_SERVICE_OK=1
  fi
fi
if [[ -n "$OLLAMA_BIN" && "$OLLAMA_SERVICE_OK" == "1" ]]; then
  ok "Ollama detected — its models are available for selection in the app."
else
  warn "No Ollama detected — that is OK: Ephe does not install an AI of its own."
  info "After the start you choose your engine in the app (local Ollama or an external endpoint such as DGX)."
fi

step "Setting up the local Python environment"
if [[ ! -d ".venv" ]]; then
  run "$PYTHON" -m venv .venv
fi
# An existing `.venv` may be a `uv venv` (no pip module and no `bin/pip` script).
# Seed pip so the installs below cannot fail on a machine that already had a
# venv, and call pip as a module everywhere: a seeded env has `python -m pip`
# even when it never got a `bin/pip` console script.
if [[ "$DRY_RUN" != "1" && -d .venv ]] && ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  run .venv/bin/python -m ensurepip --upgrade
fi
run .venv/bin/python -m pip install --upgrade pip
if [[ "$INSTALL_MODE" == "cli" ]]; then
  info "CLI mode: installing minimal dependencies (tui) only"
  run .venv/bin/python -m pip install -e ".[tui]"
else
  run .venv/bin/python -m pip install -e ".[gui,voice]"
fi
# openpyxl: xlsx support (otherwise missing from a Miniconda env, and it costs 10 tests)
run .venv/bin/python -m pip install openpyxl
ok "Dependencies installed"

# ── PWA build (desktop mode) ────────────────────────────────────────────────
# The server serves the web app (PWA) from app/dist/ — a build artifact that is
# git-ignored and therefore missing from a fresh clone. In desktop mode we build
# the frontend now so that http://127.0.0.1:8765/ loads directly.
# CLI mode (TUI) needs no frontend → the build is skipped (faster).
if [[ "$INSTALL_MODE" != "cli" ]]; then
  build_pwa() {
    step "Building the PWA (web app)"
    if ! command -v npm >/dev/null 2>&1; then
      fail "npm is missing — Node.js/npm is required for the PWA build. Install Node.js (https://nodejs.org) and run the installer again."
    fi
    # `command -v pnpm` proves a file exists, not that pnpm runs. Homebrew's pnpm
    # IS the corepack shim, and corepack resolves the `packageManager` pin from the
    # CURRENT WORKING DIRECTORY — not from `--dir` — so a pnpm that answers here can
    # still die at the real call. Measured 2026-10-15 from this directory: the shim
    # resolved pnpm 12.11.2 and then failed with "Cannot find module
    # …/corepack/v1/pnpm/12.11.2/bin/pnpm.cjs", while the same command from app/
    # worked. So probe pnpm by RUNNING it — the way find_python() already probes an
    # interpreter — in the directory the build runs in and with the `--dir` the
    # build uses. A pnpm that does not run counts as absent, which is what it is,
    # and the npm branch below is the path that works there.
    pnpm_ok=0
    if [[ "$DRY_RUN" == "1" ]]; then
      # A dry run executes no tool, so presence is all it can ask for.
      if command -v pnpm >/dev/null 2>&1; then pnpm_ok=1; fi
    elif pnpm --dir "$PROJECT_DIR/app" --version >/dev/null 2>&1; then
      pnpm_ok=1
    elif command -v pnpm >/dev/null 2>&1; then
      warn "pnpm is installed but does not run here (its corepack shim cannot resolve the pinned version) — building with npm instead."
    fi
    if [[ ! -f "$PROJECT_DIR/app/pnpm-lock.yaml" ]]; then
      info "install is running (without the lockfile)"
      if [[ "$pnpm_ok" == "1" ]]; then
        run pnpm --dir "$PROJECT_DIR/app" install
      else
        run npm --prefix "$PROJECT_DIR/app" install --no-package-lock
      fi
    elif [[ "$pnpm_ok" == "1" ]]; then
      run pnpm --dir "$PROJECT_DIR/app" install --frozen-lockfile || run pnpm --dir "$PROJECT_DIR/app" install
      run pnpm --dir "$PROJECT_DIR/app" run build
    else
      # npm, and `install --no-package-lock` rather than `ci`: a fresh clone has no
      # package-lock.json, and `npm ci` refuses that state outright — measured on
      # npm 11.18.0 against an app/ holding package.json + pnpm-lock.yaml, it exits 1
      # with "EUSAGE … can only install with an existing package-lock.json". Bare
      # `npm install` does work but writes app/package-lock.json, the second lockfile
      # tests/test_r46_pnpm_single_source.py forbids. The flag is the shape that both
      # runs without a lockfile and leaves the pnpm-only contract alone.
      info "pnpm is not usable here — building with npm (no package-lock.json will be written)"
      run npm --prefix "$PROJECT_DIR/app" install --no-package-lock
      run npm --prefix "$PROJECT_DIR/app" run build
    fi
    if [[ "$DRY_RUN" != "1" && ! -f "$PROJECT_DIR/app/dist/index.html" ]]; then
      fail "PWA build failed: app/dist/index.html does not exist."
    fi
    ok "PWA built → app/dist"
  }
  build_pwa
else
  info "CLI mode: the PWA build is skipped (the TUI needs no frontend)"
fi

step "Creating the local data folders"
if [[ "$DRY_RUN" == "1" ]]; then
  info "DRY-RUN: mkdir -p $HOME/.ephe/memory $HOME/.ephe/skills $HOME/.ephe/sessions"
else
  mkdir -p "$HOME/.ephe/memory" "$HOME/.ephe/skills" "$HOME/.ephe/sessions/audio" "$HOME/.ephe/sessions/images"
fi
ok "$HOME/.ephe ready"

# The `ephe` console script is installed into `.venv/bin` and nothing here edits
# a shell rc, so a bare `ephe configure` typed into a NEW terminal answers
# "command not found" (docs/UI_AUDIT_2026-10-12.md, "the documented first command
# is not on PATH"). The block therefore prints the activation line first and the
# commands after it; docs/INSTALL.md repeats exactly these lines, and
# tests/test_installer_cli.py pins the printed set to the documented set and both
# to the real subparsers of `ephe_cli.build_parser()`.
echo ""
echo -e "${GREEN}${BOLD}Setup complete.${NC}"
echo "Project: $PROJECT_DIR"
echo ""
echo "The 'ephe' command is not on PATH yet - activate the environment first:"
echo "  source \"$PROJECT_DIR/.venv/bin/activate\""
echo ""
echo "Then, in that same shell:"
echo "  ephe configure    # choose the engine once (saved to ~/.ephe/engine.json)"
echo "  ephe doctor       # check Ollama, model and server state"
if [[ "$INSTALL_MODE" == "cli" ]]; then
  echo "  ephe tui          # start the terminal UI"
else
  echo "  ephe start --open # start the local app, then open http://127.0.0.1:${PORT}"
fi
echo ""

if [[ "$NO_START" != "1" && "$DRY_RUN" != "1" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Start now? [Y/n] " reply
    reply="${reply:-Y}"
    [[ "$reply" =~ ^[YyJj]$ ]] || exit 0
  fi
  if [[ "$INSTALL_MODE" == "cli" ]]; then
    exec .venv/bin/ephe tui
  else
    exec .venv/bin/ephe start --port "$PORT" --open
  fi
fi
