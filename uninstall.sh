#!/usr/bin/env bash
# uninstall.sh — the other half of install.sh.
#
# install.sh leaves exactly two things on a machine: a checkout in
# EPHE_INSTALL_DIR (default $HOME/Documents/Ephe) and the app's state tree in
# EPHE_CONFIG_DIR (default $HOME/.ephe — engine.json, engine.key, sessions,
# memory, artifacts, workspaces, changesets, bench runs, caches). This script
# removes those two trees and NOTHING else, and it refuses to run when either
# path looks like something other than what it names.
#
# Why the paranoia: `rm -rf "$SOMETHING"` is the one command in this repo that
# cannot be undone or code-reviewed after the fact, and both paths are
# overridable from the environment. `EPHE_INSTALL_DIR=/ uninstall.sh` must not be
# able to delete a filesystem root, and a typo must not be able to delete a home
# directory. Every removal therefore goes through remove_tree(), which resolves
# the path, checks it against the rules in assert_removable(), and refuses
# (exit 2) instead of guessing.
#
# User data is treated as data, not as product: the checkout is reconstructible
# from git, the state tree is not. So the data tree is removed only when the
# caller said so (--yes) or answered yes at the prompt; --keep-data and a
# non-interactive run without --yes both leave it standing, and every run prints
# what stayed behind and how to remove it.
#
# Output goes through `printf '%b'` rather than `echo -e`: the installer is always
# started as `bash install.sh` (or through its bash shebang), but `sh uninstall.sh`
# is an invocation users reach for on a host where /bin/sh IS bash (macOS), and
# bash-as-sh in POSIX mode prints `-e` as a literal argument instead of
# interpreting it.
set -euo pipefail
# `-E` (errtrace): the ERR trap below has to fire inside remove_tree() and the
# other helpers too, or a failed `rm` would be the only error the user ever sees
# (install.sh carries the same comment and the same trap shape).
set -E

GREEN='\033[0;32m'
DIM='\033[2m'
BOLD='\033[1m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

INSTALL_DIR="${EPHE_INSTALL_DIR:-$HOME/Documents/Ephe}"
# The app resolves its state as EPHE_CONFIG_DIR or $HOME/.ephe
# (core/engine_config.py, core/session.py, core/feedback.py). install.sh creates
# $HOME/.ephe unconditionally; this script honours the override so a user who
# relocated the tree can still uninstall it.
DATA_DIR="${EPHE_CONFIG_DIR:-$HOME/.ephe}"
DRY_RUN="${EPHE_DRY_RUN:-0}"
KEEP_DATA="${EPHE_KEEP_DATA:-0}"
ASSUME_YES=0
FORCE=0
REMOVE_DATA=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --keep-data) KEEP_DATA=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --force) FORCE=1 ;;
    --help|-h)
      printf '%s\n' "Usage: ./uninstall.sh [--dry-run] [--keep-data] [--yes] [--force]"
      printf '%s\n' "Env: EPHE_INSTALL_DIR, EPHE_CONFIG_DIR, EPHE_DRY_RUN, EPHE_KEEP_DATA"
      printf '%s\n' ""
      printf '%s\n' "Removes the two things install.sh leaves behind:"
      printf '%s\n' "  checkout  $INSTALL_DIR"
      printf '%s\n' "  data      $DATA_DIR   (engine key, sessions, memory, artifacts)"
      printf '%s\n' ""
      printf '%s\n' "Nothing outside those two paths is ever touched, and the script refuses"
      printf '%s\n' "when a path is a filesystem root, your home directory, an ancestor of it,"
      printf '%s\n' "a directory shallower than /a/b, or not an Ephe checkout."
      printf '%s\n' ""
      printf '%s\n' "Flags:"
      printf '%s\n' "  --dry-run    list what would be removed, remove nothing"
      printf '%s\n' "  --keep-data  remove the checkout, keep $DATA_DIR"
      printf '%s\n' "  --yes        do not ask about the data tree; remove it too"
      printf '%s\n' "  --force      proceed even if the checkout carries no Ephe markers"
      printf '%s\n' ""
      printf '%s\n' "Without --yes the data tree is removed only after a prompt, and a"
      printf '%s\n' "non-interactive run without --yes keeps it and prints the one command"
      printf '%s\n' "that removes it. Ollama and its models are never touched."
      exit 0
      ;;
    *) printf '%s\n' "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '%b\n' "${GREEN}▶${NC} ${BOLD}$1${NC}"; }
info() { printf '%b\n' "  ${DIM}$1${NC}"; }
warn() { printf '%b\n' "  ${YELLOW}⚠${NC} $1"; }
ok() { printf '%b\n' "  ${GREEN}✓${NC} $1"; }
fail() { printf '%b\n' "  ${RED}✗${NC} $1" >&2; exit 1; }
# A refusal is not a failed step: the caller asked for something this script will
# not do, so it exits 2 (the same code install.sh uses for a bad argument) and
# says which path and which rule it tripped.
refuse() { printf '%b\n' "  ${RED}✗${NC} $1" >&2; exit 2; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '%s\n' "  DRY-RUN: $*"
  else
    "$@"
  fi
}

