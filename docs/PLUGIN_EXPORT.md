# Plugin export and import

Measured 2026-11-07 against this tree. This page is the specification. The build
has the install path below; the export command and the file-import command are
the next change.

## 1. What is in the tree

`ephe plugin` accepts four actions: `list`, `enable`, `disable`, `install`
(`ephe_cli.py`, `cmd_plugin`). `install` calls
`core.plugin_market.install_from_marketplace`, which resolves one row of
`plugin-marketplace.json`, fetches the zip, and commits it through
`core.plugin_install`.

`ephe import` is a different command. `cmd_import` reads a reference-client
directory through `core.importer` and maps persona files, skill trees, tool
servers and settings. A plugin zip stays on `ephe plugin`.

`core/plugin_market.py` re-exports the installer and the listing reader. It
has no writer for a zip. The plugin routes under `server/routes` have no
export handler.

The device folder is `config_root()` (`EPHE_CONFIG_DIR`, otherwise `~/.ephe`).
An installed bundle is the directory `config_root()/plugins/<name>/` whose
`ephe-plugin.json` carries that same name (`core/plugin_manifest.py`).

## 2. The bundle

Export packs one installed directory into the zip the installer already
extracts. One member layout keeps two writers on the same shape:

- One member per regular file.
- The member name is `<name>/<relative posix path>`, sorted by that name.
- The manifest member is `<name>/ephe-plugin.json`.
- `ephe-plugin.sig.json` at the plugin root is a member when the file is
  present. `dir_sha256` skips that file name at every depth, so the record
  can sit in the archive while the hash it covers stays the hash of the
  other files (`core/plugin_manifest.dir_sha256`, `SIG_FILENAME`).
- A nested `ephe-plugin.sig.json` stops the export. `verify_plugin_dir`
  already refuses that package, because the same name exclusion would leave
  the nested record outside the hash.
- A symbolic link inside the directory stops the export. `_safe_extract`
  accepts a regular file or a directory member and rejects any other mode.
- Empty directories are omitted. The directory hash reads files.
- Zip metadata is part of the archive hash, so it is fixed: `date_time`
  `1980-01-01 00:00:00`, compression `ZIP_DEFLATED`, the external attributes
  of a regular file (`0o100644` shifted 16 bits), an empty archive comment
  and no extra fields.

Two hashes travel with the bytes:

- `archive_sha256` is `sha256_hex` of the zip bytes (`core/plugin_store.py`).
  A marketplace row stores this value on `sha256`, and
  `_install_from_marketplace` compares it before extraction.
- `directory_sha256` is `dir_sha256` of the plugin directory. The signature
  payload stores this value. It is the identity of the files.

The export command prints both hashes, the name and the version on stdout.
The zip is the only file it writes.

The archive has to satisfy the extractor before it is written: at most
2000 members, at most 50 MiB uncompressed, compression ratio at most 100
(`MAX_ARCHIVE_MEMBERS`, `MAX_ARCHIVE_BYTES`, `MAX_ARCHIVE_RATIO` in
`core/plugin_install.py`).

These trees stay on the machine. They sit outside the plugin directory, so
they stay out of the zip:

- worker state at `config_root()/mcp/homes/plugin_<id>/`, including
  `client-store.json` (`core/plugin_state.state_home`)
- `config_root()/plugin-data/<name>/` (`plugin_versions.DATA_DIRNAME`)
- `plugin-lock.json`, `plugin-signatures.json`, and the installed registry
- the one-slot backup `.previous-<name>` and its sidecar
- the staging directory `.staging-<name>`

## 3. Signing

Signing stays `plugin_signing.sign_plugin_dir`. The export path uses that
function, the file name it already writes, and the algorithm it already
signs with.

When the caller passes a private PEM, export calls

```text
sign_plugin_dir(plugin_dir, private_pem, kid=<caller label>)
```

and then packs the directory, including the record that call just wrote.
The caller label is required. The function's own default, `"first-party"`,
is the label a repository signature uses. A person's export passes the
label they chose. `kid` is inside the signed payload. The verifier tries
the keys of one class and treats `kid` as the signer's own name for that
key (`core/plugin_signing.py`).

The repository key `plugins/first-party.pub.pem` stays the key of bundles
this repository ships. Export leaves that file where it is.

When the directory already holds a signature record and the caller passes
no key, export verifies that record with `verify_plugin_dir` against the
user class (`config_root()/trusted-keys/*.pub.pem`) and packs the directory
when the record matches the current bytes.

When the directory holds no record and the caller passes no key, the zip
is an unsigned local artifact. Import of that zip uses trust `local` and
the existing `allow_local_trust` switch. A listing whose trust is
`official`, `verified` or `community` already requires a signature
(`signature_required`).

