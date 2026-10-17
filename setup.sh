#!/usr/bin/env bash
# ◑ Ephe — in-repo quickstart.
#
# install.sh is the download-and-install twin of this script: same steps, same
# order, same env overrides. setup.sh is for someone who already has a checkout.
#
# Both scripts speak English to the terminal: a script's own output is a
# repository artifact, not the product's UI. German stays in the app.
#
# Fail-closed and offline-first: this script never installs an AI engine, never
# pulls a model, never writes a key and never invents an engine choice. The
# engine stays the user's decision — on the Setup page in the app, or with
# `ephe configure` in the terminal (see AGENTS.md).
#
# Run: bash setup.sh

set -euo pipefail

# The repository is the script's own directory — no subdirectory of it has a
# name the script invents.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${EPHE_PORT:-8765}"
NO_START="${EPHE_NO_START:-0}"
DRY_RUN="${EPHE_DRY_RUN:-0}"
# Python extras, same default as install.sh desktop mode. An explicitly empty
# value (EPHE_EXTRAS="") means base dependencies only — hence `-`, not `:-`.
EXTRAS="${EPHE_EXTRAS-gui,voice}"

for arg in "$@"; do
  case "$arg" in
    --no-start) NO_START=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --help|-h)
      echo "Usage: bash setup.sh [--no-start] [--dry-run]"
      echo "Env: EPHE_PORT, EPHE_NO_START, EPHE_DRY_RUN, EPHE_EXTRAS"
      exit 0
      ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

step() { echo ""; echo "▶ $1"; }
info() { echo "  · $1"; }
ok()   { echo "  ✓ $1"; }
warn() { echo "  ⚠ $1"; }
fail() { echo "  ✗ $1" >&2; exit 1; }

# Dry-run prints the command instead of running it — the proof harness uses this
# to show the exact sequence without touching a machine.
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "  DRY-RUN: $*"
  else
    "$@"
  fi
}

echo ""
echo "◑  Ephe — offline assistant (one command, one checkout)"
echo "   No subscription, no account. With a local engine Ephe runs without the internet."
echo "   Cloud engines are a choice, not a default."

# ── 1. System ───────────────────────────────────────────────────────────────
step "Checking the system"
case "$(uname -s)" in
  Darwin|Linux) ok "$(uname -s) supported" ;;
  *) fail "The automatic start supports macOS and Linux. For Windows: install.ps1 (see README)." ;;
esac

# ── 2. Python 3.10+ ─────────────────────────────────────────────────────────
step "Checking Python"
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
[[ -n "$PYTHON" ]] || fail "Python 3.10+ is required. Install Python and run 'bash setup.sh' again."
if [[ "$DRY_RUN" == "1" && -z "$PYTHON" ]]; then PYTHON="python3"; fi
ok "Python $("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

# ── 3. Node.js 20+ (the PWA build needs it) ─────────────────────────────────
step "Checking Node.js"
command -v npm >/dev/null 2>&1 || fail "Node.js/npm is missing. The web frontend needs Node.js 20+: https://nodejs.org"
NODE_MAJOR="$(node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/')"
if [[ -n "$NODE_MAJOR" && "$NODE_MAJOR" -lt 20 ]]; then
  fail "Node.js ${NODE_MAJOR} is too old — the frontend requires Node.js 20+ (app/package.json: engines)."
fi
ok "Node.js $(node -v)"

# ── 4. Python dependencies (local .venv) ────────────────────────────────────
step "Setting up the Python environment"
if [[ ! -d ".venv" ]]; then
  run "$PYTHON" -m venv .venv
  info ".venv created"
else
  ok ".venv present — reusing it"
fi
run .venv/bin/python -m pip install --upgrade pip
if [[ -n "$EXTRAS" ]]; then
  run .venv/bin/pip install -e ".[${EXTRAS}]"
else
  run .venv/bin/pip install -e .
fi
ok "Python packages ready (extras: ${EXTRAS:-none})"

