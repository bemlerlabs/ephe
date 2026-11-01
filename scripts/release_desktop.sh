#!/usr/bin/env bash
# Ephe — desktop release with a signed update artifact.
#
# Why this script exists: the updater is wired into the app
# (tauri_plugin_updater in src-tauri/src/lib.rs, pubkey and endpoint in
# app/src-tauri/tauri.conf.json), but a plain `npm run tauri build` produces
# NEITHER the signed .app.tar.gz nor latest.json without createUpdaterArtifacts.
# The endpoint therefore answered 404, and since R2-U the surface has honestly
# said "check not possible" instead of "you are up to date".
#
# The key lives on this machine at ~/.tauri/ephe.key (0600), its
# password in the macOS keychain under the service name
# ephe-updater-signing — not in a plaintext file, not in the repo, never in
# any output. Anyone building from another machine exports both themselves.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(node -p "require('./app/package.json').version")"
KEY_FILE="${EPHE_UPDATER_KEY:-$HOME/.tauri/ephe.key}"

# The repository the release is published to, and the one the updater feed points
# at — one value, because a feed that names a different repository than the
# publish target describes artifacts that no client will ever fetch. This checkout
# resolves `gh` to its first remote, which is the private development repository,
# so every call below names the target instead of inheriting it.
RELEASE_REPO="${EPHE_RELEASE_REPO:-bemlerlabs/ephe}"

if [[ ! -f "$KEY_FILE" ]]; then
  echo "  ✗ signing key missing: $KEY_FILE" >&2
  echo "    create it: npx tauri signer generate -w ~/.tauri/ephe.key -p <PASSWORD>" >&2
  echo "    then put the public part (ephe.key.pub) into" >&2
  echo "    app/src-tauri/tauri.conf.json → plugins.updater.pubkey." >&2
  exit 1
fi

PW="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"
if [[ -z "$PW" ]] && command -v security >/dev/null 2>&1; then
  PW="$(security find-generic-password -s ephe-updater-signing -a "$USER" -w 2>/dev/null || true)"
fi
if [[ -z "$PW" ]]; then
  echo "  ✗ password for the signing key not found." >&2
  echo "    it is read from \$TAURI_SIGNING_PRIVATE_KEY_PASSWORD or from the" >&2
  echo "    keychain: security add-generic-password -s ephe-updater-signing \\" >&2
  echo "      -a \"\$USER\" -w <PASSWORD>" >&2
  exit 1
fi

# Tauri's build wants the key CONTENT in the variable. With only the path set it
# fails late, after the whole bundle is built, with "a public key has been
# found, but no private key". Read it here so the failure is immediate.
export TAURI_SIGNING_PRIVATE_KEY="$(cat "$KEY_FILE")"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$PW"

# The pinned public key decides which private key may sign. Measured on 2026-11-01: this
# machine's `~/.tauri/ephe.key` carries key id 6cf6767f2631dfdd while
# `app/src-tauri/tauri.conf.json` pins e01157dba5c1d5b5 — the key the release environment
# holds. A bundle signed here uploads cleanly and every installed client then refuses the
# update, which reads as a broken feed rather than as the wrong key. So the run stops before
# building, on a probe signature, and names both ids.
PROBE_DIR="$(mktemp -d)"
NOTES_FILE=""
trap 'rm -rf "$PROBE_DIR" ${NOTES_FILE:+"$NOTES_FILE"}' EXIT
printf 'ephe updater signing key probe' >"$PROBE_DIR/key-probe"
(cd app && npx tauri signer sign "$PROBE_DIR/key-probe" >/dev/null) 2>&1 | tail -2
KEY_IDS="$(node -e '
const fs = require("fs"), path = require("path")
const conf = JSON.parse(fs.readFileSync("app/src-tauri/tauri.conf.json", "utf8"))
// A Tauri key or signature block is base64 of "untrusted comment: …\n<keydata>"; the key id
// is bytes 2..10 of the decoded second line, for a public key and for a signature alike.
const keyIdOf = (wrapped) => {
  const text = Buffer.from(wrapped.trim(), "base64").toString("utf8")
  const line = text.split("\n").filter(Boolean)[1]
  if (!line) throw new Error("not a minisign block")
  return Buffer.from(line.trim(), "base64").subarray(2, 10).toString("hex")
}
const pinned = keyIdOf(conf.plugins.updater.pubkey)
const probePath = path.join(process.argv[1], "key-probe.sig")
console.log((fs.existsSync(probePath) ? keyIdOf(fs.readFileSync(probePath, "utf8")) : "none") + " " + pinned)
' "$PROBE_DIR")"
read -r SIGN_ID PIN_ID <<<"$KEY_IDS"
if [ "$SIGN_ID" = "$PIN_ID" ]; then
  echo "  ✓ signing key $SIGN_ID matches the pinned updater key"
elif [ "$SIGN_ID" = "none" ]; then
  echo "  ✗ the probe signature was not written, so the key cannot be identified." >&2
  echo "    the usual cause is a wrong password for $KEY_FILE." >&2
  exit 1