# `set -e` stops on the first failing command but names neither the line nor the
# command (install.sh makes the same argument). The ERR trap prints both.
trap 'printf "%b\n" "  ${RED}✗${NC} uninstall.sh failed at line $LINENO: $BASH_COMMAND" >&2' ERR

# --- Path resolution and the removal guard ----------------------------------

# Physical path of $1: the parent's real location plus the leaf name. A leaf that
# does not exist yet still resolves through its parent, so the guard also runs in
# a dry run and before any `mkdir`. The leaf is deliberately NOT resolved: when
# DATA_DIR is a symlink, `rm -rf` must remove the link, not its target.
resolve_path() {
  local target="$1" parent base
  base="$(basename -- "$target")"
  parent="$(dirname -- "$target")"
  if [[ -d "$parent" ]]; then
    printf '%s/%s\n' "$(cd -P -- "$parent" && pwd)" "$base"
  else
    printf '%s\n' "$target"
  fi
}

tree_size() { du -sh "$1" 2>/dev/null | awk '{print $1}'; }
tree_files() { find "$1" -type f 2>/dev/null | wc -l | tr -d ' '; }

# Squeeze doubled separators and drop a trailing one, but keep '/' meaning '/':
# '//tmp/' is /tmp, and a filesystem root must not normalise into an empty string
# that no guard recognises.
norm_path() {
  local p
  p="$(printf '%s' "$1" | tr -s '/')"
  if [[ "$p" == "/" ]]; then
    printf '%s' "/"
  else
    printf '%s' "${p%/}"
  fi
}