# ── 5. Frontend dependencies + PWA build ────────────────────────────────────
# The product server serves the built PWA from app/dist/ — a git-ignored build
# artifact, so it is missing on a fresh checkout and has to be built here.
step "Building the frontend"
if [[ ! -f "app/package.json" ]]; then
  fail "app/package.json not found — this script runs in the Ephe repository root."
fi
# The install and the build run INSIDE app/: corepack resolves the pinned
# "packageManager" from the package.json of the working directory, so `pnpm --dir`
# from the repository root (which has none) silently ignores the pin and reaches
# for a different pnpm over the network.
if command -v pnpm >/dev/null 2>&1 && [[ -f "app/pnpm-lock.yaml" ]]; then
  (
    cd "$SCRIPT_DIR/app"
    run pnpm install --frozen-lockfile || run pnpm install
    if ! run pnpm run build; then
      echo "  ✗ The frontend build failed." >&2
      echo "    'npm run build' = 'tsc -b && vite build'; the lines above say" >&2
      echo "    which file is missing. Typical case on a fresh checkout:" >&2
      echo "    app/package.json does not declare @types/node, while the test files" >&2
      echo "    under app/src/ import node:fs — and tsc aborts." >&2
      exit 1
    fi
  )
else
  info "pnpm or app/pnpm-lock.yaml unavailable — npm without a lockfile"
  (
    cd "$SCRIPT_DIR/app"
    run npm install
    run npm run build
  )
fi
if [[ "$DRY_RUN" != "1" && ! -f "app/dist/index.html" ]]; then
  fail "Frontend build failed: app/dist/index.html does not exist."
fi
ok "Frontend built → app/dist"

# ── 6. Engine: report the state, never decide it ────────────────────────────
step "Engine status"
if [[ -f "$HOME/.ephe/engine.json" ]]; then
  # provider + model only: the file never holds a key, and nothing is printed
  # beyond what the user already chose.
  .venv/bin/python - <<'PY' || warn "The engine file could not be read."
import json, os
try:
    c = json.load(open(os.path.expanduser("~/.ephe/engine.json")))
    print(f"  ✓ Chosen engine: {c.get('provider')} / {c.get('model')}"
          + (f" @ {c.get('api_url')}" if c.get("api_url") else ""))
except Exception:
    raise SystemExit(1)
PY
else
  info "No engine chosen yet — Ephe does not invent one."
  info "After the start, the Setup page appears in the browser; there you choose"
  info "local Ollama, your own Ollama on the network, or an OpenAI-compatible"
  info "endpoint. In the terminal: .venv/bin/ephe configure"
fi

# ── 7. Start ────────────────────────────────────────────────────────────────
if [[ "$NO_START" == "1" || "$DRY_RUN" == "1" ]]; then
  echo ""
  echo "◑  Setup complete. Start: .venv/bin/python run_server.py --port ${PORT}"
  echo "   Then in the browser: http://127.0.0.1:${PORT}"
  exit 0
fi

# A listener on the port is usually a running Ephe. Taking the port down would
# kill someone else's session, so the script stops and says so instead.
if .venv/bin/python - "$PORT" <<'PY'
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
then
  warn "Something is already listening on port ${PORT} — probably Ephe itself."
  info "I do not kill other people's processes. Open http://127.0.0.1:${PORT}"
  info "or start on your own port: EPHE_PORT=8786 bash setup.sh"
  exit 1
fi

echo ""
echo "◑  Ephe will be reachable at:  http://127.0.0.1:${PORT}"
echo "   On the phone:               .venv/bin/python run_server.py --lan"
echo "                              (scan the QR code in the terminal; own network only)"
echo ""
echo "   Tips for the first minutes:"
echo "   → \"Remember this: my name is [your name]\""
echo "   → \"What can you do for me today?\""
echo ""
echo "   Stop with: Ctrl+C"
echo ""

# The server owns its own foreground process — no background PIDs to reap.
exec .venv/bin/python run_server.py --port "$PORT"
