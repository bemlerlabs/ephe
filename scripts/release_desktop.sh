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

echo "  … building Ephe ${VERSION} with update artifacts"
(cd app && npx tauri build --config '{"bundle":{"createUpdaterArtifacts":true}}')

BUNDLE="app/src-tauri/target/release/bundle"
# Tauri writes `<product>_<arch>.app.tar.gz` (Ephe_aarch64 on this Mac), not the
# bare `<product>.app.tar.gz` this script named in four places — so the feed
# pointed at a URL that 404s and --publish could not upload what it built.
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
node - "$VERSION" "$SIG" "$FEED" "$(basename "$ARTIFACT")" <<'NODE'
const [version, sigPath, out, assetName] = process.argv.slice(2)
const fs = require('fs')
const feed = {
  version,
  notes: fs.existsSync('CHANGELOG.md')
    ? fs.readFileSync('CHANGELOG.md', 'utf8').split('\n## ')[1]?.split('\n').slice(1).join('\n').trim().slice(0, 800) || `Ephe ${version}`
    : `Ephe ${version}`,
  pub_date: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
  platforms: {
    'darwin-aarch64': {
      signature: fs.readFileSync(sigPath, 'utf8').trim(),
      url: `https://github.com/bemlerlabs/ephe/releases/download/v${version}/${assetName}`,
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
  if gh release view "$TAG" >/dev/null 2>&1; then
    echo "  ⚠ $TAG already exists — nothing created. Upload the artifacts again:"
    echo "    gh release upload $TAG --clobber $ARTIFACT $SIG ${BUNDLE}/macos/latest.json ${BUNDLE}/dmg/Ephe_${VERSION}_aarch64.dmg"
    exit 0
  fi
  # The updater hangs on two things: the artifact AND the feed in the same
  # release. If either is missing, the endpoint answers 404 and the surface
  # says "check not possible" — which is then rightly what it says.
  gh release create "$TAG" \
    "$ARTIFACT" \
    "$SIG" \
    "${BUNDLE}/macos/latest.json" \
    "${BUNDLE}/dmg/Ephe_${VERSION}_aarch64.dmg" \
    --title "Ephe ${VERSION}" \
    --notes "$(node -p "require('${FEED/#app\//}').notes" 2>/dev/null || echo "Ephe ${VERSION}")"
  echo
  echo "  ✓ $TAG published. Verify with:"
  echo "    curl -o /dev/null -w '%{http_code}\n' https://github.com/bemlerlabs/ephe/releases/latest/download/latest.json"
  exit 0
fi

echo
echo "  Publish with:  scripts/release_desktop.sh --publish"
echo "  (or only re-upload the artifacts: gh release upload v${VERSION} --clobber …)"