# The two-path containment rule: if one root sits inside the other, removing the
# outer one would silently take the inner one with it — which is how a "keep my
# data" run ends up deleting it. Refuse rather than order the two removals.
assert_disjoint() {
  local checkout="$1" data="$2"
  if [[ "$checkout" == "$data" ]]; then
    refuse "'$checkout' is both the checkout and the data tree. Set EPHE_INSTALL_DIR and EPHE_CONFIG_DIR to different paths."
  fi
  if [[ -n "$checkout" && "$data" == "$checkout"/* ]]; then
    refuse "the data tree '$data' lives inside the checkout '$checkout'. Set EPHE_CONFIG_DIR to a path outside it."
  fi
  if [[ -n "$data" && "$checkout" == "$data"/* ]]; then
    refuse "the checkout '$checkout' lives inside the data tree '$data'. Set EPHE_INSTALL_DIR to a path outside it."
  fi
}

# Every rule that stands between a wrong path and `rm -rf`. Exits 2 on a tripped
# rule, so nothing is removed.
assert_removable() {
  local raw="$1" label="$2" resolved depth
  resolved="$(norm_path "$(resolve_path "$raw")")"
  [[ -n "$resolved" ]] || refuse "$label path is empty."

  if [[ "$resolved" == "/" ]]; then
    refuse "$label is '/': refusing to remove the filesystem root."
  fi
  depth="$(awk -F/ '{print NF-1}' <<<"$resolved")"
  if (( depth < 2 )); then
    refuse "$label is '$resolved', a top-level directory. Refusing: an Ephe tree is never at the root of the filesystem."
  fi
  if [[ "$resolved" == "$HOME" ]]; then
    refuse "$label is your home directory ($HOME). Refusing."
  fi
  if [[ "$HOME" == "$resolved"/* ]]; then
    refuse "$label ($resolved) contains your home directory. Refusing."
  fi
  # A leaf that is a symlink is fine (rm -rf removes the link), but a checkout
  # that resolves onto something already covered by the rules above is not.
  if [[ -d "$raw" && ! -L "$raw" ]]; then
    resolved="$(norm_path "$(cd -P -- "$raw" && pwd)")"
    if [[ "$resolved" == "/" || "$resolved" == "$HOME" || "$HOME" == "$resolved"/* ]]; then
      refuse "$label resolves to '$resolved', which is a filesystem root or contains your home directory. Refusing."
    fi
  fi
}

# The same predicate install.sh uses to decide it is standing in a checkout.
is_ephe_checkout() {
  [[ -f "$1/pyproject.toml" && -d "$1/app/src" && -f "$1/run_server.py" ]]
}

# --- Reporting ---------------------------------------------------------------

describe() {
  local path="$1" label="$2" size="$3" files="$4"
  if [[ "$DRY_RUN" == "1" ]]; then
    info "$label: would remove $path ($size, $files files)"
  else
    ok "$label: removed $path ($size, $files files)"
  fi
}

remove_tree() {
  local path="$1" label="$2" size files
  if [[ ! -e "$path" && ! -L "$path" ]]; then
    info "$label: $path does not exist — nothing to remove"
    return 0
  fi
  if [[ ! -d "$path" ]]; then
    warn "$label: $path is not a directory; leaving it alone"
    return 0
  fi
  assert_removable "$path" "$label"
  # Measure first: the numbers have to describe what was there, and reading them
  # after `rm -rf` would report the size of nothing.
  size="$(tree_size "$path")"
  files="$(tree_files "$path")"
  run rm -rf -- "$path"
  if [[ "$DRY_RUN" != "1" && ( -e "$path" || -L "$path" ) ]]; then
    fail "$label: $path still exists after rm -rf — something kept it. Inspect it by hand."
  fi
  describe "$path" "$label" "$size" "$files"
}

# --- Refuse a bad environment before any step runs --------------------------
assert_disjoint "$(norm_path "$(resolve_path "$INSTALL_DIR")")" "$(norm_path "$(resolve_path "$DATA_DIR")")"

printf '%s\n' ""
printf '%b\n' "${GREEN}${BOLD}Ephe uninstaller${NC}"
printf '%b\n' "${DIM}Removes exactly two trees: the checkout and the state tree. Nothing else.${NC}"
printf '%s\n' ""

# --- The checkout ------------------------------------------------------------
step "The checkout"
if [[ -e "$INSTALL_DIR" || -L "$INSTALL_DIR" ]]; then
  assert_removable "$INSTALL_DIR" "checkout"
  if [[ -d "$INSTALL_DIR" ]] && ! is_ephe_checkout "$INSTALL_DIR"; then
    if [[ "$FORCE" == "1" ]]; then
      warn "$INSTALL_DIR carries no Ephe markers (pyproject.toml, app/src, run_server.py) — proceeding because of --force."
    else
      refuse "$INSTALL_DIR exists but is not an Ephe checkout (no pyproject.toml + app/src + run_server.py). Refusing to remove it; pass --force if you really mean this path."
    fi
  fi
fi
remove_tree "$INSTALL_DIR" "checkout"

# --- The data tree ----------------------------------------------------------
step "Your data"
if [[ ! -e "$DATA_DIR" && ! -L "$DATA_DIR" ]]; then
  info "data: $DATA_DIR does not exist — nothing to remove"
elif [[ ! -d "$DATA_DIR" ]]; then
  warn "data: $DATA_DIR is not a directory; leaving it alone"
else
  size="$(tree_size "$DATA_DIR")"
  files="$(tree_files "$DATA_DIR")"
  if [[ "$KEEP_DATA" == "1" ]]; then
    info "keeping $DATA_DIR ($size, $files files) because of --keep-data"
  elif [[ "$ASSUME_YES" == "1" ]]; then
    info "removing $DATA_DIR ($size, $files files) because of --yes"
    REMOVE_DATA=1
  elif [[ "$DRY_RUN" == "1" ]]; then
    info "a real run without --yes would ASK about $DATA_DIR ($size, $files files)"
  elif [[ -t 0 ]]; then
    printf '%s\n' "  $DATA_DIR holds the state install.sh cannot recreate:"
    printf '%s\n' "    engine.json, engine.key   the engine choice and its key"
    printf '%s\n' "    memory/                   profile, corrections, chroma_db"
    printf '%s\n' "    sessions/                 conversations, tasks, images, audio"
    printf '%s\n' "    artifacts/, changesets/, workspaces/, bench/   your work"
    read -r -p "  Delete $DATA_DIR ($size, $files files) as well? [y/N] " reply
    if [[ "$reply" =~ ^[YyJj]$ ]]; then
      REMOVE_DATA=1
    fi
  else
    info "no terminal to ask on, and no --yes: keeping $DATA_DIR ($size, $files files)"
  fi
  if [[ "$REMOVE_DATA" == "1" ]]; then
    remove_tree "$DATA_DIR" "data"
  fi
fi

# --- What is left ------------------------------------------------------------
printf '%s\n' ""
step "What was left alone"
info "any other checkout: this run only touched the two paths named above"
info "Ollama and its models: untouched (the installer never installed them either)"
if [[ -e "$DATA_DIR" ]]; then
  info "your data: $DATA_DIR ($(tree_size "$DATA_DIR"), $(tree_files "$DATA_DIR") files)"
fi
# An engine key may also live in the OS keychain (ENGINE_KEYRING_SERVICE = "ephe",
# core/engine_config.py), which is outside both trees by design — this script does
# not reach outside them, so the entry is reported rather than removed.
info "the OS keychain item 'ephe' / 'engine_api_key', if your engine key was stored there: not removed (remove it in Keychain Access if you want it gone)"
if command -v ephe >/dev/null 2>&1; then
  info "the 'ephe' on your PATH at $(command -v ephe): untouched (it is not inside the two paths)"
fi

printf '%s\n' ""
if [[ "$DRY_RUN" == "1" ]]; then
  printf '%b\n' "${GREEN}${BOLD}Dry run — nothing was removed.${NC}"
  printf '%s\n' "Run the same command without --dry-run to remove what is listed above."
elif [[ -e "$DATA_DIR" || -L "$DATA_DIR" ]]; then
  printf '%b\n' "${GREEN}${BOLD}The checkout is gone; your data is still at $DATA_DIR.${NC}"
  printf '%s\n' "Remove it too with: ./uninstall.sh --yes    (or: rm -rf \"$DATA_DIR\")"
else
  printf '%b\n' "${GREEN}${BOLD}Ephe is gone from this machine.${NC}"
  printf '%s\n' "Reinstall at any time with: curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.5.0/install.sh | bash"
fi
printf '%s\n' ""
