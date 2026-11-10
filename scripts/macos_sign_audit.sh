#!/usr/bin/env bash
# macos_sign_audit.sh — what the seal of a macOS bundle actually says.
#
# Why this exists (issue #192): the shipped `Ephe.app` carried a *linker* signature
# only — `flags=0x20002(adhoc,linker-signed)`, `Info.plist=not bound`,
# `Sealed Resources=none`. `codesign --verify --strict` failed on it with
# "code has no resources but signature indicates they must be present", `spctl`
# rejected it, and no notarization ticket existed. Every privacy grant macOS keys to
# the code requirement (the microphone among them) is lost on each rebuild while the
# signature is a build hash.
#
# The tool prints the four answers in the order a maintainer reads them and exits on
# the first one that is a defect:
#
#   codesign --verify --deep --strict   the seal itself (exit 1 = not signed or broken)
#   codesign -dv --verbose=2            identity, CDHash flags, TeamIdentifier
#   spctl -a -vv                        what Gatekeeper says about a downloaded copy
#   xcrun stapler validate              whether a notarization ticket is stapled
#
# The seal is the only gate that fails this script. `spctl` rejecting an ad-hoc bundle
# is the expected, documented state (no Developer ID, no ticket) — it is reported and
# the exit stays 0, because a script that failed on the known state could not be used
# to check a local build.
#
# Every form ends with `state=`: `adhoc-not-notarized` (what a release built without
# Apple secrets produces), `developer-id-notarized`, `developer-id-not-notarized`, or
# `invalid`. `--summary` wraps that line in a markdown block for $GITHUB_STEP_SUMMARY,
# followed by the sentence that says what the state means for someone opening the
# download.
#
# Nothing here signs anything: the signing decision belongs to the build
# (`--config '{"bundle":{"macOS":{"signingIdentity":"-"}}}'` for an ad-hoc local/CI
# build, the Developer ID identity plus the notarization variables when they exist),
# and this reads what that decision produced.
#
# Usage: scripts/macos_sign_audit.sh <path/to/App.app | path/to/App.dmg>
#        scripts/macos_sign_audit.sh --quiet <bundle>     one line
#        scripts/macos_sign_audit.sh --summary <bundle>   a markdown block for $GITHUB_STEP_SUMMARY

set -euo pipefail

QUIET=0
SUMMARY=0
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --summary) SUMMARY=1 ;;
    --help|-h)
      printf '%s\n' "Usage: scripts/macos_sign_audit.sh [--quiet|--summary] <App.app|App.dmg>"
      printf '%s\n' "Prints codesign --verify --deep --strict, codesign -dv, spctl and stapler."
      printf '%s\n' "Exit 0 when the seal is valid (an ad-hoc seal is valid), 1 when it is not."
      printf '%s\n' "--quiet prints one line; --summary prints a markdown block for a CI step summary."
      exit 0
      ;;
    -*) printf '%s\n' "Unknown option: $arg" >&2; exit 2 ;;
    *)
      if [[ -n "$TARGET" ]]; then
        printf '%s\n' "Only one bundle or disk image can be audited per run." >&2
        exit 2
      fi
      TARGET="$arg"
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  printf '%s\n' "Usage: scripts/macos_sign_audit.sh [--quiet|--summary] <App.app|App.dmg>" >&2
  exit 2
fi
if [[ ! -e "$TARGET" ]]; then
  printf '%s\n' "No such bundle: $TARGET" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  printf '%s\n' "This audit reads macOS signatures and only runs on Darwin (this is $(uname -s))." >&2
  exit 2
fi

# A disk image is audited through the bundle it carries, which is what a person
# downloads and what Gatekeeper sees; the mount is private to this run.
MOUNT=""
cleanup() {
  if [[ -n "$MOUNT" ]]; then
    hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true
    rmdir "$MOUNT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

BUNDLE="$TARGET"
case "$TARGET" in
  *.dmg)
    MOUNT="$(mktemp -d "${TMPDIR:-/tmp}/ephe-dmg-XXXXXX")"
    hdiutil attach "$TARGET" -nobrowse -readonly -mountpoint "$MOUNT" -quiet >/dev/null
    app="$(find "$MOUNT" -maxdepth 1 -name '*.app' -print -quit)"
    if [[ -z "$app" ]]; then
      printf '%s\n' "The disk image carries no .app at its top level: $TARGET" >&2
      exit 2
    fi
    BUNDLE="$app"
    ;;
esac

# The seal is the one verdict this script is allowed to fail on. `|| rc=$?` keeps
# `set -e` out of it while the exit code still reaches the caller.
verify_rc=0
verify_out="$(codesign --verify --deep --strict --verbose=2 "$BUNDLE" 2>&1)" || verify_rc=$?

detail="$(codesign -dv --verbose=2 "$BUNDLE" 2>&1 || true)"
spctl_rc=0
spctl_out="$(spctl -a -vv "$BUNDLE" 2>&1)" || spctl_rc=$?
staple_rc=0
staple_out="$(xcrun stapler validate "$BUNDLE" 2>&1)" || staple_rc=$?

