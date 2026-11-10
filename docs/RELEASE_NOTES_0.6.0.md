# Ephe 0.6.0 — release notes

Written against the tree at `d8bfda9a`, the commit this tag ships. Every number below was read
from a command on that tree; the command is named beside it.

0.6.0 is the creator-mode wave. It carries 327 commits since `v0.5.7`
(`git rev-list --count v0.5.7..HEAD`) and the install lines name the new tag. The per-commit
record is [`CHANGELOG.md`](../CHANGELOG.md) under `[0.6.0]` — 163 of its rows name their commit.
This page does not repeat that list. It says what the release is for, what it deliberately does
not contain, and what an upgrade has to know.

## What is in it

**Creator mode is a fourth composer tile** (`app/src/components/dashboard/chat/ComposerModeMenu.tsx`)
and its own guard. The tile asks for the session's consent first, and the session then holds any of
`code`, `files`, `network` through `GET|PUT /api/creator/consent`
(`server/routes/creator.py`). The five calls are kernel tools (`core/tools/creator_tools.py`):
`create_plugin_scaffold`, `install_plugin_bundle`, `read_plugin_source`, `verify_plugin_bundle`,
`write_plugin_source`. A call whose privilege the session does not hold is refused before its
handler runs, and its name leaves the offer list, so the model is not invited to plan around a
refusal. Commits `b4daa41c`, `78859a31`, `80e3852f`, `9e55aaf4`, `cecb0dee`.

**Extensions 1.0 v2 bundles.** A bundle declares its surface, its tool families and its data
roots, and the platform derives the served tool names from the manifest (`45ffc36d`). A mounted
surface is served with its own policy and its own credential (`53373610`, `b4775433`), a bundle's
tool runs in a bounded child rather than in the backend (`24ab5d99`), and a bundle's stored state
has a ceiling that is stated in bytes (`dde4ef8a`, `31ffba5e`). The first declarative v2 surface
ships as `plugins/countdown` (`472570f8`, `f028d493`).

**The creation eval.** 24 cases over six categories, each with a turn half and an end-state half,
plus a rubric. The harness now runs in a home of its own — `--browser` refuses without `--config`
(`1b59de25`, `626ec7e7`) — installs and enables the bundle a turn staged, inside that home
(`7fefe776`), derives the check → producing-call → privilege table from the guard instead of
restating it (`5bfa26b9`), and no longer reads the checkout's own plugin catalogue (`8b2e9b96`).

**Security and correctness fixes a person notices.** The redactor closes the word-boundary gap
that could leave a secret-shaped token in a receipt line, and reads the token body so ordinary
compounds stay words (`0ac4bbb9`, `dcfbe87f`, `ebdcc7ba`). A loopback mutation needs the app
origin or the LAN token, and a mount nonce is required on loopback (`a720fb15`, `2d0919c1`).
`plugin_manager` answers "what is installed" without being told a verb (`ad48c2fc`); the
discovery answers are English like the rest of the turn (`454577a5`); a turn that can ask a
question asks it with `ask_user` instead of writing a JSON blob as answer text (`7e63af4b`);
`ephe doctor` prints the path beside the version the manifest at that path reports (`456be950`).

## Not in this release

The eval's own rate is **not** part of this release. The 24-case run of 2026-11-09 spent 24 turns
with `unusable=0` and 81 tool calls, and graded 10 of 24 cases. Eleven of the fourteen failures are
the set's or the harness's own doing, so the number measures the instrument, not the product, and
stays out of every page and comparison until the repairs land
(`register/00-RUN-2026-11-09-FAILURES.md`, the fourteen rows with their verbatim evidence).

Open, with the record that holds them:

- **Page storage in a mounted surface (P0).** Three bundles wrote `localStorage`; the mount
  refuses it in the engine's own words. `docs/decisions/PLUGIN_SURFACE_PAGE_STORAGE.md` is an open
  owner decision and no product code was changed for it.
- **The request leaves the model-visible turn (P0).** After the first tool round, six of 24
  transcripts state the request is missing. It has no fix in this release.
- **Refusal halves and capability rows (P1).** A case can ask for a refusal whose call the grant
  never offered, and for a manifest family the prompt never asks for.
- **Two underspecified cases (P2).** `creation-11` and `creation-13` ask for data they never
  supply.
- **One workspace authority (#153).** `docs/decisions/workspace-authority.md` is a proposal plus a
  pin; `get_workspace_dir()` still falls back to a directory inside `DENY_ROOTS`.
- **`ask_user` in a tool-less turn.** The fix covers tool turns; a terminal turn without tools can
  still write the JSON blob as answer text.
- **Windows installation** is documented but not verified end to end.
- **No catalogue for third-party publishers.** MCP servers are added by hand; the one bundled
  third-party skill pack ships as bundled content and installs after a confirmation, and that is
  not a marketplace.
- **Unsigned desktop bundles.** Without a signing key in the release environment the bundler
  writes no signature and the updater manifest answers 404 (`.github/workflows/release.yml`). A
  key that does not match the updater public key the app ships is refused by the installed app;
  `scripts/release_checklist.py` reports which key the environment holds.
- **The notes register keeps its open rows.** 35 were open on 2026-11-09, three in progress
  (`HANDOFF_2026-11-09_CREATOR_MODE.md` §6). This release closes none of them by declaration.

## Known gaps in this tree

- **The catalogue does not carry the countdown bundle.** `plugins/` holds 17 first-party bundles
  and `plugin-catalog.json` lists all 17, but the shipped `marketplace/index.json` lists 16 and
  carries no artifact for `countdown`. The counts in the READMEs and in
  [`PLUGINS_OVERVIEW.md`](PLUGINS_OVERVIEW.md) follow that index — nine plugins and seven presets —
  so the new bundle is on disk and not in the Extension Center. Rebuild the index (and then say
  ten) or keep the bundle out of the release.
- **`plugin-catalog.json` disagrees with the vision bundle.** `scripts/generate_plugin_catalog.py
  --check` fails on a clean tree: the committed row for `vision` carries `aba76bfc…`, the committed
  directory hashes to `279d3e69…`. `dir_sha256` hashes every file in a bundle, and the committed
  row was generated in a working copy that carried an untracked
  `plugins/vision/tools/__pycache__`; a clean checkout has not got one.

## Upgrade from 0.5.7

- **Six carriers move together.** `pyproject.toml` `[project].version` is the source;
  `app/package.json`, `app/src-tauri/tauri.conf.json`, `app/src-tauri/Cargo.toml`, `uv.lock` and
  `app/src-tauri/Cargo.lock` follow. `tests/test_version_sync.py` names all six.
- **The install lines move with them.** The three READMEs and the four start documents name
  `v0.6.1` in the installer URL and in the sentence under it. A saved `v0.5.7` command still
  works; it installs the older release.
- **A bundle is installed by its staged name.** `install_plugin_bundle` verifies the staged bytes
  in place, extracts them under the plugins root and answers with the manifest's name and version,
  the directory hash and the `enabled` state it read; the Extensions surface holds the switch
  after that.
- **No data migration is required.** Settings, sessions, artifacts and the engine key keep their
  paths (`~/.ephe`), and the engine key keeps its binding sidecar.

## Gates run for this tag

`python scripts/readme_check.py --root .` and `--public` (the second is green only once the tag
exists), `python scripts/changelog_unreleased.py --check` (326 commits read, pass), and `python
scripts/catalog_freshness.py`, which is red for the `vision` row above. The two backend tests that
hold a fixed port need an idle machine (`HANDOFF_2026-11-09_CREATOR_MODE.md` §3a); the full-suite
number for this tag is not published on this page.
