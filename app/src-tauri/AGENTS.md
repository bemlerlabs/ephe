# Desktop shell

The Rust shell: readiness, the updater and the release bundle.

Applies on top of the root AGENTS.md.

## Readiness contract

The shell writes a readiness payload to the window and the PWA reads it. Two fields are a contract
with the built frontend:

- `ready` — a boolean, true only after a backend answered for itself.
- `state` — one of `ready`, `starting`, `configured`, `unreachable`, `refused`, `unconfigured`.

Release 0.6.8 fixed a composer that stayed locked for a whole session because the surface looked for
`bereit` while the shell wrote `ready`. A field rename ships in both halves and in the same release,
and the default before an answer is `false`: an empty window must never read as a working product.
The failure states carry the sentence and the action (run `ephe doctor`, start the backend), because
the window has no other place to put them.

## Build and test

```bash
cargo test --manifest-path app/src-tauri/Cargo.toml   # the shell's own suite
cargo check --manifest-path app/src-tauri/Cargo.toml  # a fast read after a Rust edit
cd app && npm run tauri build                         # release bundle; also rebuilds the PWA
ephe desktop                                          # build, install to /Applications, open
```

A green PWA build says nothing about the shell. The release build writes
`app/src-tauri/target/release/bundle/macos/Ephe.app`, and that copy is build output rather than an
install; start the installed bundle once after a shell change.

A shell change reaches people only through a signed release ([`docs/RELEASE_POLICY.md`](../../docs/RELEASE_POLICY.md)),
so a `src-tauri/` edit is never a rolling patch.

## Updater and signing

- `tauri.conf.json` carries the updater public key and the release endpoint. The private key never
  enters the tree; CI reads it from the release environment.
- The updater artifact is signed, and the shell verifies it against the embedded public key before
  installing. `createUpdaterArtifacts` lives in the release workflow, never in `tauri.conf.json`: a
  committed `true` makes every local build refuse when the key is absent. Without the key the release
  stays unsigned, publishes no `latest.json`, and the endpoint answers 404, which is better than an
  unsigned manifest.
- The bundle identifier, product name and version fields are release carriers; they move together in
  the bump, never as a drive-by edit.

## Windows and devtools

- `devtools(true)` is guarded by `cfg!(debug_assertions)` for the app's own child windows
  (`src/browser.rs`). A plugin window never sets it: that document is untrusted code and a devtools
  panel could read values back out of it. Do not add a devtools escape in a release path.
- A new window, capability or plugin surface is a security boundary: the capability files under
  `capabilities/` grant a named set, and a broad grant is the review.
- The CSP in `tauri.conf.json` is the release policy; `devCsp` exists for the dev server and does not
  travel into the bundle.