team="$(printf '%s\n' "$detail" | sed -n 's/^TeamIdentifier=//p' | head -1)"
identity="$(printf '%s\n' "$detail" | sed -n 's/^Signature=//p' | head -1)"
identifier="$(printf '%s\n' "$detail" | sed -n 's/^Identifier=//p' | head -1)"
flags="$(printf '%s\n' "$detail" | sed -n 's/.*flags=\(0x[0-9a-fA-F]*\).*/\1/p' | head -1)"

# One token for the two facts a release reader needs: does the seal hold, and has Apple
# seen the build. The second half is not a gate — a release with no Apple account is a
# supported release — so `spctl` and `stapler` only ever contribute to the word after the
# dash. `state=invalid` is the one that fails.
if [[ "$verify_rc" != "0" ]]; then
  state="invalid"
elif [[ -z "$team" || "$team" == "not set" ]]; then
  if [[ "$staple_rc" == "0" ]]; then state="adhoc-notarized"; else state="adhoc-not-notarized"; fi
else
  if [[ "$staple_rc" == "0" ]]; then state="developer-id-notarized"; else state="developer-id-not-notarized"; fi
fi

# The quiet line and the summary block report the same facts in the same order; a summary
# that disagreed with the log would be the thing this script exists to prevent.
report_line() {
  printf 'seal=%s identifier=%s signature=%s team=%s spctl=%s notarized=%s state=%s\n' \
    "$([[ "$verify_rc" == "0" ]] && printf valid || printf invalid)" \
    "${identifier:-?}" "${identity:-?}" "${team:-none}" \
    "$([[ "$spctl_rc" == "0" ]] && printf accepted || printf rejected)" \
    "$([[ "$staple_rc" == "0" ]] && printf yes || printf no)" \
    "$state"
}

if [[ "$SUMMARY" == "1" ]]; then
  # A markdown block for $GITHUB_STEP_SUMMARY: the release's own record of what it signed.
  printf '### macOS bundle seal: `%s`\n\n' "$TARGET"
  printf '```\n'
  report_line
  printf '```\n\n'
  case "$state" in
    invalid)
      printf 'The seal is **invalid**: `codesign --verify --deep --strict` fails, so a downloaded copy cannot be verified and macOS cannot pin a privacy grant to this bundle. Rebuild it with a signing identity (see `docs/INSTALL.md`, "The macOS bundle seal").\n'
      ;;
    adhoc-not-notarized)
      printf 'Not notarized: the bundle is ad-hoc signed — no Developer ID and no Apple ticket — so Gatekeeper refuses a copy that arrives with a quarantine flag. That is the expected state for a release built without Apple secrets, and the seal above is valid. Install with right-click → Open, or `xattr -d com.apple.quarantine /Applications/Ephe.app` (see `docs/INSTALL.md`).\n'
      ;;
    developer-id-not-notarized)
      printf 'Not notarized: the bundle carries a Developer ID signature and no stapled ticket, so Gatekeeper still refuses a copy that arrives with a quarantine flag. The seal above is valid; notarization is optional (see `docs/INSTALL.md`).\n'
      ;;
    *)
      printf 'Notarized: Developer ID signature with a stapled ticket; a downloaded copy opens without the first-launch step.\n'
      ;;
  esac
elif [[ "$QUIET" == "1" ]]; then
  report_line
else
  printf '%s\n' "codesign --verify --deep --strict  $([[ "$verify_rc" == "0" ]] && echo PASS || echo FAIL)"
  printf '%s\n' "$verify_out"
  printf '%s\n' ""
  printf '%s\n' "codesign -dv"
  printf '%s\n' "$detail"
  printf '%s\n' ""
  printf '%s\n' "spctl -a -vv  ($([[ "$spctl_rc" == "0" ]] && echo accepted || echo rejected))"
  printf '%s\n' "$spctl_out"
  printf '%s\n' ""
  printf '%s\n' "xcrun stapler validate  ($([[ "$staple_rc" == "0" ]] && echo ticket || echo no ticket))"
  printf '%s\n' "$staple_out"
  printf '%s\n' ""
  printf '%s\n' "state: $state"
  printf '%s\n' ""
fi

if [[ "$verify_rc" != "0" ]]; then
  printf '%s\n' "The bundle seal is invalid: a downloaded copy cannot be verified, and macOS binds every privacy grant to a requirement this bundle does not satisfy. Rebuild it with a signing identity (see docs/INSTALL.md, 'The macOS bundle seal')." >&2
  exit 1
fi

# The seal is valid. Two states are legal and they mean different things to a user:
# a Developer ID signature with a stapled ticket (a downloaded copy opens normally),
# or an ad-hoc signature (Gatekeeper rejects the downloaded copy; right-click → Open).
if [[ "$QUIET" != "1" && "$SUMMARY" != "1" ]]; then
  if [[ "$team" == "not set" || -z "$team" ]]; then
    printf '%s\n' "Ad-hoc seal: valid on this machine, and Gatekeeper rejects a copy that arrives with a quarantine flag. Not notarized — see docs/INSTALL.md."
  elif [[ "$staple_rc" != "0" ]]; then
    printf '%s\n' "Developer ID seal without a stapled ticket: the seal is valid and the build is not notarized, so the download needs the notarization step (APPLE_ID/APPLE_TEAM_ID or the API-key pair) before it opens without a prompt."
  fi
fi
exit 0
