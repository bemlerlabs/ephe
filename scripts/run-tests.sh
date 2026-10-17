#!/usr/bin/env bash
# run-tests.sh — canonical test entry point for Ephe.
#
# Hardens the environment against dev-environment contamination:
#   - clears PYTHONPATH (stops the Referenz-A/system venv on python3.11 from   # language-gate: ignore (Referenz-A is the repo's name for the anonymised reference client, used verbatim even in the English locale)
#     bleeding into the local pytest and triggering a pydantic_core mismatch)
#   - uses the local .venv explicitly (`.venv/bin/python -m pytest`)
# All arguments are passed through to pytest unchanged.
#
# Examples:
#   ./scripts/run-tests.sh                                  # full suite
#   ./scripts/run-tests.sh tests/test_installer_cli.py -q   # focused
set -euo pipefail
cd "$(dirname "$0")/.."   # project root

# Clear PYTHONPATH hard — the root cause of the pydantic_core mismatch
export PYTHONPATH=
unset PYTHONPATH 2>/dev/null || true

# Standard env for the release bar (overridable from outside)
export EPHE_MODEL="${EPHE_MODEL:-mock}"
export EPHE_OFFLINE="${EPHE_OFFLINE:-1}"
export EPHE_MEMORY_DIR="${EPHE_MEMORY_DIR:-/tmp/ephe-test-memory}"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "❌ .venv missing — run this once:" >&2
  echo "   python -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

echo "▶ run-tests.sh: PYTHONPATH cleared, venv=$PWD/$PY"
exec "$PY" -m pytest "$@"
