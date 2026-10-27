#!/usr/bin/env bash
# Ephe — install the desktop app locally (R4).
#
# Why this script exists: `ephe desktop` builds and opens the bundle from
# app/src-tauri/target/… — it never lands in /Applications. The installed
# Ephe therefore stays what it was, and LaunchServices collects one more dead
# address of the same product with every build. The update button cannot do this:
# it asks GitHub for a published release, and as long as nothing is published the
# feed answers 404 (it then says "check not possible", not "no update" —
# that is the truth).
#
# What it does, and what it does not do:
#   - the old /Applications/Ephe.app goes to the trash, with a timestamp.
#     Nothing is deleted — undoing it is a move back.
#   - ditto copies the new bundle, so frameworks, symlinks and the code
#     signature arrive unchanged; `cp` is not specified to carry them over.
#   - LaunchServices is reset to exactly ONE address.
#
# Usage:  scripts/install_desktop.sh [--build] [--launch]

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/app"
TARGET_ROOT="$APP_DIR/src-tauri/target/release/bundle"
INSTALL_TO="/Applications/Ephe.app"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

BUILD=0
LAUNCH=0
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --launch) LAUNCH=1 ;;
    *) echo "Unknown option: $arg (only --build, --launch)" >&2; exit 2 ;;
  esac
done

if [[ "$BUILD" == 1 ]]; then
  echo "… release build (this takes a while)"
  (cd "$APP_DIR" && npm run tauri build >/tmp/ephe-tauri-build.log 2>&1) || {
    echo "✗ build failed — log: /tmp/ephe-tauri-build.log" >&2
    tail -20 /tmp/ephe-tauri-build.log >&2
    exit 1
  }
fi

BUNDLE="$TARGET_ROOT/macos/Ephe.app"
if [[ ! -d "$BUNDLE" ]]; then
  echo "✗ no bundle under $BUNDLE — build it first (ephe desktop or --build)." >&2
  exit 1
fi

# We do not want the freshly built bundle compared against itself.
if [[ "$(cd "$BUNDLE" && pwd -P)" == "$(cd "$INSTALL_TO" 2>/dev/null && pwd -P || echo none)" ]]; then
  echo "✗ source and destination are the same — nothing to do." >&2
  exit 2
fi

if pgrep -f "Ephe.app/Contents/MacOS" >/dev/null 2>&1; then
  echo "⚠ Ephe is still running. The new version takes effect only after a restart;"
  echo "  running windows keep the old code (there is no instance guard)."
fi

if [[ -d "$INSTALL_TO" ]]; then
  TRASH="$HOME/.Trash/Ephe-$STAMP.app"
  echo "… previous version → $TRASH"
  mv "$INSTALL_TO" "$TRASH"
fi

echo "… installing $BUNDLE → $INSTALL_TO"
ditto "$BUNDLE" "$INSTALL_TO"

# LaunchServices: one address per product. Without this, dead build paths and DMG
# shells stay in the register and win when `open -a Ephe` runs.
LSR=/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister
if [[ -x "$LSR" ]]; then
  echo "… LaunchServices reset"
  "$LSR" -kill -r -domain local -domain system -domain user >/dev/null 2>&1 || true
  "$LSR" -f "$INSTALL_TO" >/dev/null 2>&1 || true
fi

echo "✓ installed: $INSTALL_TO"
if diff -rq "$BUNDLE" "$INSTALL_TO" >/dev/null 2>&1; then
  echo "  content matches the build (diff -rq empty)."
else
  echo "  ⚠ content differs — please check:" >&2
  diff -rq "$BUNDLE" "$INSTALL_TO" | head -5 >&2
fi
echo
# A backend tree that lags the app is invisible to the version string: both can
# say 0.1.11 while the tree is nine commits behind. Compare the commits and say
# so, without moving anything on the owner's machine.
REPO_ROOT="$(cd "$APP_DIR/.." && pwd)"
BACKEND_JSON="$HOME/.ephe/desktop.json"
if [[ -f "$BACKEND_JSON" ]] && command -v python3 >/dev/null 2>&1; then
  BACKEND_ROOT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("project_root",""))' "$BACKEND_JSON" 2>/dev/null || true)"
  if [[ -n "${BACKEND_ROOT:-}" && -d "$BACKEND_ROOT" ]]; then
    APP_SHA="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD 2>/dev/null || true)"
    BACKEND_SHA="$(git -C "$BACKEND_ROOT" rev-parse --short=12 HEAD 2>/dev/null || true)"
    if [[ -n "$APP_SHA" && -n "$BACKEND_SHA" && "$APP_SHA" != "$BACKEND_SHA" ]]; then
      echo "  ⚠ the backend runs $BACKEND_SHA, this app was built from $APP_SHA" >&2
      echo "    sync it: git -C \"$BACKEND_ROOT\" merge --ff-only && (cd \"$BACKEND_ROOT/app\" && npm run build)" >&2
    elif [[ -n "$APP_SHA" ]]; then
      echo "  backend tree matches the app build ($APP_SHA)"
    fi
  fi
fi
echo "Undo:  mv \"$HOME/.Trash/Ephe-$STAMP.app\" $INSTALL_TO"
[[ "$LAUNCH" == 1 ]] && open "$INSTALL_TO" && echo "… started"
exit 0
