# Updates — desktop app, PWA and terminal

Three surfaces, three update paths. The desktop app and the PWA can follow
published releases only or every commit on `main`; the terminal always follows
release tags. The release channel is the default everywhere.

| Surface | Default | Commit channel | What actually moves |
|---|---|---|---|
| Desktop app | `release` | backend + PWA only | the signed `.app` plus the backend checkout at its tag; between releases the backend and the PWA |
| PWA in a browser | `release` | backend + PWA | the backend checkout and the assets the server sends |
| Terminal CLI/TUI | `release` only | not offered | the checkout, fast-forwarded to a release tag |

## The two channels

`release` installs a tagged release. A tag is cut deliberately and the desktop
bundle that carries it is signed. This is the quiet, default channel.

`commit` also follows the tip of `main` between tags. The comparison is
ancestry-based: a checkout that is ahead of `main` or has diverged from it is
never told to go backwards. An untagged build is named honestly, for example
`0.6.3+1a2b3c4d5e6f` — the version the tree carries plus the commit it runs.
The channel does not create a release and does not cut a tag; normal commits
between releases stay normal commits. An installation without a git checkout
cannot follow commits — it has no build commit to compare and stays on releases.

The channel is stored as the deep setting `appearance.update_channel` and can
be overridden for one process with `EPHE_UPDATE_CHANNEL=release|commit`. Unknown
values, and the old names `stable` and `main`, normalise to `release`/`commit`;
anything unrecognised falls back to `release`. A stored old value keeps its
meaning: `stable` is `release`.

## Desktop app

The native shell updates through the Tauri updater. Its endpoint is
`https://github.com/bemlerlabs/ephe/releases/latest/download/latest.json`; the
manifest and the bundle are checked against the minisign public key pinned in
`app/src-tauri/tauri.conf.json`. A draft release becomes installable only when
the owner publishes it.

A release update replaces the `.app` and then pins the backend checkout to the
shell's own tag (`v<version>`, not `origin/main`), so the backend runs the code
the signed shell was built from. The installer step refreshes the Python
environment and the PWA bundle beside that tree.

The commit channel cannot replace the shell. There is no signed manifest for an
arbitrary commit, and the WebView the shell draws is bundled inside the `.app`.
On the commit channel an update therefore moves the backend tree and the PWA it
serves; a restart loads the new backend, and the native shell catches up with
the next signed release. The update dialog states this instead of promising
a shell update it cannot perform. The desktop app's own "Install & restart" is
only ever offered for a release.

## PWA in a browser

The PWA is the built `app/dist` served by the local backend. It has no app
bundle to replace, so it updates by moving the backend tree it is served from:

- release: `POST /api/update/release` moves the checkout to the newest release
  tag and runs the installer;
- commit: `POST /api/update/apply` moves the checkout to the tip of `main` and
  runs the installer.

The service worker shows a reload offer when a new worker is waiting; after an
applied backend update the update dialog offers the reload itself. The running Python process keeps the imports it started
with, so Python changes take effect at the next backend start while the served
web build can reload at once. A browser cannot install a desktop bundle, so the
release path falls back to the release page when the installation has no
checkout the backend can move. The PWA is not signed by the Tauri key — it is code delivered
by the local backend, whose integrity is the git tree plus the transport the
tree came from.

## Terminal CLI and TUI

The terminal is release-only by design. `ephe update` asks the release feed and
fast-forwards the checkout to that release tag; it never asks for `main`'s tip
and never follows untagged merges. A merged pull request between two releases
is not offered in the TUI, and a stored `commit` setting changes nothing there.
If the newest release is already this build, the command is a no-op with exit
code 0, even when the checkout carries commits past that tag. If a newer release
exists but the checkout already contains it, the command refuses instead of
rewriting the tree backwards.

`ephe update --channel commit` is the explicit exception, for a checkout that
serves the desktop or PWA backend. It follows `main`'s tip and says so; after
that the checkout is no longer release-pinned. The default command does not do
this.

`ephe doctor` reports the release answer as well, because that is the row's
command. `EPHE_NO_UPDATE_CHECK=1` turns automatic checks off; an explicit
`ephe update` still runs because it is the user's own request.

## What "every commit" means

`commit` compares the build's commit with the tip of `main` through the GitHub
compare API. Only a build that is strictly behind is offered an update; a build
that is ahead, identical, or diverged is not. The API answers with the number of
commits between the two points, the tip's short sha, and the tip's subject line.
The build's reported version is `<release-version>+<sha>`, so a commit build is
never mistaken for a released version.

Between releases the team commits and merges as usual. Nothing is tagged until a
release is actually cut (`scripts/release_cut.sh`); the existence of newer
commits does not create a release and does not change the CLI's release-only
path.

## Switching channels

- Settings → Appearance → **Update channel** (deep setting
  `appearance.update_channel`) is the durable switch for the desktop app and the
  PWA.
- `EPHE_UPDATE_CHANNEL=release|commit` pins one process.
- `ephe update --channel commit` moves a backend tree to `main` once. The next
  `ephe update` asks releases only again; the checkout stays on `main` and is not
  moved backwards to a tag.

Switching to `commit` means accepting that the desktop shell itself will trail
the backend until the next release; switching back to `release` stops offering
untagged merges immediately. The update dialog names the channel the answer came
from and the one the surface is set to, so the two facts cannot be confused.

## Failures and refusals

The check is fail-soft: an unreachable release source yields `available: false`
with an error field, never a crash and never the claim "you are current". The
answer is cached for six hours (five minutes after a failure), per channel, so a
release check and a commit check cannot read each other's answer.

An update stops before running anything when the tree cannot be moved: no git
checkout, another branch (the release path also accepts a detached tag), local
changes, or a second update already running. The API answers with a reason code
(`not_a_checkout`, `not_on_main`, `dirty_tree`, `busy`, `release_unreachable`,
`fetch_failed`, `tag_missing`, `release_failed`, `ahead_of_release`,
`install_failed`) and the surface owns the sentence the user reads.

## What is signed, and what is not

- Desktop release: the updater manifest (`latest.json`) and the bundle carry the
  minisign signature checked against the key in `tauri.conf.json`. A tag is not
  installable until its release is published.
- Release tags: a git tag on `main`; the release runbook and provenance checks
  decide that the tag sits on the trunk. The tag itself is not a minisign
  artifact.
- Commit channel: nothing is signed. The tree comes from the git remote over
  TLS, and `install.sh` runs the tree it just checked out. A commit update on the
  desktop therefore never replaces the signed shell; it moves the backend and
  the PWA and says so.
- PWA: the assets are served by the local backend and are not signed by the
  Tauri key. Their integrity is the checked-out git tree plus the transport it
  came from.