else
  echo "  ✗ the signing key is ${SIGN_ID}, the app pins ${PIN_ID}." >&2
  echo "    an artifact signed here is refused by every client's updater. Export the" >&2
  echo "    release environment's key to \$EPHE_UPDATER_KEY, or let the release" >&2
  echo "    workflow build the bundle: it holds the matching private key." >&2
  exit 1
fi

echo "  … building Ephe ${VERSION} with update artifacts"
(cd app && npx tauri build --config '{"bundle":{"createUpdaterArtifacts":true}}')

BUNDLE="app/src-tauri/target/release/bundle"
# The updater artifact's name is not stable across the two paths that build it: the release
# workflow's mac leg uploads `Ephe_aarch64.app.tar.gz`, while a `tauri build` on this machine
# wrote `Ephe.app.tar.gz`. The feed's URL is built from whatever is found, because the bare
# name this script used to hardcode matched nothing on either path and the feed 404s.
ARTIFACT="$(find "${BUNDLE}/macos" -maxdepth 1 -name '*.app.tar.gz' -print -quit 2>/dev/null || true)"
if [[ -z "$ARTIFACT" ]]; then
  echo "  ✗ the build ran through, but the updater artifact is missing under ${BUNDLE}/macos" >&2
  echo "    without it the updater has nothing to install." >&2
  exit 1
fi
SIG="${ARTIFACT}.sig"
if [[ ! -f "$SIG" ]]; then
  echo "  ✗ the build ran through, but the signature is missing: $SIG" >&2
  echo "    without it the updater will not accept the artifact." >&2
  exit 1
fi

FEED="${BUNDLE}/macos/latest.json"
# The release body comes from the same script the release workflow uses, so the
# desktop feed's notes and the GitHub release's description are one text. The slice this
# script used to take off CHANGELOG.md was `split('\n## ')[1]`, which is the
# `[Unreleased]` block: the update window rendered a sha inventory that named the wave
# "below" instead of the release the reader is installing.
NOTES_FILE="$(mktemp)"
if ! python3 scripts/release_notes.py "$VERSION" >"$NOTES_FILE" 2>/dev/null || [ ! -s "$NOTES_FILE" ]; then
  printf 'Ephe %s' "$VERSION" >"$NOTES_FILE"
fi
node - "$VERSION" "$SIG" "$FEED" "$(basename "$ARTIFACT")" "$RELEASE_REPO" "$NOTES_FILE" <<'NODE'
const [version, sigPath, out, assetName, repo, notesPath] = process.argv.slice(2)
const fs = require('fs')
const feed = {
  version,
  notes: fs.readFileSync(notesPath, 'utf8').trim(),
  pub_date: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
  platforms: {
    'darwin-aarch64': {
      signature: fs.readFileSync(sigPath, 'utf8').trim(),
      url: `https://github.com/${repo}/releases/download/v${version}/${assetName}`,
    },
  },
}
fs.writeFileSync(out, JSON.stringify(feed, null, 2) + '\n')
NODE

echo
echo "  ✓ artifacts under ${BUNDLE}/macos/ and ${BUNDLE}/dmg/"
ls -1 "${BUNDLE}/macos" "${BUNDLE}/dmg" 2>/dev/null | sed 's/^/      /'

if [[ "${1:-}" == "--publish" ]]; then
  TAG="v${VERSION}"
  if gh release view "$TAG" --repo "$RELEASE_REPO" >/dev/null 2>&1; then
    echo "  ⚠ $TAG already exists in $RELEASE_REPO — nothing created. Upload the artifacts again:"
    echo "    gh release upload --repo $RELEASE_REPO --clobber $TAG $ARTIFACT $SIG ${BUNDLE}/macos/latest.json ${BUNDLE}/dmg/Ephe_${VERSION}_aarch64.dmg"
    exit 0
  fi
  # The updater hangs on two things: the artifact AND the feed in the same
  # release. If either is missing, the endpoint answers 404 and the surface
  # says "check not possible" — which is then rightly what it says.
  gh release create "$TAG" \
    --repo "$RELEASE_REPO" \
    "$ARTIFACT" \
    "$SIG" \
    "${BUNDLE}/macos/latest.json" \
    "${BUNDLE}/dmg/Ephe_${VERSION}_aarch64.dmg" \
    --title "Ephe ${VERSION}" \
    --notes "$(cat "$NOTES_FILE")"
  echo
  echo "  ✓ $TAG published in $RELEASE_REPO. Verify with:"
  echo "    curl -o /dev/null -w '%{http_code}\n' https://github.com/${RELEASE_REPO}/releases/latest/download/latest.json"
  exit 0
fi

echo
echo "  Publish with:  scripts/release_desktop.sh --publish"
echo "  (or only re-upload the artifacts: gh release upload --repo $RELEASE_REPO --clobber v${VERSION} …)"