A share is the zip. The receiver places the signer's public PEM at
`config_root()/trusted-keys/<label>.pub.pem` before import. Those files are
class `user`. A file import labels a signed zip `community`, and
`_install_from_marketplace` then verifies against that class. A file import
keeps the labels `official` and `verified` for listings that already use
the first-party class.

## 4. Import and the installed identity

Import reads a local zip. It builds a one-entry listing in memory (`name`,
`version`, `sha256`, `trust`, and `signature` when the archive contains a
record) and calls `install_from_marketplace` with a fetcher that returns
those bytes. `marketplace_service` already installs a local source in that
shape. Extraction happens under `plugins/.staging-<name>/payload`. The
rename onto `plugins/<name>` happens after the checks.

`--expect <archive_sha256>` writes that hex string onto the listing. A
different file is the existing status `hash_mismatch`, and the staging
tree is removed. With the flag omitted, the listing hash is the hash of
the file just read, and the signature and the directory hash are the
checks that still run.

The identity check runs after the staged manifest validates and, when a
signature is present, after `verify_plugin_dir` succeeds, and before
`backup_current`. File import passes `on_identity_conflict="refuse"`.
Marketplace callers leave the argument unset. Unset keeps today's rule:
a lower version is `downgrade_refused`, and any other version replaces
the installed directory.

With `refuse`, once an installed directory has a manifest that loads:

- A higher installed version returns `downgrade_refused`. The staging
  tree is removed. `--replace` leaves that refusal in place.
- Equal versions, equal `dir_sha256`, and a pin that is absent or whose
  `sha256` equals the candidate hash: the staging tree is removed, the
  installed directory stays, the pin stays, and the result is `extracted`
  with `unchanged` true.
- Any other difference of version, directory hash or pin hash returns
  `identity_conflict` and removes the staging tree. The result carries
  the installed version, the installed directory hash, the candidate
  version and the candidate directory hash. `--replace` sets the argument
  to `replace`, and the installer then follows its existing rename.

`--replace` acknowledges the identity. A wider permission set is a second
acknowledgement. When an older manifest exists, import uses the inspect
hook `marketplace_service` already builds for `permission_delta`. Added
tool families or data roots return that status until the caller passes
the digest the hook compares. `--replace` carries the identity and leaves
the digest to `--approve-permissions`.

`verify_artifact` runs on the staging directory before the rename. A
refused verdict removes the staging tree and returns `refused`. The
marketplace service still scans after its own commit. This page leaves
that order on the service.

## 5. Where quarantine and the lockfile land

A failed candidate is deleted with `plugins/.staging-<name>/`. The
installed directory stays as it was. The tree has no quarantine folder
for this path.

`plugin-lock.json` in the device folder is the lockfile
(`core/plugin_lockfile.LOCK_FILENAME`). `build_lockfile` records a
directory whose manifest fails validation under the key `quarantined`.
That list describes directories already on disk. A failed import writes
nothing there, because the candidate never commits.

After a rename (`extracted`, and the directory moved), import calls
`rebuild_lockfile(config_root() / "plugin-lock.json")`. That is the call
`marketplace_service._write_lock` already makes. The installer writes the
signature pin itself: `record_pin` into `plugin-signatures.json` when the
listing carried a signature, `clear_pin` when the install was unsigned
local trust. An unchanged result writes neither file.

`ephe plugin install` calls `install_from_marketplace` and returns without
rebuilding the lockfile. File import does the rebuild. This page leaves
the existing install command as it is.

Export writes neither the lockfile nor the pin file.

## 6. Commands the next change adds

```bash
ephe plugin export <plugin_id> --out <file.zip> [--key <private.pem> --kid <label>]
ephe plugin import <file.zip> [--expect <archive_sha256>] [--trust-local] [--replace] [--approve-permissions <digest>]
```

Both actions join the `plugin` subparser and `cmd_plugin`. The functions
are `export_plugin` and `import_plugin` on `core/plugin_install.py`, beside
the extractor they have to satisfy. Signing stays on `core/plugin_signing.py`.

No HTTP route is added. `identity_conflict` is a status on the install
result, beside `downgrade_refused`. It stays off the refusal tables until
a route raises it.

The host-method list stays as it is. No skill is added.
`marketplace/index.json` stays on the zips it already lists.

An open overlay and a native plugin window stay as they are. Import does
not publish `plugin.mount`. A person who has the bundle open reloads it
with the control the hot-reload path already provides. A native window
is a separate surface, and this path leaves it in place.

## 7. What lands later

The commands, the zip writer and the conflict argument are the next
change. This page registers no refusal code, bumps no marketplace row,
and moves no locale string.
