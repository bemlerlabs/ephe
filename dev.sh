#!/usr/bin/env bash
# One command starts backend + frontend (parallel dev mode, `pnpm web`).
# Usage: ./dev.sh   ·   Ctrl+C shuts both down cleanly.
set -e
cd "$(dirname "$0")"

# A PYTHONPATH inherited from the shell (a different venv) bleeds into the
# server as a pydantic_core mismatch; scripts/run-tests.sh clears it for the
# same reason.
unset PYTHONPATH

# Backend Python: the venv when present, otherwise system python.
PY="python"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

# Frontend deps are installed once; without them `pnpm dev` fails deep inside
# Vite with a message that names nothing actionable.
if [ ! -d app/node_modules ]; then
    echo "app/node_modules is missing — run: (cd app && pnpm install)" >&2
    exit 1
fi

# On exit (Ctrl+C / error) kill the whole process group → no orphans.
trap 'kill 0' INT TERM EXIT

"$PY" run_server.py --lan &
( cd app && pnpm dev ) &

wait
