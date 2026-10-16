#!/usr/bin/env bash
# CLI demo GIF recording for Ephe (Textual TUI)
# Requirements: asciinema + agg installed (see README below)
#   pip install asciinema
#   cargo install agg  (or: brew install agg)
#
# The TUI only runs in a TTY. asciinema records the session, agg turns it into a GIF.
set -euo pipefail
cd "$(dirname "$0")/.."
# Put the venv binaries (asciinema, ephe) on PATH — the script runs without an activated venv
export PATH="$(pwd)/.venv/bin:$PATH"

MODEL="${1:-gemma4:e4b}"
OUT_DIR="docs/media"
OUT="${OUT_DIR}/ephe-cli-demo.gif"

command -v asciinema >/dev/null || { echo "asciinema missing (pip install asciinema)"; exit 1; }
command -v agg     >/dev/null || { echo "agg missing (cargo install agg)"; exit 1; }
command -v tmux    >/dev/null || { echo "tmux missing"; exit 1; }

echo "recording 'ephe tui --model $MODEL' …"
# asciinema: 2s idle timeout, max 120s
asciinema rec "${OUT_DIR}/_rec.cast" --overwrite -i 2 -q -c '
  tmux new-session -d -s ephe "exec .venv/bin/ephe tui --model '"${MODEL}"'"
  tmux send-keys -t ephe "/post Zeig mir die 5 wichtigsten Best Practices für lokale LLMs" Enter
  sleep 8
  tmux send-keys -t ephe "/swarm Vergleiche lokale vs. cloud LLM inference" Enter
  sleep 6
  tmux send-keys -t ephe q
  tmux wait-for ephe || true
'

echo "Konvertiere zu GIF …"
agg "${OUT_DIR}/_rec.cast" "${OUT}" --font-size 16 --theme dracula --speed 1.2
rm -f "${OUT_DIR}/_rec.cast"
echo "Fertig: ${OUT}"
ls -lh "${OUT}"
