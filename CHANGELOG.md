# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

The 0.6.0 wave is named below (`6c50104d`, `6c3f9b2c`, `5ed12dc7`, `f0cba82b`, `adc7d454`, `24891ea9`, `b10967e7`, `40830e86`, `5ba67a73`, `75384975`, `0ef4b969`, `bc927dda`, `aa5c6c9c`, `9649f55e`, `33f010db`, `19b84e65`, `9bf4f3e2`, `f98572f0`, `e030bb6d`, `6a7fb799`, `d534b963`, `b68ae21e`, `6f1ae8ff`, `bbd8e549`, `a2ab651b`, `456be950`, `ec493c65`, `b5d42de1`, `8395cd95`, `71236902`, `fcb88daa`, `c2658b22`, `971896e9`, `6dbd1d12`, `ae2f1a6d`, `360e6b8c`, `84171304`, `430c8a7b`, `53373610`, `b4775433`, `2c162621`, `2b215004`, `b9e247ff`, `54f66d24`, `497c4f8e`, `4064bff4`, `067ae706`, `7af07bd6`, `bd284ae1`, `a3646844`, `472570f8`, `e2e22d58`, `e7d9d968`, `67a538c5`, `f028d493`, `eae937d9`, `d77efda6`, `aba7c645`, `87467f21`, `f7298530`, `24ab5d99`, `64bb90c0`, `0afe6397`, `45ffc36d`, `67850254`, `76f26571`, `d26c1eff`, `b7600c11`, `e951801e`, `d16ef4b0`, `a75deb13`, `dd782d5f`, `95ead535`, `91a003a6`, `dde17371`, `fc147137`, `493f9966`, `ed64a3ed`, `5a156e8a`, `aa64edcb`, `ac7cb427`, `49a2e7d7`, `6be3edeb`, `bf872fe1`, `e7d2cc2a`, `fa88f333`, `c6c07c08`, `af06fefc`, `dde4ef8a`, `03a1eebe`, `7125e3cb`, `51a797b2`, `c831dfdf`, `8a8ebcff`, `cc8661f0`, `05fb0a8b`, `601790f9`, `e096bcf3`, `fc49ce6b`, `3ebe432b`, `b7c9e658`, `6817a76a`, `fc5a3183`, `31ffba5e`, `c4330ba3`, `3e22561b`, `de9ed9c4`, `e5aa8f91`, `2cef6bef`, `32317339`, `f06042a5`, `113bd5b4`, `50a5d5b0`, `8abe285b`, `c91de054`, `4e569812`, `982d22b2`, `61fa7b79`, `2ae31ffe`, `7d851e33`, `df202b03`, `2f18fe6f`, `2616e4fb`, `36faf16a`, `74e87e09`, `87863bb8`, `789faaa6`, `84280eb5`, `deb4c0d8`, `5f3e8e29`, `08e192d5`, `36a2cc3a`, `2d0919c1`, `a720fb15`, `84c845f8`, `df466ee9`, `793f9708`, `e1ec1e68`, `da5a7f2b`, `928b21d5`, `7463a532`, `3e9a38dc`, `b4114acd`, `407b0e7f`, `2867fcfe`, `caa057ee`, `783f768e`, `c41e5bb0`, `43d20ae2`, `ccfadf26`, `94c2b60e`, `b4daa41c`, `80e3852f`, `9e55aaf4`, `83e05c4f`, `c21f8428`, `be290ebe`, `f62cdcfa`, `86279bb5`, `9a0e5e41`, `cb52a2d8`, `2f017582`, `7d59aeba`, `358734d2`, `1cfbcc67`, `2d6fc7ff`, `c8db491e`, `ddd9b1d9`, `b72f10e5`, `cecb0dee`, `ea244a20`, `6f6b0c9b`, `ef56e57f`, `78859a31`, `1b59de25`, `626ec7e7`, `5bfa26b9`, `8b2e9b96`, `7fefe776`, `454577a5`, `7e63af4b`, `0ac4bbb9`, `ad48c2fc`, `f574aff9`, `1855ea0b`, `dcfbe87f`, `ad088632`, `32d6ad04`, `ebdcc7ba`): every `feat` and `fix` commit since `v0.5.7`, each with its own row under its heading here.

## [0.6.0] - 2026-11-09

A folder's name and the version inside it are two separate facts (`456be950`). The record the desktop starts from names the checkout an installation reads, and on the machine that ships Ephe that name came out of the first provisioning while the tree inside it had moved on — so "it says current" and "nothing is new" were both true at once. `ephe doctor` now prints the path beside the version the manifest at that path reports for itself, and prints the read that failed when nothing came back.

### Fixed

- eval: the mount rows are a measurement, and the run owns its home (`1b59de25`).
  The browser half of the creation eval booted the product server without
  `EPHE_CONFIG_DIR`, so a mount was graded against the operator's real shop
  rather than the run's own. `--browser` now refuses without `--config`, the
  session refuses to boot without a home, and the one staged bundle is
  installed and switched on inside that home by a named `actor="eval"` — the
  same seam the browser test holds. A turn that staged a bundle and never
  installed it is reported as that, and a turn that staged two is reported
  with both names instead of "no staged bundle to mount".

- eval: the printed grading command carries the run's home (`626ec7e7`).
  The command the paid run prints at the end is what the operator pastes, and the
  runner now refuses `--browser` without `--config`. `grading_command()` builds that
  line, the run prints it, and a test pins the home inside it — so a run cannot end in
  a refusal after its turns were paid for.

- eval: a case can no longer ask for a check its grant cannot reach (`5bfa26b9`).
  Every check has a producing call, and the privilege that call asks for is read from
  `core.tools.creator_guard.judge` at load time instead of being restated beside the
  cases. `load_cases` refuses a case whose own grant cannot make the call that produces
  a check it asks for, with the check, the call, the privilege and that source in the
  message. The three mount rows are produced by the harness (task #161), so the 19
  files-only cases stay valid and a test pins them. The mount table in the rubric now
  says the harness installs and enables the staged bundle, and the name count it quotes
  was re-measured from the layer that answers it.

- eval: the graded run does not read the checkout's plugin catalog (`8b2e9b96`).
  `scan_plugins()` always appended `<repo>/plugins` as a second root, so a run isolated
  into its own home still answered with first-party bundles from the working tree - a
  catalog that measures the developer's checkout, and a receipt that can name an absolute
  path from it. `EPHE_BUILTIN_PLUGINS_ROOT` moves that second root, resolved per call the
  way `EPHE_CONFIG_DIR` is, and the bootstrap the eval run builds now points it at an
  empty folder it owns. Unset, the scan path is the one it always was.

- eval: the harness puts the staged bytes back where the install reads them (`7fefe776`).
  `take_staged_bundles` copies a turn's bundle out of the run home into the case's own
  folder, and `install_plugin_bundle(name)` reads `<config>/creator/plugins/<name>`. The
  harness now carries the tree back into the home before it installs, so the mount rows
  can reach a bundle the run actually staged. Found by grading a one-case smoke run.

- eval: a session test no longer leaks the home it sets.
  `SurfaceSession.start()` writes `EPHE_CONFIG_DIR` directly, so the test that pinned that
  behaviour left the variable pointing at its own temporary folder for every module after
  it in the same run. It now stops the boot at the server constructor and restores the
  variable by hand, which is what the next test module reads.

- tools: the discovery answers are English like the rest of the turn (`454577a5`).
  `tool_search` and `tool_describe` rendered their cards in German, so an English answer carried
  German sentences out of the tool layer. The cards are English now, with the contracts (field
  names, JSON shape, ordering) untouched, and a test holds a short list of the words that must not
  reappear.

- tools: a question the turn can ask stays a question (`7e63af4b`).
  A session whose tool array was narrowed away from `ask_user` could only state its question as
  answer text, so a JSON blob arrived at the person instead of a card. The ask gate now travels
  with every whitelist (it writes nothing), and the guidance tells a turn that holds it to ask
  with it. The empty whitelist of an ask-mode turn still names no tool at all.

- security: the redactor closes the word-boundary gap (F-2) and reads the token body (`0ac4bbb9`).
  A secret-shaped token that sat against a letter or a line end could survive the pass, so a
  receipt line could carry it out. The pattern now matches on the boundary the token really has,
  keeps its idempotence, and a test pins the survivor that used to escape.

- tools: plugin_manager answers a question without being told the verb (`ad48c2fc`).
  `action` was required, so the most natural question - what is installed - was a refusal; the
  paid creation run spent five calls on it. The default is `list` now, and the description says so.

- tooling: the language ratchet offers to lower its baseline when that is actionable (`f574aff9`).
  The offer is back in the default output, in the two lines the sister gates print, and a
  matching tree stays silent. A baseline entry is not a file below the baseline, so the
  earlier count no longer reads the entries as files.

- frontend: the chat store's prose matches its baseline entry.
  The one unclaimed tell in app/src/store/chat/session.ts is repaired, so the file's baseline
  entry stays where it was instead of being raised.

- platform: the capability family check says why it reads the way it does, and the retired
  allowlist reasons are gone.

- eval: the case set says how many bundles a turn leaves, and the unservable rows are gone (`1855ea0b`).
  `expect.bundles` is part of the case now (one by default, zero for a refused turn), so a line
  that asks for two folders is refused at load time instead of failing an end state nobody can
  attribute - the two-bundle turns of the paid run are the case for it. The three capability rows
  whose bundle could not carry the family are repaired or dropped, the five cases that referenced
  data they never supplied now supply it, and the rubric says all of it.

- docs: two decisions the paid run and the path audit opened are written down with their pins.
  `docs/decisions/PLUGIN_SURFACE_PAGE_STORAGE.md` records why a mounted surface cannot write page
  storage (the sandbox leaves the origin opaque) and the two ways out, with
  `tests/test_plugin_surface_storage_refusal.py` pinning what happens today.
  `docs/decisions/workspace-authority.md` records the one authority a workspace root needs and
  the fallback that is currently unreachable, pinned by `tests/test_path_authority_pin.py`.
  Neither changes product behaviour: both are the owner's call.

- eval: the rubric stops claiming what the set does not do (`ad088632`).
  The data line names the three paths no turn creates, `expect.bundles` is the loader contract
  with the folder count named as the checker's own, and the repaired capability prompts ask for a
  family instead of spelling a tool name.

- tooling: the lowering hint is one message for the whole gate family (`32d6ad04`).
  It prints in the default PASS once a file sits below its baseline entry, in the shape the
  sibling gates use, and stays quiet under `--staged`.

- security: the corrected `sk-` rule, body instead of delimiter (`dcfbe87f`, `ebdcc7ba`).
  Sixteen characters with at least one digit: an ordinary compound stays a word and a key glued
  behind a letter stays masked, with the fixture assembled at runtime.

- ci: the two invented fixture values are accepted by value (`6f1ae8ff`).
  `c8db491e` added an access-key and an API-key shape literally to
  `tests/test_audit_read_side_redaction.py`; the file assembles both at runtime today, so the
  tracked tree is clean while the range scan of a pull request still judges that commit. The
  allowlist carries the two values with the reason above them.

- plugins: the catalog is regenerated for the release, and the vision pack's hash with it (`b68ae21e`).
  `generate_plugin_catalog.py --check` reported `vision: sha256 aba76bfc != 279d3e69` on the
  release tree, so the shipped index named a hash the directory no longer produced. Regenerated:
  17 plugins, 0 skipped, and `--check` answers fresh.

- app: the orphaned browser pane is closed at boot, and the panel cannot cover the composer (`e030bb6d`).
  A native browser child WebView paints above the page and survives a reload of it, so a new page
  life could inherit the pane a previous life opened. `closeOrphanedBrowserPane()` runs before the
  React mount, the stored active tab is restored into the inventory without becoming the visible
  one, and the pane carries a hard `lg:max-w-[60vw]` bound over its stored width. Nineteen tests
  hold the three behaviours.

- docs: NOTICE names the bundled frontend and the Rust crates (`b68ae21e`).
  The file said the frontend is "CDN, not bundled" while `app/package.json` bundles 39 runtime
  dependencies; all 39 and the 18 `app/src-tauri` crates now carry name, version, SPDX licence and
  source, every one read from installed metadata. The two copies the hygiene test compares stay
  byte-identical.

- release: the packaging carriers move to 0.6.0 with the source (`d534b963`).
  `packaging/homebrew/ephe.rb`, `packaging/npm/package.json`, `packaging/scoop/ephe.json` and the
  reinstall line in `uninstall.sh` still named 0.5.7, so the source archive URL and the extract
  directory pointed at the previous tag and two ratchets went red.

- prompt: the compaction ledger survives the window trim (`6a7fb799`).
  `_assemble_system_prompt_into` folded only `messages[0]` into the prompt, and the working-memory
  ledger the compactor appends sits at index 1, so the window trim dropped it as the oldest
  unprotected message and the next turn ran without the ledger. Every system block folds in before
  the trim now; the compactor is untouched.
- tools: the skill-tool contract names the ask gate (`6a7fb799`).
  Since `7e63af4b` the ask gate travels with every non-empty whitelist; the test that asserted
  "only the skill's tools" predated that decision and named the old set. It expects `ask_user` now,
  with the reason in the test.

- catalog: a regeneration carries the curated switch forward (`33f010db`).
  The generator wrote `enabled: True` for every plugin, so a curated decision to ship a bundle
  switched off survived one regeneration. `enabled` is read from the committed catalog now, as
  `tags` already was, and the build takes its two inputs as arguments so the rule has a test.

- context: a system block in the middle of the history survives compaction (`9649f55e`).
  Every role in the middle became a 280-character bullet, so a skill prompt sitting between two
  turns came back at 290 of its 1220 characters. The middle's system blocks are carried byte for
  byte now, the compactor replaces only a ledger it wrote itself, and a result larger than its
  input leaves the history alone. The filed 12-to-67 growth does not reproduce: measured, one
  compaction of 67 messages yields 12.

- paths: one authority decides the workspace root, and it steps aside from the checkout
  (`aa5c6c9c`). Two paths disagreed: `DENY_ROOTS` denied the device folder while
  `get_workspace_dir()` handed out a folder inside it, so an unconfigured install had file tools
  that reached nothing - the paid run's `read_file` failure. The neutral default is a folder under
  the home now, the legacy folder migrates once, and a name that resolves to the product's own
  checkout moves to a sibling so a first write never lands in the source tree.

- config: every reader of the device folder asks the config root (`75384975`).
  With `EPHE_CONFIG_DIR` set, the sandbox launcher, the CLI's desktop config, two eval scripts and
  three maintenance scripts still resolved `$HOME/.ephe`, so a proof run read the real device folder.
  Each site asks the authority now, and a test pins it against a temporary home.
- surfaces: a bundle keeps its page state inside the sandbox (`0ef4b969`).
  Page storage threw `SecurityError` because the surface's origin is opaque; `allow-same-origin`
  would hand a bundle the app's storage and tokens, so the mount carries a storage bridge instead:
  a snapshot before the first script, `sdk/ephe-storage.js` for `localStorage`/`sessionStorage`, reads
  from the snapshot, writes over the existing SDK channel into a per-plugin state root. The limits
  are written down in `docs/PLUGIN_SDK.md` §3c and the decision record.
- docs: the startup cost is measured, and the plan-accept words match the modes (`bc927dda`).
  `scripts/bench_startup.py`, `scripts/bench_panel_state.py` and the Rust window-state harness fill
  `docs/PERFORMANCE_BASELINE.md` with numbers that carry their machine, date and command; the same
  measurement names a defect (valid JSON of the wrong type makes the panel boot throw). The
  plan-accept sentence, its spec and three walkthrough files now name Analyst, Architect, Operator
  and Creator, and `app/src/lib/planAcceptAnchor.test.ts` holds the three together.

- security: the paths a request names are confined where the analyzer can see it (`5ba67a73`).
  CodeQL turned the release pull request red with thirty-nine alerts. The plugin store confines its
  state home through `path_guard.confine`, a bundle named `..` can no longer answer its parent
  folder, the asset walk refuses a `..` segment before it opens a descriptor, four CSP checks parse
  the header instead of matching a substring, and the consent route answers a validated kind instead
  of the exception text. Two alerts stay and carry a written dismissal reason in the security tab.
- tests: a missing tool is a stated skip, and the CI job brings the tool (`5ba67a73`).
  `tests/support/capabilities.py` detects the node toolchain, rustc and the OS boundary so a test
  that needs one skips with its reason; the pytest legs install node, rust and bubblewrap so the
  proof runs there. The workspace-authority test builds its checkout at the candidate name, which is
  why it only failed on Linux.

- tests: a missing OS boundary is a stated skip, and the CI job proves the boundary (`40830e86`).
  Twenty-two confinement tests were red on Ubuntu because bubblewrap is absent there and the worker
  answers `sandbox_unavailable` (the product's fail-closed behaviour). One capability detection now
  names what the machine lacks, the neighbour families use it, the refusal itself stays proven
  without any boundary, and the pytest legs install bubblewrap, rust and node and assert them usable
  with `EPHE_REQUIRE_OS_BOUNDARY=1`.

- sandbox: a program under the home is not missing inside the boundary (`b10967e7`).
  The Linux confinement wrapped `$HOME` in an empty tmpfs with nothing bound back, so every program
  installed under the user's home answered "not found" to `/bin/sh`: the interpreter a run uses and
  rustup's shim. The mount list re-opens the install root of the named program after the hides, only
  paths under a hide, never the home itself. The widening (`~/.cargo` also exposes the files beside
  the shim) is named in the docstring. The outbound-refusal test was green on Linux for the wrong
  reason - the interpreter never started - and runs for real now.

- security: the last three CodeQL alerts are answered where they occur (`f0cba82b`).
  The asset walk refuses an empty, dot-only or separator-carrying segment before it opens a
  descriptor; the plugin tool route answers the router's coded refusal with the exception's kind and
  no text; the fourth origin check compares the parsed origin list exactly.

- cli: the TUI closes its MCP clients on the loop that started them (`5ed12dc7`).
  The stdio clients lived in a module-global and were never closed, so their pipe transports
  outlived the loop that owns them and the garbage collector met a closed loop at interpreter exit
  (`RuntimeError: Event loop is closed`) - the unraisable exception that failed the coverage leg
  while every test passed. Teardown is fail-tolerant: a closing error cannot turn a finished run into
  a failed one.

- server: `tool_failed` is a coded refusal, and the coverage floors are met (`6c3f9b2c`).
  The plugin tool route answered `Refused("tool_failed")` while `server.refusals.REASONS` carried no
  such code, so the page received a 500 instead of the envelope; the code is registered as a 500 with
  a sentence in both locale bundles. Five test files cover this round's new lines by behaviour:
  `ephe_cli.py` measures 100.00% (floor 100) and `server` 96.10% (floor 94). The lines that no honest
  test reaches - a POSIX `IsADirectoryError`, a FIFO that blocks the open, a dead break - are named in
  the suite rather than hidden behind a pragma.

### Added

- creator: the staged bundle gains a read (`78859a31`).
  Creator mode shipped a write with no read, and the staging folder sits under the
  device root, which the path guard denies to every agent tool. A live turn
  scaffolded a bundle, was refused its own manifest twice over, and spent the rest
  of its round budget on file tools it had been told to leave alone.
  `read_plugin_source` answers one file inside one staged bundle, with the byte
  count and whether the text was cut at the context cap. The path is checked
  against the bundle's resolved root before a byte is read, and each refusal names
  the rule the path broke. The dispatch map is 37 names now.

- browser: a watch frame names the audit row it belongs to (`df466ee9`).
  A running browser step opens a view the reader can follow, with pause,
  stop, and a takeover. A frame with no row reads as unproven. A hand-back
  is the next tool result, so the agent reads the page before it acts again.
  The picture stays on this machine.

- plugins: the shell restores a surface from its host record (`84c845f8`).
  The shell keeps slot, size, placement, and whether the window is open
  beside the mount record. A restart mints a fresh credential and puts
  that box back. A page field is refused. A damaged section leaves the
  committed switches as they were.

- server: a loopback mutation needs an app origin or the LAN token (`a720fb15`).
  A local process that sends no Origin can still read. A mutation, a
  WebSocket handshake, and a GET that spends authority need an origin
  this server serves or the LAN token. The worker network rule stays
  pinned on both boundaries.

- surface: a mount answers the opaque origin a sandboxed document presents
  (`be290ebe`).
  A sandboxed surface document's origin is `null`, and an ES module is
  fetched in CORS mode, so the mount's own script and stylesheet arrive
  with `Access-Control-Allow-Origin: null` named in the response. A classic
  script asks for nothing and a module asks for exactly this. Naming an
  origin is not the same as lending a credential: the server sets no cookie
  and gives the mount no token, so the bytes arrive with a name on them
  and nothing else. The grant is scoped to the mount's own asset responses
  and reaches no other caller.

- surface: a mount nonce is required on loopback (`2d0919c1`).
  The surface family answers only a path that carries a live nonce.
  A GET that writes state or opens another service is refused when
  the origin is present and disallowed. Read-only GETs still answer.
  The app's own fetches of other `/api` routes stay token-free.

- plugins: an extension icon is fetched with the LAN header (`36a2cc3a`).
  An img element cannot send the auth header. Off loopback the icon
  route answers 401, and a query token is refused on that path. The
  tile fetches the bytes and paints a blob. A missed fetch stays the
  lettermark.

- skills: workbook and deck prompts stay inside the writers (`08e192d5`).
  `create_xlsx` writes one sheet. The pptx writer emits no notes page.
  The document factory and the research notebook had asked for three
  sheets and for notes inside the file. Those sentences now follow
  the writers.

- skills: the image skill names the png file the tool writes (`5f3e8e29`).
  `generate_image` forces a `.png` suffix and prints `PNG_FILE`. The
  bundled skill had taught a JPEG name and an `IMAGE_FILE` marker. The
  skill, its rubric, and the image docs now follow the tool.

- desktop: a Dock click asks whether the workbench is visible (`deb4c0d8`).
  On macOS 26.6 a miniaturized window reports `isVisible` false once the
  animation settles, and `isMiniaturized` true does not sit beside it.
  The handler stops reading the flag that cannot change the answer.
  AppKit deminiaturizes after the callback returns. A hidden workbench
  still comes back from this call.

- surface: a standing mount keeps its nonce (`84280eb5`).
  The credential still dies after 300 s, which is what keeps a leaked
  URL from becoming a permanent key. While the surface is open the
  parent asks the mint route to measure that window again from now,
  and the frame keeps the same address. A fetch of the document leaves
  the clock where the mint set it. A dead nonce stays dead. The overlay
  and the desktop window share that renewal. A URL copied into history
  stops working at the end of the window.

- cli: the run sink accepts the tool-call id (`74e87e09`).
  The shared parser passes the id on tool start and tool done. The
  terminal sink stopped at the name and the arguments, so the first
  tool call raised and the run ended.

- shell: file arguments stay inside the file-tool roots (`87863bb8`).
  A whitelisted head such as cat never checked its path arguments, so
  a credential-shaped name was readable. The name is refused with the
  sandbox on and with it off. bash is an interpreter head with the
  same eval lock as python. A pipe into bash stays blocked. An
  unknown head names the closest allowed command. Device nodes the
  sandbox already names (`/dev/null`, `/dev/tty`, the standard
  streams) stay usable (`789faaa6`). A script the interpreter is
  allowed to run can still open a credential-shaped file from inside
  the script.

- shell: device state follows `EPHE_CONFIG_DIR` (`36faf16a`).
  `desktop.json`, the engine key, the desktop logs and the artifact
  root sit in that folder, or in `$HOME/.ephe` when the variable is
  empty. Python's `config_root()` is the same folder. The
  single-instance plugin still binds `/tmp/com_ephe_ephe_si.sock` from
  the bundle id `com.ephe.ephe` and stays one process per identifier.

- shell: the workbench command list is an explicit ACL (`2616e4fb`).
  The manifest names every registered command, with the three surface
  names first. The webview `main` receives that set. A window labelled
  `ephe-plugin-*` receives none of it. The door matches the three names.
  The browser pane `ephe-browser` is outside the set. `default.json`
  still binds its plugin permissions to the main window.

- plugins: export and import of a made bundle are specified (`35edd831`).
  The zip is the archive the installer already extracts. Signing stays
  on `sign_plugin_dir`. A file import checks the installed identity
  before the rename. The lockfile is `plugin-lock.json` in the device
  folder, rebuilt the way the marketplace service already rebuilds it.
  A failed candidate is removed with its staging directory. The
  commands are the next change.

- plugins: an open bundle reloads without a restart (`2f18fe6f`).
  Reload calls the existing mount and cannot acknowledge a moved
  contract. The pin refusal stays on the rail. The frame address stays
  put until `plugin.mount` names that bundle, and then the same window
  loads the document again.

- plugins: extensions split global scope from session scope (`df202b03`).
  `MODE_PLUGINS` in `core/plugin_scope.py` (`2ae31ffe`) is the only
  mode-to-plugin table. The shipped table names no bundle. The view
  (`7d851e33`) adds `scope`, the modes that name a bundle, and the
  module the manifest already carries. A badge shows when the global
  switch is off and a mode names the bundle. Pause-all still outranks
  both. The committed enabled bit is not rewritten. German and English
  copy for the new rows landed with the surface.

- plugins: the page sdk is one file (`61fa7b79`).
  A surface loads `ephe.js` from its own mount. The build's copy wins
  over a file of the same name in the bundle. `ephe.storage.get` and
  `ephe.storage.set` name a key. `ephe.callTool` runs one tool the
  bundle owns and still meets the approval gate. `ephe.subscribe`
  hears this bundle's lifecycle events. The overlay answers the page.
  A native window has no embedding frame in this build. The field
  lists stay in `docs/PLUGINS.md`.

- refusals: `plugin_unknown` and `invalid_request` are registered (`982d22b2`).
  A plugin route that answers either code already sends it as a detail
  code. Both bundles now carry a sentence and a next step. The route
  still returns the detail dict, so the field name stays on the answer.

- plugins: the voice tools ask the host (`c91de054`).
  `synthesize` writes one local WAV through piper. `transcribe`
  reads one file already stored for this session. The spoken text
  and the transcript stay out of the bridge row. The cloud fallback
  stays on the audio route. The family is `voice`. The host method
  count is 52.

- plugins: the Extensions row shows a bundle's stored bytes (`c4330ba3`).
  The row names the megabytes kept and the megabytes allowed. Stored
  files lists the names and removes the one the reader confirms. A
  host path stays off the row and off the route. A name that leaves
  the state folder is refused. Asking for the folder does not create
  it. `plugin_state_full` names that row. The example slots stay 129
  of 128. The default ceiling stays 512. The review ceiling stays
  16384. The same control is on the PWA and the desktop shell.
  `GET /api/plugins/{id}/state` and
  `POST /api/plugins/{id}/state/remove` are on the frozen contract.

- plugins: the default state ceiling is 512 MiB (`31ffba5e`).
  The number a silent bundle gets moves from 128 to 512. A declared
  whole number still wins, including one below the default, up to
  16384. 1024 stays a line a bundle writes for itself. The ceiling
  is the bytes kept in the bundle's state folder. An undeclared
  bundle audits `state_cap_bytes=536870912`. The code-sandbox cell
  keeps its own 128 MB default. The earlier row for the first
  ceiling stays as written. The Extensions row that shows usage
  against this ceiling is still its own task.

- plugins: the picture tool asks the host (`fc5a3183`).
  `generate_image` leaves the kernel map in the same commit the
  manifest becomes 1.2.0. It is a host method. The kernel function
  stays. A field the caller left out stays off the wire. The prompt
  stays out of the `bridge_call` row. The `tool_start` row still
  receives the arguments. A body above the bridge cap is cut there.
  The kernel map is 32. The marketplace index still names version
  1.0.0 and `artifacts/image-studio-1.0.0.zip`. The host wait is 200
  seconds, so the kernel's 120 second generation and its 60 second
  download finish first. The saved name ends in .png. An empty
  prompt and a missing endpoint stay the kernel sentences. Size is
  forwarded as written. The endpoint may reject a size it does not
  offer. A vector drawing stays on the presentations bundle. This
  call does not render a motion clip.

- plugins: the deck tools ask the host (`6817a76a`).
  `create_pptx_deck`, `create_pitch_deck`, `inspect_pptx_template`,
  `edit_pptx_template`, `qa_pptx_deck`, `create_diagram` and
  `create_svg` leave the kernel map in the same commit the manifest
  becomes 1.2.0. Each one is a host method. The kernel functions
  stay. A field the caller left out stays off the wire. The slide
  text, the notes and the path stay out of the `bridge_call` row.
  The `tool_start` row still receives the arguments. A body above
  the bridge cap is cut there. The kernel map is 33. The marketplace
  index still names version 1.1.0 and
  `artifacts/presentations-1.1.0.zip`. The zip and that index row
  move together at the release. The writer fixes a 13.333 by 7.5
  inch canvas. A requested count is a list of slide objects. Speaker
  notes are stored in the deck spec. The pptx file has no notes
  page. A diagram and a drawing are separate SVG files.
  `verify_artifact` runs on the path the tool printed. The report
  beside the deck warns below 8 slides. The qa tool looks for the
  words Proof Object, which this writer does not put on the slide.
  A contributed call gets the same one-shot argument repair the
  kernel map already applies.

- plugins: the sheet and chart tools ask the host (`b7c9e658`).
  `create_xlsx` and `generate_chart` leave the kernel map in the same
  commit the manifest becomes 1.2.0. Each one is a host method. The
  kernel functions stay. A field the caller left out stays off the
  wire. The rows, the labels and the path stay out of the
  `bridge_call` row. The `tool_start` row still receives the
  arguments. A body above the bridge cap is cut there. The kernel map
  is 40. The marketplace index still names version 1.1.0 and
  `artifacts/spreadsheets-1.1.0.zip`. The zip and that index row move
  together at the release. The workbook has one sheet. The first row
  is the header. A total is a formula. A percent written as 12% is
  stored as the fraction 0.12. The chart is a separate SVG.
  `verify_artifact` runs on the path the tool printed. The tool does
  not recalculate, and it does not write a second sheet.

- plugins: the document tools ask the host (`3ebe432b`).
  The nine document names leave the kernel map in the same commit
  the manifest becomes 1.2.0. Each one is a host method. The kernel
  functions stay. A field the caller left out stays off the wire.
  The body, the path and the source text stay out of the `bridge_call`
  row. The `tool_start` row still receives the arguments. A body above
  the bridge cap is cut there. The kernel map is 42. The marketplace
  index still names version 1.1.0 and `artifacts/documents-1.1.0.zip`.
  The zip and that index row move together at the release. The skill
  passes the title and the full body. A report with several sections
  sets document mode. The page is A4 and the margin floor is 18 mm.
  A citation marker is written only from a supplied source.
  `create_docx` writes a new file. `verify_artifact` runs on the path
  the tool printed. A URL that was not read is a gap.

- plugins: the shell and file tools ask the host (`fc49ce6b`).
  The twelve code-shell names leave the kernel map in the same commit
  the manifest becomes 1.2.0. Each one is a host method. The kernel
  functions stay, so the command check and the path check stay inside
  them. A missing file, a refused path and a shell timeout come back
  as the sentence those functions already write. A field the caller
  left out stays off the wire. The command, the path and the file body
  stay out of the `bridge_call` row. The `tool_start` row still
  receives the arguments. A file body above the bridge cap is cut
  there. `delete_file`, the workspace dev server, `task_output`,
  `task_stop` and `run_shell_pty` stay on the kernel map. `bash`,
  `read` and `edit` still call the same kernel functions. The kernel
  map is 51. The marketplace index still names version 1.1.0 and
  `artifacts/code-shell-1.1.0.zip`. The zip and that index row move
  together at the release. The shell profile writes the workspace, the
  temp directory and the device nodes. The rest of the home stays
  closed. Network is denied, including the loopback. The switch stays
  off. A requested sandbox with no boundary on the host does not run,
  and the audit records `sandbox-unavailable`. Docker still runs. The
  settings hint still describes the old reach. That sentence belongs
  to the locale lane. A permitted plugin run records an empty
  decision. Status already says the call ran. A result that names a
  blockade still records blocked.

- plugins: the image tool asks the host (`e096bcf3`).
  `analyze_image` leaves the kernel map in the same commit the vision
  manifest becomes 1.2.0. It is one host method. The kernel function stays,
  so the path check stays inside it. A missing file and a path outside the
  allowed roots come back as the sentence that function already raises.
  `question` and `region` stay off the wire when the caller left them out.
  The path and the question stay out of the `bridge_call` row. The
  `tool_start` row still receives the arguments. The kernel client has no
  clock of its own. The host wait is the register's non-streaming bound.
  The worker clock runs twenty seconds longer. The kernel map is 63. The
  marketplace index still names version 1.0.0 and
  `artifacts/vision-1.0.0.zip`. The zip and that index row move together
  at the release.

- plugins: the desktop tools ask the host (`601790f9`).
  `vision_click` and `vision_type` leave the kernel map in the same commit
  the manifest becomes version 2. Each one is a host method. The kernel
  functions stay, so the confirmation stays inside them. A missing callback
  is that same raise, carried back to the turn. The coroutine runs on the
  loop the caller published, so the dialog can still be answered.
  `analyze_image` stays a kernel tool until its own method. A version-2
  manifest cannot mix a string name with tool objects, so this commit drops
  it from the vision declaration. The target description and the typed text
  stay out of the `bridge_call` row. The `tool_start` row still receives the
  arguments. A no from the person is the abort sentence the kernel already
  writes. The kernel map is 64. The marketplace index still names version
  1.0.0 and `artifacts/vision-1.0.0.zip`. The zip and that index row move
  together at the release.

- plugins: the browser tools ask the host (`05fb0a8b`).
  Eight names leave the kernel map in the same commit the manifest becomes
  version 2. `browser_go`, `browser_screenshot`, `browser_click`,
  `browser_type`, `browser_press`, `browser_scroll`, `browser_evaluate` and
  `browser_exec` are one host method each. The kernel functions stay, so the
  address check and the release gate stay with them. A blank field still
  reaches the sentence those functions already write. A navigation row keeps
  the host and drops the path and the query. Typed text, a script and a code
  block stay out of the `bridge_call` row. The kernel map is 66. The
  marketplace index still names version 1.1.0 and
  `artifacts/browser-use-1.1.0.zip`. The zip and that index row move together
  at the release.

- plugins: memory asks the host for each action (`cc8661f0`).
  The name leaves the kernel map in the same commit the manifest becomes
  version 2. `memory_add`, `memory_replace`, `memory_remove` and `memory_list`
  are one host method each. An action outside those four reaches the kernel
  function through `memory_action`, which refuses a known action. A stored
  sentence comes back with its code and with the flag that says the action
  happened. A blank field still reaches the kernel sentence. The entry body
  stays out of the `bridge_call` row. The live store writes a kind into the
  type column and a correction into `superseded_by` and `valid_to`. The
  retired importer is a command string in the provider module. This function
  does not open that store. The kernel map is 74. The marketplace index still
  names version 1.1.0 and `artifacts/memory-1.1.0.zip`. The zip and that index
  row move together at the release.

- plugins: web-research serves both tools from the confined worker (`7125e3cb`).
  `web_search` and `fetch_url` leave the kernel map in the same commit the
  manifest becomes version 2, so one name has one provider. The worker still
  has no socket. It asks the host: `search` calls the kernel search, and
  `fetch_url` calls the kernel fetch. The sentences those functions already
  write come back, including a blank URL. The query and the prompt stay out of
  the audit row. A refusal comes back as the sentence and its code, so the card
  can still translate it. The shipped names publish on the first schema read
  and on the first call, and a set this process already registered for that
  plugin stays. A bundle of tools and no surface passes the definition-of-done
  gate. The names stay addressable for skills, profiles, the router, the code
  kernel and the agent tool list. `web_search` is on the chat auto-run list.
  `fetch_url` is in the read-only set, so the chat path lets it run too. The
  other four flagship bundles stayed on the kernel rail in that commit. The marketplace index
  still names version 1.1.0 and `artifacts/web-research-1.1.0.zip`. The zip and
  that index row move together at the release. This checkout is the copy the
  worker sentences above describe.

- plugins: a confined worker can ask the host to search (`03a1eebe`).
  The bridge had one method, `fetch`. A research bundle still has no socket, and
  `web_search` is the function that already owns the deadline, the backend order
  and the reach line. `search(query, max_results=None)` calls that function and
  hands its text back. The kernel entries stay in this commit. The query stays
  out of the audit row: a search row names the method and records no target. A
  bundle that did not declare `network` is refused before the function runs. A
  blank query is `bridge_args_invalid`. When every backend refuses, the status
  line crosses as `bridge_internal`.

- plugins: a bundle's stored state has a ceiling, and spending it is said in numbers (`dde4ef8a`).
  128 MiB per bundle by default, or the whole number of megabytes its own manifest asks for
  (`permissions.state_cap_mb`, up to 16384; `true` and the other shapes Python counts as
  integers are refused so a bundle never lands on a 1-byte ceiling). The gate stands between
  runs: neither rail offers a per-directory quota, and a child that found mid-write that it
  could not write would report that as a failure of the tool rather than as a folder that is
  full. So the run that crosses is allowed and measured — every tool row now carries
  `state_bytes=`, `state_files=` and `state_cap_bytes=`, no path in them — and the call after it
  is refused before a worker starts, with the code `plugin_state_full` and both numbers in the
  sentence. The wording was checked against the product: no surface opens a bundle's folder
  yet, so the reader is sent to their own file system instead of to a control that does not
  exist, and the surface is its own task.

- plugins: a declared data root now opens on the confined worker's rail (`af06fefc`).
  `permissions.data_roots` was one line in a manifest read by two rails that disagreed: the
  kernel file tools a bundle calls honoured it, while a v2 tool of the same bundle, running
  behind the OS boundary, saw nothing of it — the runner never carried the declaration into
  the spec, so the profile gained no rule. One function answers the question for both now, so
  the same words mean the same set of paths whoever reads them. The grant stays read-only: the
  worker writes in its own state directory, nowhere else. Measured with a real `sandbox-exec`
  run, in both directions, with `$HOME` moved into the lane so the whole-home deny actually
  covers the folders under test — the declared folder opened, its sibling beside it stayed
  shut, and taking the roots out of the spec call makes the first half fail.
- plugins: every plugin tool run states the bytes it left behind (`af06fefc`). The completion
  row carries `state_bytes=`, `state_files=` and `state_roots=` beside the identity fields,
  measured by walking the state directory after the child exits. No path crosses into the
  trail. A ceiling on those bytes is still a decision to be made, and it can now be made
  against numbers that are already being written.

- plugins: a confined tool can ask the host for what its boundary forbids (`c6c07c08`).
  A plugin worker has no network — the macOS profile carries `(deny network*)` and bubblewrap
  runs `--unshare-net` — and the reason that was a fix is that the request it stopped carried
  nothing: no plugin id, no family consulted, no row tying the call to the mount. The
  capability returns over the stdio the tool already speaks on, as one request line out and
  one answer line back, and the host grants it against the manifest. `fetch(url)` is the first
  method: the host's own `guarded_fetch` answers, hop by hop, and a refusal from the guard
  crosses as `bridge_method_denied` beside the four other gates — a method nobody registered,
  a family the bundle never declared, a blank required argument, and the 32 calls one run may
  make. The grant is read off the mount into `ToolDescriptor.families`, so a bundle naming a
  family inside its own arguments changes nothing. Every call writes one `bridge_call` audit
  row naming the plugin, the tool, the method, the code, the gate that answered and the host
  asked; the path and the query stay out, because a URL can carry a token the way any URL can.
  A tool that never asks produces the byte stream it always produced: the drain separates
  bridge traffic before the classifier's buffer sees a byte, so the framing check, the output
  cap and the timeout sentence of the worker supervisor keep their exact meaning. Measured with
  a real confined child on this machine's boundary: a three-argument handler reached the host,
  the answer came back upper-cased through its own pipes, and the same call from a bundle that
  declared `read` was refused with `cause=undeclared-family` and never reached the handler.
  `docs/PLUGIN_SDK.md` §3a carries the signature, the six codes and both ceilings, and a test
  opens that document and compares them against the modules.

- workspaces: The board reads the run ledger as its fourth register (`581a4a48`). A chat turn
  writes one ledger file per run and nothing else, so the board now asks the ledger which
  turns exist: each row names the session it ran in, the state the lines say it reached, the
  file it last touched and its own five-phase view, ordered so the turn that keeps writing
  stands first. A session already on the board from an open approval keeps exactly one row —
  two rows for one turn would put `running` beside the `waiting_on_human` line a person has
  to act on. The row shape and the four state words live in `core.fleet_rows`, beside each
  other, because a board built in two places is free to disagree about what `blocked` means.
- cli: The doctor says which checkout this install reads (`456be950`). The desktop record
  names a folder, a folder's name was chosen once by whoever provisioned the machine, and the
  number a release carries lives in the manifest inside it. The new row reads the record, then
  reads the version out of the tree at that path, and prints the two beside each other. Five
  shapes of a failed read each get their own sentence — no record, a record that is not JSON,
  one naming no checkout, a folder that is gone, a folder reporting nothing — so a machine the
  instrument could not read is never shown as a machine that is up to date. Measured live:
  `Installed checkout - …/0.1.4 — reports 0.5.6`.
- settings: The device folder shows what it keeps, on the screen (`8395cd95`, `71236902`).
  Under Settings - Privacy & Security a person now reads the entries Ephe leaves on the
  machine: each declared folder and file with the words for what it holds, the bytes it
  takes, the total between them, the rows the declaration protects, and the count of
  leftovers no row names. The clear beside it says what it will forget and what will stay
  before it acts, and it runs only on the second click: the audit log, the cell guest and
  the signing anchors stay, the undeclared leftovers stay untouched, and the answer names
  the counts of the run that was just done. Two routes carry it — `GET /api/device` reads
  the declaration, `POST /api/device/forget` runs the clear dry-run-first and refuses by
  name anything the declaration keeps or never names — and a card that cannot read the
  folder says so and offers the retry, because an unreadable folder is not an empty one.

- browser: a browser session Ephe is running can be watched (`ed64a3ed`, `5a156e8a`).
  `GET /api/browser/watch/{session}` streams the page's own frames over the server-sent shape
  the app already consumes, and a name from the URL never opens a browser of its own: an
  unknown session answers `browser_session_unknown` with no engine call behind it. The reader
  gets a state, because a picture alone cannot answer the one question a run raises. Frames
  arrive when the page changes, so a still page yields about one every two seconds where an
  animating one ran 93 fps in measurement, and `casting`, `unchanged` once the age passes the
  threshold, and a refusal are three different sentences on the surface. The cast is asked for
  when the first reader arrives and stopped when the last one leaves, and that stop is
  scheduled rather than awaited because the server cancels the task the cleanup runs inside.
  Measured on a running server, with a real page behind it: `200 text/event-stream` from the
  loopback route, the first frame 17,790 bytes carrying the JPEG marker with the page's
  viewport `1280x800` beside the cast `800x500`, then keepalives and no further frame while
  the loaded page stayed as it was, and the session reading `is_watched() == False` after the
  reader closed.

- creator: the four calls that build a plugin are kernel tools (`b4daa41c`).
  `create_plugin_scaffold` composes a manifest v2 declarative bundle and reads it back with
  the loader before a single file lands, so a scaffold the loader rejects leaves no staging
  directory and answers with the loader's own first word as its error code.
  `write_plugin_source` resolves inside the bundle and refuses a path that leaves it.
  `verify_plugin_bundle` is the loader, the worker's own entry resolver, and the two name
  guards that keep a declared tool name honest, and it reports the directory digest the
  fingerprint gate takes. `install_plugin_bundle` opens no second install path: it packs the
  bundle and hands the bytes to the installer the marketplace already runs, so the hash
  check, the zip-slip guard, the identity comparison, the downgrade refusal, the one-slot
  backup and the audit row are that installer's. The answer reports the install path's own
  trust class and warning, and its next line points only at surfaces a reader can open.

- creator: the mode's three permissions are enforced where a call runs (`80e3852f`).
  Entering Creator Mode needs one of `code`, `files` and `network`; each of the three is then
  enforced on its own, at the one dispatch seam, after the mode gate and before the user
  hooks. What a name asks for is read from the two authorities that already decide it, the
  kernel dispatch map and the manifest-declared tool family, so no third permission list
  ages beside a registry that moves, and a name neither authority knows is refused. A
  refused call returns the coded refusal, audits its own denial, and leaves the offered tool
  list, so the model is not shown a call this session cannot run. A grant is a set per
  session, kept in one `0600` file in the device folder, replaced whole when the consent
  route writes it, and forgotten by the two paths that delete a session.
  `GET` and `PUT /api/creator/consent` answer and replace exactly what the gate reads, and
  both verbs ask the same question of a session key.

- creator: the tile asks before the session takes the mode (`9e55aaf4`).
  The fourth composer tile opens a sheet in place of switching. It reads what this session
  holds from `/api/creator/consent`, sends the rows the user ticked as one set, and moves
  the stored mode only on a write that answered, so a refused read or a refused write
  leaves the session on the mode it was on and names which of the two failed. One of
  `code`, `files` and `network` is enough to enter, per the owner ruling, and each stays
  enforced per call by the guard: the sheet grants an entry and never widens a call. A
  composer with no session has nothing to grant, so it takes the plain path and the guard
  is the enforcement there.

- creator: the run log names the bundle the answers built (`83e05c4f`).
  The four creator calls answer in JSON, and each says something the rows above
  it do not: which bundle was staged, which files it holds now, whether the
  loader read it, and whether the install took. The card reads only those
  payloads, so a turn that stopped in prose claims no file, version, digest or
  refusal it never reported. Its one action asks the store view which bundle
  this is and hands the surface that bundle declares to the display module,
  which answers with the side this platform has. A refusal is read out in that
  layer's own words, and a bundle with no surface says so openly, where a
  control that cannot answer would otherwise sit.

- plugins: a declared surface says what it may touch (`84171304`).
  `components.ui` was accepted structurally and never meant anything, so a
  bundle could name a surface and the platform had no answer to what it may do.
  The contract is sixteen webview capabilities, one descriptor per plugin, and
  default-deny: an unknown capability name quarantines the whole plugin the way
  an unknown tool family already does. Each name carries the layer that refuses
  it, whether that layer can confine a plugin surface in this tree today, the
  audit kind it writes, and whether a user has to grant it beyond the install
  declaration. The enforced set is derived from that column and is empty, and a
  test pins the emptiness, so no name is advertised as confined before the
  commit carrying its layer can be observed. The tier is provable at the
  manifest: a countdown descriptor declaring notifications, a dock badge and
  fullscreen round-trips with an empty grant list, needing a manifest line and no
  code permission.

- plugins: every enforced capability names the test that watches it (`430c8a7b`).
  The ratchet that holds a capability unenforced until a layer observes it now
  checks that the witness exists. Each record carries `observed_by`, the
  repo-relative path of the test file that can see that confinement, and an
  enforced name with no witness, or with a witness missing from disk, fails.

- plugin-ui: a declared surface is served with its own policy and credential (`53373610`).
  An iframe and a webview can carry no header, so the credential a surface load
  authenticates with is a 32-character nonce minted by an already authenticated
  fetch: bound to one plugin id, alive for 300 seconds, held in this process and
  never written down, while the long-lived LAN token stays out of URLs. The
  middleware accepts it only inside `/api/plugins/ui/` and the route alone
  decides value, binding and expiry before a byte of the plugin directory is
  read. The document arrives with a policy assembled from its own capability
  list: a closed baseline, wasm buying `wasm-unsafe-eval`, workers buying
  `worker-src`, network buying nothing a manifest cannot name, and
  `frame-ancestors` listing our origins with no wildcard. Assets come from a
  media-type table through the existing containment, a directory is never
  listed, and every refusal is coded, so no plugin path reaches a 500 body.

- shell: a plugin surface window gets its own label and its own capability (`2b215004`).
  The desktop mounts one plugin document in a WebviewWindow of its own. Tauri
  binds capabilities to window labels, so `ephe-plugin-<id>` answers to a new
  capability file that grants the core default and nothing else, while
  `default.json` keeps main alone. Each window command reads the label of the
  calling window in Rust and refuses a caller whose label carries the plugin
  prefix, because the handler registers commands for the whole app and one
  mounted widget could otherwise open, close and steer every other surface. The
  size bound and the URL come from the descriptor contract, so the shell
  re-decides neither: a surface asking 480x320 gets it, the workbench floor no
  longer pulls every window up, and window-state keeps a transient label out of
  the store.

- shell: the frontend half of a native plugin surface window (`b9e247ff`).
  `pluginSurface.ts` bridges `plugin_window_open`, `plugin_window_close` and
  `plugin_window_bounds` in the shape the browser pane already uses, and says
  plainly that a browser tab has no native window, because the overlay dock is
  the surface that shows the same plugin there. The descriptor crosses as
  `ui_descriptor()` returns it and the shell answers with the window it actually
  built, so a surface that asked for transparency can report a decorated window
  when the platform refused it. `plugin-window:opened` and `plugin-window:closed`
  reach the main window, which is the only window allowed to drive the surface
  layer. No new platform read enters the tree, so the shell-parity manifest
  still owes no entry.
- tools: a contributed tool is a descriptor, never a callable (`d77efda6`).
  The dynamic registry holds name, plugin id, schema, transport, the textual
  `module:callable` entry, the declared family and a sha256 over the canonical
  schema bytes. One lock covers it: register, a `replace_for_plugin` that runs
  all its checks before its first write, unregister, get, names and an immutable
  `descriptor_snapshot`. A name colliding with the kernel map or a live `mcp_`
  tool is refused at registration with a code, visibility authority stays in the
  plugin runtime, and no plugin module is imported here.
- tools: the schema view and the dispatch answer to that registry (`aba7c645`).
  Registered descriptors reach the model through the existing gate and filter,
  name-sorted last so the prompt prefix stays byte-stable for the turn freeze. A
  call on a dynamic name validates through the kernel path and then refuses with
  the coded reason, instead of running anything the confined runner has yet to
  provide.
- tools: one offer array per turn, built once and frozen (`87467f21`).
  Kernel, MCP and dynamic entries sort by name where the array is built, so
  re-registering the same set moves no byte, and a chat turn freezes that array
  at its first read: retries, the failover half and the revision call of the same
  turn id all carry the original. A tool arriving mid-turn reaches the model on
  the next turn only. One user turn spans two tool calls on both routes, and the
  second read could rebuild across the 60-second window — that drift is what a
  hallucinated tool selection needs. The snapshot is a view over the live
  registry, never a cache that could go stale the other way.
- sandbox: the worker supervisor classifies a confined child with per-OS truth (`f7298530`).
  Descriptors in, fixed-status outcomes out: ok, timeout, crashed, nonzero, oom,
  sandbox unavailable, protocol error. No boundary means no spawn, and the test
  proves the child never ran; the timeout path kills the process group and proves
  it gone, which on macOS means handling the `EPERM` a zombie-only group raises.
  The restart budget ends a crash loop with a coded refusal, and the policy
  snapshot names each ceiling as enforced, bounded or not-enforced for this
  platform — Windows has no rung and denies on failure, and the kernel OOM path
  is recorded as unmeasured here.
- sandbox: a plugin tool runs in a bounded child, never in the backend (`24ab5d99`).
  The runner resolves a descriptor's `module:callable` entry with the existing
  containment rule and calls it only inside an OS-bounded child started by the
  supervisor, so no plugin Python is imported or run in the backend process. One
  JSON request crosses the child's stdin and one JSON line its stdout; the
  launcher loads the entry under `__main__` and the parent asserts the plugin
  module never entered its own `sys.modules`. Confinement is the default: no
  boundary means no spawn, and the statuses map to model-facing results that
  carry no host path.
- refusals: the confined tool rail answers with registered codes (`64bb90c0`).
  A plugin tool that cannot run has to be understood by the reader, not only by
  the developer who wrote it. Three identifiers were emitted as bare strings —
  the sandbox refusal, the exhausted restart budget and the transport's
  not-available marker — so all four are now born once in one module and read by
  the runner, the budget, the wiring and the HTTP reason table as its keys: the
  audit decision, a card's reason code and the envelope are one string. Each
  carries an English fallback, a German and English entry with the same slots, a
  params row and a next step; the HTTP half answers through the product's own
  handler rather than a 500, and a confinement refusal names the missing
  boundary, never a directory.
- tools: a contributed tool meets the family gate and is audited as one (`0afe6397`).
  A descriptor's declared family used to move nothing: the mode gate judged every
  plugin name as a write, a plugin whose manifest never asked for the family was
  answered "not available" rather than "disabled", and the audit rows carried a
  tool name with no owner and no pin. Now the family is judged against the
  permission the plugin's own manifest declared, a read-only mode is admitted to
  a declared read tool only, an installed-but-off plugin becomes the disabled
  verdict, and every rail row carries the plugin id, family, transport and short
  fingerprint. No gate got weaker: a contributed name is still asked about on the
  chat path, and a plugin no manifest speaks of is granted nothing.
- manifest: a v2 bundle declares a tool and the platform derives its name (`45ffc36d`).
  The tool list becomes meaningful for a bundle that ships a tool of its own:
  name, entry, family, description and parameters, validated by the new tool
  contract, while a version 1 list of kernel names is accepted exactly as before,
  so the shipped first-party bundles stay untouched and v2 gains no lenient path.
  The served name is derived and never declared — one builder, and the namespace
  check reads the same normalised form, which closes the hand-built-namespace
  gap. Normalising the dash is what lets `timer` plus `lite_x` and `timer-lite`
  plus `x` spell one name: both claims become contested, both lose the name, and
  the reason names both plugins and both declarations instead of a bare code. No
  plugin module is imported anywhere here; the entry stays the validated text the
  confined worker resolves.
- dod: the gate reads a declared tool against the bundle it sits in (`67850254`).
  The definition-of-done gate counted v2 tool entries, named the path Tier 2 and
  left, so it said nothing a text read could not already say. It now asks the
  four questions that need the bundle: the entry file ships, the callable is
  bound in it — an `ast` read over the shipped bytes, so nothing is imported —
  the family is one the manifest's own permissions declare, and no two
  declarations inside the bundle serve one derived name. A missing piece is a
  line in the problem list, never an exception. One answer now says what a bundle
  contributes, and the registry scan and the gate read that same answer; two
  parsers went with it, where an object entry used to print its dict repr beside
  "outside the skill grant". No shipped bundle declares a v2 tool yet, so the
  live portfolio moves by no row.
- mount: a bundle's tools go live as one atomic transition (`76f26571`).
  Mount and unmount are transitions on the existing lifecycle machine rather than
  a second registry: read the bundle, refuse a contested or reserved name on the
  scan's own answer, diff the contract against the lockfile pin and refuse until
  it is acknowledged, then write the lockfile entry, the activation record and the
  descriptor batch. Any failure after the first write restores all three and
  names the step that broke in the audit. An unmount removes exactly that
  plugin's names and remembers them, so a call arriving for a name that just left
  answers the coded refusal instead of a 500. A mount asked for mid-turn stays
  invisible until the next turn: the per-turn freeze holds, extended rather than
  weakened.
- register: the board reads the run ledger as its fourth register (`971896e9`).
  The workspaces route stopped at the git-worktree register, which no chat turn
  has ever written, so the board beside a turn that had just produced a file
  answered with empty lists while the run sat in the one register a streamed turn
  does write. The read now turns ledger lines into rows naming the session, the
  state, the file last touched and the run's own projection, ordered so the turn
  that kept writing stands first. A session already on the board from a pending
  approval keeps one row, because two rows for one turn would put a running state
  beside the waiting line a person has to act on. The row shape and the four state
  words moved to one module, since a board built in two places is free to disagree
  about what blocked means. Proved at the route, and the order proved by writing
  the sort backwards and watching the test fail.
- shell: the overlay stack decides its geometry and its order in one place (`497c4f8e`).
  The browser half of a plugin surface needs the two decisions the desktop half
  already makes behind a window label: one surface per plugin, and geometry
  clamped to the space the caller measured. Both live as functions of state, so a
  viewport that shrank under a parked window is an arithmetic case with a test
  rather than a layout engine to agree with. The surface bridge gains the
  credential side both platforms mount with: the mint the route issues to an
  authenticated fetch, and the directory-shaped URL that puts the nonce where a
  frame can carry it, because a frame sends no header and only the path segment
  survives to the files the document derives.
- shell: the overlay stack rides the store the shell already has (`4064bff4`).
  The dock that paints a surface and the caller that opens one have to read the
  same object, and the app keeps cross-surface state in one place already, split
  as action factories, so the stack arrives as another factory of that shape and
  the geometry stays where it is tested. Nothing here is written down: a surface
  the user dragged is not a change to the session, no path reaches the persist
  helpers, and one case asserts the transcript is untouched after an open, a move
  and a close.
- shell: the overlay host frames a surface with the sandbox it was served for (`067ae706`).
  The stack the model decides gets painted here: each surface is one box with a
  44 px rail and one iframe, and the iframe carries the isolation directive the
  serving route sends the document with, at the embedder as well, so a plugin
  document gets its opaque origin from two enforcement points. The host adds no
  request of its own — one opened surface costs its document plus whatever that
  document references, measured per engine in the wave report. It mounts beside
  the confirmation host, is exported through the shell barrel and named by two
  locale leaves; no route and no platform read appear, so the parity manifest
  stays as it is.
- shell: one place decides whether a surface is a window or a frame (`7af07bd6`).
  A caller that wants a plugin on screen asks one function and gets the surface
  its platform has: the shell window the native command builds, or the frame the
  overlay dock paints from the store. The bridge question is asked once, so no
  fourth platform detector joins the tree. A fallback is loud in both directions:
  a refused window stays refused, the curated sentence the shell rejects with
  rides to the user as the toast detail and the overlay stack is never written
  behind it, while a tab that cannot mint its mount address, or whose stack write
  lands nowhere, says which part refused. A flag a tab cannot hold is named as
  one, and a transparent widget that came back decorated is read out. Both halves
  run against the real bridge and the real store, and every product mutation went
  red before it was restored.
- plugins: a surface loads its library from the bundle, hash declared (`bd284ae1`).
  A generated document that reaches for a renderer from a public CDN takes a
  network permission nobody asked for, causes a privacy event on every load, and
  is refused by the policy this mount is served under anyway. The working
  alternative is a vendored file with a stated hash: a library list beside the
  manifest declares name, version, path, kind and sha256, and the shipped bytes
  are re-read against it. A mismatch, a declared file that never shipped, an
  undeclared file under the vendor directory, or a byte past a cap quarantines the
  whole plugin, and because the surface route reads the manifest per request the
  refusal lands on the next fetch. The caps are measured: eight MiB per file, the
  route's own asset limit restated and pinned equal by a test, and 24 MiB per
  plugin, re-verified in 7.44 ms at the hashing rate measured here. WebAssembly
  needs its declared capability at both layers: validation refuses the entry and
  the asset rule refuses an asset no policy could run.
- plugins: the definition-of-done gate reads a v2 bundle (`a3646844`).
  The gate was written for a command-and-skill bundle, so it had no answer for a
  declarative surface. It now reads both versions, and a bundle on any other
  version is answered with the version it declares rather than passing unread.
  The v2 path asks the loader to accept the bundle, which is where the shipped
  contract checks the descriptor, the capability vocabulary, the entry document,
  the vendored-library hashes and the data roots; then it requires exactly one
  declared surface, no tool entry points, which is the escalation path this gate
  does not read, and every file the entry document names present in the bundle.
  The assertions with no version in them — the changelog line, the README
  reference and the golden suite — apply unchanged, and the command and example
  rules still apply to a v2 bundle that declares commands or skill packs.
- plugins: the countdown surface, one declarative v2 bundle (`472570f8`).
  The first shipped bundle that is a surface rather than a list of commands: a v2
  manifest declaring one floating-window entry document with its size, its
  transparency and its always-on-top flag, three capabilities named in the
  vocabulary and nothing else, one declared data root, no tool entries, and an
  engine floor at the version it shipped under. Its assets, icon, rubric and
  golden cases come with it, and the portfolio, registry, migration, marketplace
  and golden assertions moved to read the bundle as it is.
- plugins: the switch row opens the surface the bundle declares (`e2e22d58`).
  The store view hands each row the flattened descriptor of its v2 bundle, and a
  row without a surface key has nothing to open. The plugin store row is now the
  production caller of the surface show path: one button mounts the surface
  through the display module and takes it down over the same path, so close and
  reopen travel one ledger on both halves. Hiding answers false when nothing stood
  and reports a failed close when a window does not confirm it, with the copy in
  both catalogs. The countdown's tool leg is reported as blocked in the wave
  report rather than worked around: the connector rail registers servers from user
  config only, gates every bridge name to its own bundle, fails closed on a
  plugin-owned tool name, and gives a confined child neither the config root nor
  its coordinate.
- route: a bundle's tools mount and unmount over the API the app already trusts (`e951801e`).
  The transition existed and nothing could reach it from a request. The hot-mount
  route and its matching delete now drive it through the guards every other plugin
  mutation has — the same-origin marker, the read-only brake, the signature gate a
  switch passes — and answer in the envelope the client already reads, so a
  refusal is a code and a payload rather than a 500 or a 200 carrying a false
  saved field. Precondition matching on this resource is the bundle version,
  compared inside the lifecycle lock against the manifest just read: no entry of
  this machine is part of what would be published, so a token over committed
  switch state could not name a bundle the machine has never seen. The pin alarm
  travels as data — a conflict from the changed-contract check carries one entry
  per served name with both fingerprints and which field moved, because a reader
  who has to accept a change is shown the change. No second event stream is added:
  the notification a surface waits for is the mount's own publish, which the
  existing subscriber is proved to receive.
- mount: a bundle states the trust class it publishes under and its content digest (`d16ef4b0`).
  A generated bundle has no signature record, so the enable-time gate has nothing
  to verify and passes it — right for code the user authored, and silent about the
  fact. The mount now says the class out loud, signed when a record came with the
  directory and local when the author is the user, in the route's answer, the
  state record and the audit line, so a surface that offers a mount can name what
  it offers. The digest answers the other half: the pin holds the schema and the
  description, so it sees a rewritten contract and cannot see an edited handler
  under an unchanged one. The mount records the hash of the directory it read and
  treats the two classes by their different risk — bytes that moved under a record
  accepted as signed refuse the mount until acknowledged, with both hashes in the
  payload, while a local bundle reports the move and mounts, because its author
  saved those bytes on purpose and a gate that refused every save would only train
  the user to click through it. That asymmetry is the decision of the change, and
  its open consequence is stated in the plugin docs: for a local bundle the
  remaining guard on what runs is the contract pin plus confinement.
- browser: a step answers with what the page said (`91a003a6`).
  Every browser action used to end with the agent's own account of it,
  which is the same class of claim as a model reporting a test it never
  ran. Each action now reads the page once before it acts and once after
  (address, title, node count, text length, scroll offset, focus,
  checked count) and ends with `STEP_EVIDENCE:{...}` carrying the counts
  that moved; a step whose effect cannot be observed answers `unproven`
  with the reason, because an unobservable action is not a successful
  one. The contract had been attached to `go` only, so the actions a run
  is actually made of — `click`, `click_at_xy`, `type_text`, `press` —
  still reported themselves, and the pre-read is what makes the first
  action of a session verifiable at all. Two defects caught while
  verifying: a baseline `_baseline_or_none` fetched and then discarded
  would have made every first action answer that no state was read
  before it, and the evidence line reached 370 bytes against the audit's
  own detail cap, so it arrived in the trail cut mid-JSON — the cap is
  now the shared `DETAIL_MAX_CHARS` in `core/audit_log.py` and `_fit`
  squeezes the free-text fields to it instead of copying 300 into a
  second file. `type_text` and `press` stop echoing what was typed,
  which put a password into the model's context as readily as a search
  box. The comparison costs one extra round trip per action, measured at
  0.5 ms against a real engine on a 41-node page. Frame retention is
  absent by choice: `_write_frame` was dead code here, and what is kept
  is #85's policy question.
- browser: the watched cast is the page's own frames (`dde17371`).
  `core/browser_frames.py` is a newest-wins bus: one slot per reader, so
  a pane that falls behind loses the stale frame and never the newest, a
  late joiner still gets the current frame, and `dropped` counts the gaps
  so "it stutters" is a number and not an impression.
  `PlaywrightBrowserManager.start_watch` attaches a page-level CDP
  session and turns on `Page.startScreencast` at 2 fps, 800x500, quality
  50; `stop_watch` and `is_watched` end and report it. Verified against
  the installed engine: a real frame of 4024 base64 characters on a
  1280x800 page. Four things read right in the source and only failed
  when run: Playwright's event callback is synchronous, so an
  `async def` handler was constructed and never awaited and the cast
  started cleanly, reported success and produced nothing; reading the
  queue with a timeout on the event loop parks the loop, which stops the
  very callback that would have delivered the frame, so callers go
  off-thread; publishing an empty placeholder on a paced-out frame
  evicted the real frame from the one-slot reader, so the throttle meant
  to protect a slow reader hid the page from it; and the protocol's
  `deviceWidth`/`deviceHeight` is the page viewport while the jpeg is
  scaled to the requested `maxWidth`/`maxHeight`, so an overlay drawn at
  page coordinates lands off by that ratio — both spaces now ride the
  frame as `viewport_*` and `cast_*`. Pacing is ours by choice, not a
  protocol knob: `everyNthFrame` as a rate limiter starved discrete
  actions and the un-acked window is three frames, so the ack goes out
  immediately and the drop happens here. No frame is retained, because
  that is #85's policy question and a silent write here would have
  decided it by accident.
- extensions: the row says which rail the bundle itself runs on (`aa64edcb`).
  The switch said a plugin is on; it did not say what kind of on, and
  here the two facts come apart: a version 1 bundle lists names of tools
  Ephe already implements, so that bundle is a switch, while a version 2
  bundle carries one entry per tool that the confined worker resolves
  inside the plugin directory. `core/plugin_rail.py` decides the rail
  from the manifest itself through `plugin_tools_contract.tool_claims`,
  the same read the scan and the mount use, so the row and the mount
  cannot disagree about one bundle. Three rails: `declarative` (no tool
  at all, the host reads the bundle's files as data), `kernel` (version 1
  names: Ephe's code runs, the bundle switched it on) and `worker`
  (version 2 entries: the bundle's own code, a confined child process,
  behind the signature gate and the per-family approval rule). The
  counts beside the rail are the two that decided it, and a declarative
  row shows none, because "0 tools" on a bundle that declares no tool is
  a number about nothing. The rail is a property of what is declared,
  not of what is enabled; whether one tool answered in this process is
  the mount's record and a different column. The payload omits the key
  where no manifest behind a catalogue entry could be read, since the
  rail of a bundle nobody read is not a fact this surface may state, and
  an absence reads differently from `declarative`. The test prints the
  census of the shipped tree instead of asserting it, which is why the
  flagship migration could move the numbers without making this row lie.
- browser: the step card states what the page answered (`49a2e7d7`).
  The watch frame arrived without the one fact that makes it evidence:
  the backend already ended every browser action with a `STEP_EVIDENCE:`
  line, and the run surface rendered the step's prose and left that
  verdict inside it, so a reader watching a page could see Ephe click
  without seeing whether the environment confirmed anything.
  `app/src/lib/browserStepEvidence.ts` reads the line back with a
  deliberately narrow parse — the first `STEP_EVIDENCE:` it can read as
  JSON, with a verdict inside the two the backend writes, or nothing at
  all — and nothing is the right answer for a step that carried no line,
  because a row that shows a verdict the instrument never produced is
  the same class of defect as a model reporting a test it did not run.
  Inside the row: a count that stayed at zero is left out, so it never
  presents `+0 elements` as a finding and an `unproven` step says that
  one word and nothing else; a loss keeps its sign, because `-5
  elements` is the page having removed something; the backend's own
  reason sentence stays in the audit row, since it is English prose typed
  by the server and the localisation rule exists so a reader who set
  German is not handed it, while the numbers and the verdict need no
  translation to be honest. The facts are typed as `EvidenceFact` and the
  word map is total over that type, so a fact the parser can emit either
  has a key in both bundles or the build stops. The payloads in the tests
  are copied from a live run of `browser_go` measured on 2026-11-05, so
  the field names asserted there are the ones the backend writes.
- plugins: a bundle serves the name it declares (`fa88f333`).
  The owner's decision, and it retires a rule from #13: `components.tools`
  entries are served under the name the manifest writes, so `web_search`
  stays `web_search` when `web-research`'s implementation moves behind
  the confined worker — that string is what the model was taught, what
  prompts name, what tool cards render and what saved sessions hold.
  Migrating a capability must not rename it. What the prefix was believed
  to be for is already done by two guards:
  `plugin_tools_contract.reserved_namespace(name)` consults
  `default_reserved_names()` — the whole kernel map plus the live MCP
  catalog — and `register` refuses a name either holds with that
  namespace's own code, so a bundle cannot take `web_search` while the
  kernel still owns it; and `plugin_registry.scan_tool_activations` marks
  a name two manifests both declare as contested, which
  `plugin_mount_trust.refuse_contested_names` denies with a reason naming
  both claimants. Dropping the derivation also drops a collision it
  manufactured: `timer` + `lite_x` and `timer-lite` + `x` used to spell
  one served name, which no single manifest could see coming, and the pair
  that is genuinely contested — two bundles declaring `tick` — is now the
  case the tests exercise. `served_tool_name` in
  `core/tools/dynamic_registry.py` stays the one function the manifest
  scan, the mount and the gate call, returning the declared name;
  `PLUGIN_PREFIX` and the dash-normalising helper go with it, because a
  constant nothing reads is a rule nobody enforces. The consequence for
  the flagship migration is that each bundle becomes an atomic swap, which
  is why this lands first: it declares its existing names, the kernel
  entry retires in the same commit, and a mount attempted before that
  retirement is refused with a coded reason instead of silently shadowing.
- ci: the hook judges the catalog row a bundle edit leaves behind (`e1ec1e68`).
  A bundle edit without its catalog row makes the store name bytes the
  directory no longer holds. Measured on 0ef1c8e6: two rows drifted, the
  drift gate exited 1 and the full suite carried 14 failures, while the
  commit hook stayed green because it had no catalog check — the drift
  survived six commits. `scripts/catalog_staged.py` reads the INDEX and
  not the disk, because on a shared tree the file on disk can carry
  another strand's unfinished edit and a refusal naming an unstaged byte
  would be this hook's own version of that defect; the index is what the
  bundle and the row will both say once the commit exists. Scope is what
  the commit takes: a bundle path names its own slug, a catalog path
  names the slugs whose row changes against HEAD, so a catalog-only
  commit is judged on its own rows and not on every bundle in the shared
  index, and the whole-tree check stays in CI where a clean checkout is
  what gets judged. Exit 0 the rows match, 1 drift, 2 the inputs could
  not be read — a signal death and an unreadable input are no verdict,
  not a pass. Receipt: eight tests, seven of them red before the script
  existed; end to end on this tree a staged bundle edit alone refuses
  with exit 1 and names the bundle, and the same edit with a regenerated
  row passes with exit 0.
- ci: the hook judges the skills lock beside the plugin catalog (`928b21d5`).
  The skills lock is the second committed catalog and `ephe doctor` reads
  it, and 5f3e8e29 edited the image-creator pack and left the row behind:
  the lock gate exited 1, doctor printed that the lock was missing and
  exited 1, and that one stale row failed eight doctor tests plus three
  lock and catalog tests — twelve reds from one line. Neither catalog had
  a hook check, so both edits landed without one. The same index reader
  now carries both: a `skills/<pack>` path names its pack, a
  `skills-lock.json` path names the packs whose row changes against HEAD.
  The pack hash is the generator's own algorithm over the index blobs —
  SKILL.md and the four counted subfolders `references/`, `templates/`,
  `scripts/`, `assets/`, sorted as `relpath\n<sha256>\n` — so a file
  outside those cannot move the row. A no-verdict outranks a drift and
  both refuse the commit. Receipt: six new tests red before the branch
  existed, 23 green across the gate and the existing hook contracts; end
  to end a staged pack edit alone refuses with exit 1 and names
  image-creator, and with a regenerated row it passes with exit 0.
- plugins: a bundle tool can declare the MCP rail (`7463a532`).
  `descriptors_for` hard-coded the plugin transport, so no manifest could
  reach the MCP rail — `TRANSPORT_MCP` lived only in the registry
  vocabulary and in tests that built a descriptor by hand. That was
  blocker (1) of the walking skeleton at the descriptor layer. A version 2
  tool may now carry `transport: "mcp"` beside a `components.mcp` server
  entry, and the descriptor carries that transport with no entry of its
  own, because the server owns the callable. Validation refuses the shapes
  that would promise a rail nothing answers: an MCP tool without a
  declared server, a second entry on an MCP tool, a transport outside the
  two the registry carries, and a server entry that escapes the bundle by
  the same lexical rule a plugin callable uses. The host imports none of
  it, per ruling A1; the confined server runs it in the next slice. The
  served name keeps the rail's `mcp_` prefix, which the registry's
  namespace rule requires. Ownership stays the bundle's: `_gate_with`
  reads `activations.get(name)` before the blanket connector rule, so a
  name a manifest declares is answered by that manifest and the connector
  rule only fires for a name no manifest owns. Receipt: eight tests, six
  red before the change, 111 green across the transport slice and the
  surrounding contract, registry, wiring, DoD and runtime files.
- teams: the leader reads each report and gives the next order (`3e9a38dc`).
  The four shipped orchestrations — `leader`, `parallel`, `sequential`,
  `review` — run a single cycle: members work once and the leader
  summarizes. A real team keeps going until the work is done, so
  `iterative` is the fifth value in `ORCHESTRATIONS`
  (`core/agent_team_schema.py:20`): the leader reads the member reports
  and replies with a structured decision, either sending one named member
  back with a specific instruction or finishing with a summary. The loop
  is bounded by a new `max_iterations` budget, clamped to 1..8 with
  default 3, on top of the member and wall-clock caps, and it terminates
  fail-safe when a decision cannot be read or names a member the team does
  not have, so an unreadable reply ends the run instead of spinning. The
  six new tests watched the mode refused before it existed.
- teams: the iterative mode is selectable and keeps its own cap (`b4114acd`).
  The team editor now offers `iterative` in its orchestration dropdown
  and, when it is chosen, a bounded leader-round cap beside the member and
  wall-clock budgets. The budget handlers spread the existing budget
  object, so editing one field no longer drops the iteration cap — which
  the first red tests caught. Both language bundles carry the new labels,
  and the four editor tests watched the option and the cap field absent
  before they existed.
- agents: delegation is a control the user can switch in Settings (`2867fcfe`).
  The main agent's `spawn_agent` tool was always offered. The agent team
  is now activatable like a plugin: `advanced.agent_team_enabled` is a
  deep-settings boolean in the Advanced area and
  `core/tools/registry.py` appends `SPAWN_AGENT_SCHEMA` only while
  `deep_bool` answers true, so switching it off withdraws the tool from
  the schema array. The default stays on, which keeps the behaviour an
  installation that sets nothing already had. The field is a real control
  by the register's own bar: a production reader calls it by its full key
  and its card carries both language texts through `labelKey` and
  `hintKey` in the locale bundles. Three tests watched the switch do
  nothing before the reader existed, and the settings-register contract
  suite stays green.
- plugin-mcp: the walking skeleton routes one tool call through a confined server (`43d20ae2`).
  Slice 2 of #50: a plugin declaring `components.mcp` can now serve tools
  over the MCP rail. `core/plugin_mcp_server.py` starts the plugin's server
  as a confined subprocess, discovers tools with `tools/list`, and routes
  `tools/call` through the live JSON-RPC connection, so ruling A1 holds and
  the host keeps its distance from the plugin's server module. Three tests
  pin the contract rather than the implementation: a live call reaches the
  subprocess and returns its answer, an unstarted server refuses with the
  existing 'not available' line, and stopping the server reaps the
  subprocess.

- plugins: a mount reports each tool it registered (`86279bb5`).
  `plugin.mount` still carries the whole set for a consumer that wants one
  frame, and each tool now arrives as its own `plugin.tool_registered` event
  before it. A subscriber that reacts to one tool no longer decomposes a batch
  to find it, which is where a plugin reacting to another plugin starts. The
  mount's observable surface went from one event to N+1 and
  `tests/test_plugin_registration_events.py` pins the count.

- plugins: a listener can ask for one plugin's events (`9a0e5e41`).
  `subscribe_filtered()` sits beside `subscribe()` on the lifecycle bus and takes
  a `plugin_id`, an `event_type`, or both. `_matches_filters()` decides on the
  bus, so a plugin watching another one's registrations stops receiving every
  other plugin's noise. The filtered list is kept beside the unfiltered one and
  a single `unsubscribe()` clears both.

- surface: the plugin names the slot it renders in (`cb52a2d8`).
  `SurfaceDescriptor.slot` is an optional `overlay`, `native` or `side-panel`,
  and `resolveSurfaceSlot()` honors a declaration over the runtime default. A
  plugin that says `side-panel` on desktop gets the side panel; the host's guess
  (native on desktop, overlay in a browser tab) now decides only a manifest that
  says nothing. The type is declared once in `pluginSurface.ts` and re-exported
  from `surfaceHost.ts`, so the two halves cannot drift apart.


































### Fixed

- tools: a plain-def handler is answered instead of awaited (`ef56e57f`).
  `execute_tool` ended its gate chain with `await func(**arguments)` for every name in
  `TOOL_MAP`, and 7 of its 36 entries are ordinary functions. Awaiting a `str` raises, so
  the handler ran, its side effect was kept, and the answer was lost — the model saw
  `object str can't be used in 'await' expression` where a bundle path should have been.
  Live run4 named it, and the four creator calls were the newest entries in the map, so
  the mode could not answer any of them; `plugin_manager`, `start_workspace_dev_server`
  and `stop_workspace_dev_server` had been unreachable the same way before this change.
  The check is `inspect.isawaitable` on what came back, which covers a plain function, a
  coroutine function and any awaitable a handler returns, so a future sync tool needs no
  registry edit. A `def` handler answering is pinned in `tests/test_tools_registry.py`,
  and `TestKernelDispatch` in `tests/test_creator_tools.py` runs scaffold, write, verify
  and install through the real registry and refuses a `[tool-error` in the answer.
  28 passed in the file, 105 across the creator, bridge and guard selection.

- tools: a bridged call reaches its tool with the parameters the engine sent (`6f6b0c9b`).
  The `tool_call` envelope carries an inner name and an inner object, and dispatch read
  the name and then handed the envelope itself to the tool as its arguments. The tool was
  therefore validated against `{"name": ..., "arguments": ...}` and refused for a
  parameter the engine had in fact sent. Both shapes a provider uses are read now, dict
  and JSON string, and text that is not an object becomes an empty argument list, which
  is the one shape the required-parameter check can answer with a repair the model can
  act on. `tests/test_bridge_attribution.py` pins the inner dict, the string envelope and
  an envelope that carries no parameters at all. 6 passed, failing first on the envelope
  still sitting in `parsed[0][2]`.

- creator: the mode instruction reaches the turn and survives a withheld call (`ea244a20`).
  Two defects in one string. `CREATOR_MODE_GUARD` existed in `core/persona.py` while
  `_mode_context()` appended the compute, page-output and architect guards behind their
  flags, so the consent screen described a mode the model was never told about. The
  sentence that then landed was worse than silence: it asked for a full stop whenever one
  creator call was missing, and live run3 obeyed that literally after
  `install_plugin_bundle` was refused for a privilege the case does not grant, answering
  `tools=0 staged=0` with three calls already executed and nothing staged. The guard now
  runs the calls the grant covers, names the step it could not take and the privilege it
  needs, and still forbids substituting the file tools for a missing call. run5 opens
  with the guard quoted in its own first sentence and reaches `tools=7 staged=2`. 49
  passed in `tests/test_creator_guard.py`, red first on the calls being thrown away.

- creator: the model is offered the calls this session's grant covers (`cecb0dee`).
  A creator-mode turn that had consented to the files privilege reached the engine with no
  creator name in its tool array, so the model had no way to write the bundle it was asked
  to build and answered with a sentence about it instead. Two independent seams produced
  that array. `_tools_for_messages()` narrowed its default path to `discovery.CORE_TOOLS`
  (42 names, none of them a creator name), and `chat_context._cached_tool_schemas()` kept a
  second TTL window — over the *filtered* offer, so a turn could be served the names another
  session's mode had produced. The window row in `test_w2_wc24_window_fit.py` asserted
  `first is second`, which is the defect written as an expectation. The registry already
  caches the unfiltered base and applies `_apply_plugin_filter()` on every return; the chat
  path now reads through it with no cache of its own, and the default array is widened by
  `creator_guard.CREATOR_TOOL_NAMES` (4 names), the same set `filter_offer()` removes again
  when the session has not consented. Six rows in the new `TestModelOfferArray` fail first,
  each naming `write_plugin_source`; the window row now asserts the registry is read twice
  and says why. Dropping the second cache costs one filter pass over a 78-entry array,
  measured 2.563 ms median and 2.602 ms p95 per turn beside a multi-second engine call.
  127 passed over the creator, snapshot, window-fit and offer selection.

- core: the settings refusal answers every reader in one language (`b72f10e5`).
  Of the six refusals `validate_sections()` can raise, four were English sentences and the
  two that name a value were German — and they are not comments. The route renders the
  `ValueError` text as the 422 detail, the exception handler moves a string detail to
  `error.message`, and the settings toast shows that message under its localized title.
  An English reader who typed a timeout of 10^9 was answered in German while the reader
  beside them, who mistyped the key, was answered in English: which language arrived
  depended on which line the value failed on. The two messages now read like the sibling
  next to them (`<field>: <value> outside [min, max]`, `<field>: <value> is not one of [...]`)
  and keep listing the legal values, because translating must not cost the reader the fix.
  Nothing parsed the old wording — every settings test used a bare `pytest.raises` with no
  match, and the repair classifier at `core/tools/registry.py:748` reads tool-error text,
  which never reaches this function, so its back-compat match stays. The new test asks the
  language gate's own marker list, imported rather than restated, over all six refusals and
  again at the field the client reads. Over the previous file 4 failed and 1 passed, each
  failure naming its German word; after, 5 passed, with 429 passed and 11 skipped over the
  settings, import, repair and redaction selection. Three developer-facing strings in the
  same file stay German and are named in the commit rather than quietly skipped.

- core: the shell judges a glob by what it matches, not by its spelling (`ddd9b1d9`).
  A pattern holding a `..` part was refused before the code looked at where it lands, so
  `cat src/../docs/*.md` — inside the workspace — lost to the same line that refuses
  `cat ../.ssh/*.md`. The match loop underneath already decides both: pathlib walks a `..`
  the way the shell the command spawns does, and every match passes `_check_resolved`, the
  door a plain file argument uses. A probe over eleven spellings removed two theories this
  slice first believed: an escaping pattern does *not* match nothing here, so the literal
  head check written for that theory guarded nothing and was dropped, and a pattern that
  matches nothing is not a read. The escape tests moved to a folder `DENY_ROOTS` names under
  a test-owned HOME, because the kernel lists the system temp folder among its allowed roots
  and a folder beside a temp workspace is a legal read. Over the previous file 1 failed and
  7 passed; after, 8 passed, with 372 passed and 13 skipped over the shell, glob, path-guard
  and sandbox selection. A credential-shaped name is still refused where it is written
  (`../.ssh/id_rsa*`), and `**` stays refused because a recursive walk is a cost, not a path.

- core: the audit page masks the lines the log wrote before the pattern existed (`c8db491e`).
  `redact()` runs at the write and its pattern set has grown since: the GitLab, AWS and Google
  shapes entered `_KEY_LITERALS` after months of audit lines were already on disk, and `tail`
  handed those stored fields to `/api/audit` as read, so a key the writer could not name stayed
  in the clear for every reader after it. Rewriting the log is not the fix — each line carries
  the digest of the one before it, which is what `verify_chain` exists to notice, and `clear()`
  refuses for the same reason. The mask moves to the read: the file stays byte-identical, the
  count still describes the same log the page does, and a credential-shaped run in any text
  field of a served entry goes. `tests/test_audit_read_side_redaction.py` proves the leak first
  (7 failed, 2 passed — the two that passed are the byte-identity and unchanged-line cases the
  fix must not break), 18 passed after, and 341 passed with 2 skipped over the audit, redaction
  and secret selection. One limitation the same probe made visible is filed, not changed: the
  `\b` in `_KEY_LITERALS` lets a key glued behind a word character through (`run_glpat-…` is
  served unmasked), and loosening it would also mask ordinary identifiers ending in `sk-`,
  with no product path known that writes a glued key.

- server: the file route reads its scope from the kernel on every call (`2d6fc7ff`).
  `358734d2` closed the by-value capture in the browse route, and the same shape was still
  standing in `server/routes/files.py`, the route that decides whether a browser may read an
  artifact file. `tests/test_routes_read_the_kernel_list.py` guards that one route from both
  directions and could not see a second route repeating the move, so this adds the class:
  `tests/test_routes_bind_the_scope_helpers_late.py` reads every module under `server/` and
  refuses a top-level `from core.tools.base import` of the five scope names, names the file and
  the line, and proves its own reach against a fixture module. A function-local import is left
  alone, which is the deliberate half of the boundary: `server/routes/artifacts.py:349` and
  `core/artifact_workbench.py:109` re-read the attribute on each call, and hoisting either line
  into the import block is what now fails. Runtime behaviour is unchanged, since nothing rebinds
  the helper while the product runs; what the freeze costs is a guard that stops answering the
  kernel, the failure that made the browse route serve 403 for another test's temp folder. The
  guard failed on this route before the change (1 failed, 8 passed), 110 passed over the scope,
  artifact, kernel-list and path route files after it, and 1468 passed over the wider
  file/artifact/route selection.

- deps: the four named CVE exposures, each held by the instrument that can reach it (`1cfbcc67`).
  Read against the installs and the lock, three were already closed and one was open, and the
  open one was invisible to every advisory instrument in this repository. CVE-2026-114583 (a
  `tarfile` link member named after the destination escapes the extraction filter) and
  CVE-2026-115557 (the eMudhra CA compromise) are interpreter fixes, so `pip-audit` never sees
  them, and the register cannot hold them either: OSV answers both with a Git-scoped record
  whose `affected[].package` is empty, which is the exact thing
  `scripts/advisory_id_check.py` rejects. `.python-version` names 3.13.18, the first 3.13
  carrying both, measured against the installs on this machine — 3.13.17 completes the upstream
  distrusted handshake and leaves the link member unrefused, 3.13.18 refuses both — and
  `tests/test_cpython_security_release_floor.py` now asserts that on the interpreter running
  the suite rather than skipping a below-floor one: 4 failed on 3.13.17, 8 passed on 3.13.18.
  CVE-2026-118662 (vite serves a `server.fs.deny` path when the request carries a query
  string) covers `>=6.4.4,<6.4.5` and the lane moved to 6.4.5 in `30777a1e`, the day after the
  advisory published; that record names its package, so it is the one the register can hold,
  and the existing npm fence was proved against a lock with the vite resolutions walked back to
  6.4.4 before the row was trusted. CVE-2026-120474 (undici hands one user's cached private
  response to another after a same-origin redirect) was the open exposure: the lock resolved
  undici@8.12.2, inside the affected range, while `pnpm audit` reported 0 findings because
  GHSA-7xg3-fphp-28hg 404s in OSV and the CVE record is Git-scoped. undici reaches this tree
  only as jsdom's own `^8.11.2`, so an override in `app/pnpm-workspace.yaml` is what moves it:
  raised to 8.12.4, re-resolved to a single undici, held by
  `tests/test_undici_override_floor.py`. Frontend suite on the new resolution: 517 files, 3663
  tests, 0 failed.

- server: a guard reads its root list from the module that owns it (`358734d2`).
  `server/routes/fs.py` bound `_get_allowed_roots` with a `from … import`, which
  copies the name into the route's own namespace the first time the module is
  imported. A test that patches the kernel and mounts the app inside that window
  leaves the browse route holding the patch after the test is gone: measured in
  the pair `tests/test_r5_framed_document_isolation.py` and
  `tests/test_routes_paths_extra.py`, the kernel answered 13 roots while the
  route answered 1 — another test's temp folder — and every `/api/fs` request
  that ran after them came back 403 `path not in allowed roots`. `network.py`
  carried the same capture in the settings row that prints the roots the file
  guard enforces, so that row could name folders the guard had stopped reading.
  Both routes now reach through `core.tools.base` on every call, which is what
  lets a patch be honoured while it lives and cost nothing once it is undone;
  the two new tests assert both directions and the batch went from 14 failed to
  80 passed.

- files: the artifact route reads the scope the surface shows (`7d59aeba`).
  #81 narrowed this read on main and the lane kept the wide one: `/api/file`
  asked the kernel's list, which covers the home folder, Desktop, Documents,
  Downloads, Developer, Code, Projects, three temp entries and the workspace,
  while the surface that hands back a file is the workspace and its output
  folder. The route builds its own answer now — for a browser, the workspace and
  the output directory; inside a plugin call, the workspace and the data roots
  that bundle declares, through the one `resolved_data_roots` the confined worker
  uses, so a bundle sees the same reach on both rails. The refusal a browser gets
  names those two folders where the sentence had promised the wider set, in the
  template and in both locale bundles. `tests/test_artifact_route_scope.py` pins
  the scope in both directions and fails when the copy drifts back to naming a
  folder the route does not read. What the first full run caught: the offline
  defaults case framed a PNG from a temp folder the narrowed route may not open,
  so it asserted frame headers on a 403 — it declares `EPHE_WORKSPACE` now
  (`76c3832a`).

- chat: a bridge call is recorded under the tool that ran (`2f017582`).
  When the engine reaches a tool through the bridge it calls
  `tool_call(name="read_file", …)`, and the dispatch callbacks reported the outer
  name. The activity line, the audit row and the tool card all said `tool_call`
  where the reader wants the tool that actually ran, so a turn that read a file
  and ran a command looked like two identical bridge calls. `_parse_tool_calls`
  resolves the inner name when the outer one is the bridge, and parses an
  arguments payload that arrives as a JSON string before reading it.

- tests: a proxy entry the parser cannot read no longer stops the run (`f62cdcfa`).
  `NO_PROXY` carrying a bare `::1` makes httpx 0.28 raise `InvalidURL` at the
  moment `ollama` builds its default client, which is at import; collection
  imports every test module, and `core.chat` imports `ollama`, so one variable in
  the environment turned the whole suite into a crash before a single fixture
  ran. `pytest_configure` now clears the proxy variables before collection, and
  the per-test fixture keeps them clear during execution. Measured: 9453 tests
  collected with `NO_PROXY` set, 0 errors.

- cli: the matrix offers a bundle with no skill what Ephe offers (`c21f8428`).
  A bundle that declares no skill pack has no grant, and the runner read that
  as a grant of nothing. The empty list is the encoding the offer builder reads
  as "ship an empty array", while the chat route hands None when no skill
  resolves and the engine then ships its core kernel. Seven suites (countdown,
  guide, mcp-connector, plugin-creator, skill-creator, vision, voice) were
  graded on a turn no Ephe session is ever given. The offer is now proven
  against the product's own builder, so the two cannot drift apart in silence.

- files: the preview names its bytes and the refusal names a next step (`94c2b60e`).
  Task #80's slice. The file route answered its refusals with bespoke
  sentences, the preview turned a PNG into mojibake and a CSV with quoted
  commas into a mis-split table, and a Range request could not be honoured
  because the payload carried no size. `error.reason_code` now carries the
  route's own code for `file_not_found`, `file_path_protected`,
  `file_path_not_allowed` and `file_too_large`; all four are registered in
  REASONS at server/refusals.py:272-286, carry one key in each locale
  bundle, and appear in the sentence table the actionable-message test
  drives at tests/test_refusal_messages_actionable.py:106-109, so the
  envelope says which one fired and the copy says what to do next.
  `preview_payload` returns `size_bytes` from stat on every mode, which is
  what makes the route's Accept-Ranges claim true instead of asserting a
  number a test invented. The null-byte guard is scoped by extension:
  xlsx, xls, docx and pptx are zip containers whose own renderer reads
  their bytes on purpose, and the unscoped guard refused them before that
  renderer ever saw them — a regression this slice introduced while fixing
  the PNG it was written for, and the PNG test still holds. CSV parses
  through the stdlib csv module, so quoted commas, embedded newlines and
  escaped quotes survive. Measured: the full backend suite went from 16
  failed / 9135 passed to 3 failed / 9148 passed and the 191 tests across
  the nine files this slice touches pass on their own; the three that
  remain pass standalone and inside the tests/test_s*.py block, so they
  are order-dependent pollution and carry their own task.

- tests: the eight calls the async dispatch left unawaited (`ccfadf26`).
  Making `dispatch_dynamic_call` a coroutine changed the calling convention
  of a function five test files reach, and only the three tests written
  beside the change were carried with it. The eight that were not all fail
  the same way: the double never runs, so a count that should be one reads
  zero. The seam itself carried two faults — its `_dispatch` answered
  synchronously and ran the executor through `asyncio.run()`, which cannot
  be called from the loop the test is already inside, and it handed back a
  plain value where the registry awaits one. Its kernel branch was
  unreachable as well: `execute_tool` folds a marker to its bundle name
  before the map lookup, and the map is keyed by the marker, so the bundle
  name is never a key. The map entry stays what its own comment says it
  is, the reachability contract and not the call, and the branch stays
  dead without lying about it; awaiting the executor fixes both. The other
  two consumers had simply kept the old convention: one test stayed a sync
  `def` and read a coroutine as a string, one monkeypatched a sync
  recorder onto a call the registry awaits. Measured: the six files that
  use the seam went from 8 failed / 235 passed to 74 passed, and the full
  suite from 24 failed / 9127 passed to 16 failed / 9135 passed — the eight
  are the difference and nothing else moved. The sixteen that remained
  belonged to the then-uncommitted file-route slice, which is the row
  above. No production code moved: the async signature is what the MCP rail
  needs, and every fault here was a consumer that had not followed it.

- api: a refused method names its code and its methods (`c41e5bb0`).
  The 405 handler tried to read the Allow header from the exception, but
  FastAPI's router raises HTTPException without headers when a method is
  refused, so the refusal that was supposed to say which methods exist
  said nothing. The handler now falls back to searching the router for the
  matched route and extracting its methods. The second half was in the
  mount: the SPA mounted at "/" caught `/api/*` paths before the router
  could refuse the method, answering 404 instead of 405, so `SPAMount`
  (server/spa.py:31) returns NONE for the prefixes the API owns and lets
  the router continue to the actual API routes and refuse properly.
  Measured: tests/test_method_refusal.py 5 of 5 pass, where it was 2 of 5.

- i18n: the merge raised the locale ceilings to the measured merged size (`783f768e`).
  The reconciliation brought device, workspaces and browser keys in from
  the trunk. Measured after the merge: en.json 152,095 B and de.json
  165,067 B, both over the ceilings the lane had held, so the ceilings
  moved to the measured values plus the 1,000 B headroom the earlier waves
  kept, and app/src/locales/bundleSize.test.ts gained a per-file assertion
  so a later merge that pushes past them fails the suite instead of
  drifting. The sequence is worth stating plainly: the owner had dissolved
  this budget on 2026-11-05, this commit two days later still raised the
  number rather than removing it, and the enforcement came out again in
  `cc3f7d2d` — which leaves this row as the record of a step that should
  not have been needed, and the weight report and the inflation bound as
  what the file still checks.

- i18n: the tsc build is clean and the locale bundles name their watch keys (`caa057ee`).
  The TypeScript build carried nine errors in two test files: `vi.fn()`
  inferred zero-parameter mocks, so `.mock.calls[N]?.[M]` and a
  `mockImplementation` with parameters failed the type checker, and the
  mocks now carry explicit signatures. Nine `chat.watch*` keys that the
  components already used through a `defaultValue` fallback are now present
  in both bundles, so the strings the run surface shows are the catalog's
  and not a code-side default; two of them, `watchBound` and `watchPause`,
  are same-by-design copies — a placeholder and a loanword — and are listed
  as such rather than translated into a false difference.

- agents: a subagent tool result names the call it answers (`407b0e7f`).
  A live team run on a remote OpenAI-compatible engine lost both members
  right after their first tool call: the helper loop appended a
  `role=tool` message with no `tool_call_id`, and the wire converter
  refuses an orphaned result, so the helper died with a
  `ToolWireViolation` instead of reporting back. The loop now names each
  result with the same id the assistant block registered — the engine's
  own id, or the positional fallback when it sent none — on the executed
  result and on the whitelist denial alike. Three tests drove the real
  converter red before the change, and the same live run afterwards
  finished with both members reporting.

- skills: the lock carries the hash the image pack now has (`da5a7f2b`).
  5f3e8e29 changed the image-creator pack so its prompt states the png
  name the tool writes, and left `skills-lock.json` behind. The lock gate
  exited 1 on that tree and `ephe doctor` reads the same lock: it printed
  that the lock was missing and exited 1, which failed eight doctor tests
  on top of the three lock and catalog tests. One stale row, twelve red
  tests. Regenerated — the diff is the image-creator hash and nothing
  else, the gate answers exit 0, and the eight affected files pass 168
  with 10 skipped, the twelve former failures among them. The commit hook
  still had no skills-lock check when this landed, so the same edit could
  land again without one; that gap is the next row.

- plugins: the catalog carries the hashes the bundles now have (`793f9708`).
  08e192d5 changed the document factory and the research notebook so their
  prompts follow the writers, and left both catalog rows behind. The drift
  gate exited 1 on that tree: two sha256 rows named bytes the directories
  no longer held. The full suite reads those rows, which is why the last
  complete reading carried 14 failures while the commit hook stayed green
  — the hook had no catalog check, so a bundle edit could land without
  one. Regenerated: the diff is the two sha256 rows in
  `plugin-catalog.json` and nothing else, and the gate answers fresh over
  the 17 bundles with 0 skipped.

- plugins: the voice names stay importable off the kernel map (`4e569812`).
  The schema list asks `core.tools` for every offered name, and
  `synthesize` and `transcribe` are the functions behind those two
  offers, so they are now exported from `core/tools/__init__.py` while
  staying off the kernel map, which is where they belong. The marketplace
  row for the voice bundle follows the 1.1.0 manifest it actually ships.

- plugins: the stored-file delete takes the read-only brake (`8abe285b`).
  The remove route deleted a stored file without the brake the switch
  routes use, and its 400 carried a code no refusal table knew. The
  brake now audits the refusal before any unlink. A name the bundle
  does not hold is plugin_state_name, with a next step on Extensions.

- tools: a missing parameter is refused before the worker (`50a5d5b0`).
  A contributed call repaired a missing required parameter into an empty
  value, then the worker answered with the directory refusal. The
  validator had already named missing-param. Enum repair stays. The
  missing parameter is returned before the worker starts.

- skills: a marker folds onto the bundle tool it names (`113bd5b4`).
  The named-tool rule folded read onto read_file, then kept the fold
  only when that name was still a kernel-map key. read_file left the
  map with the shell bundle, so the fold was dropped, the rule
  abstained, and a partial skill took the session. The fold now stands
  when the bundle name is one a skill can declare.

- skills: the picture and deck prompts carry the output contract (`f06042a5`).
  image-studio and presentations named the tools and the finish line and
  left out the contract block the other bundles carry. Both prompts now
  name the path the tool prints and require that claim to come from real
  tool output.

- skills: a quoted heading marker stays inside the prompt (`32317339`).
  The system-prompt cut searched for the two characters anywhere in the
  tail. The documents pack names those characters in a sentence, so the
  served prompt stopped there and the contract under that sentence never
  reached a model. Measured: 492 of 2871 characters served. The cut is
  now the next heading line.

- tests: the tool double sits on the dispatch the name takes (`2cef6bef`).
  A contributed name is not in the kernel map, and patching it in there
  did worse than miss the call: the reserved name space is the kernel map,
  so the entry made the bundle's own claim on that name a collision, the
  activation scan reported a conflict, and the plugin gate refused the
  call before any dispatch. Measured: conflicts `[]` -> `['read_file']`,
  gate `visible=True` -> `visible=False`, and back to `[]` once the entry
  left. The helper now reads the same two authorities `execute_tool` reads
  — the marker alias and the kernel map — and carries the double on the
  seam the call uses: a kernel name keeps the map, a contributed name gets
  the worker seam, and an awaitable double keeps its await count because
  that seam runs on a thread with no loop of its own. Six red assertions
  turn green, 44 passed across the four files, and the denial assertions
  that were green on the plugin refusal are now load-bearing: with the
  chat gate mutated to always approve, 14 of them fail.

- net: the proxy rewrite reaches the client without loading it (`e5aa8f91`).
  The core package imported the HTTP client to patch its constructors, and
  that package imports a renderer the CLI startup budget counts as heavy,
  so `import ephe_cli` loaded it. The environment rewrite now runs on the
  standard library alone and an import hook patches the constructors as
  the client package loads. A client cannot be built before its package
  has loaded, so every constructor call still normalizes first. Measured:
  with the hook removed and the rewrite alone, three tests bring back
  `Invalid port: ':1]'`, the new subprocess guard among them.

- tools: the marker names on the offer are importable (`de9ed9c4`).
  Every offered name has to resolve to a function in the tool package, and
  bash, read and edit arrived on the offer carrying the bundle's schema
  while the package exported only the canonical three. Each marker is now
  the object the registry holds. The call path is unchanged: execute_tool
  resolves the name to the bundle before the gate.

- tools: marker names call the bundle tool (`3e22561b`).
  bash, read and edit stay on the offer as copies of the bundle schema.
  A call resolves to run_shell, read_file or edit_file before the gate,
  and the worker runs. The kernel object on the marker stays unread.
  Switching the bundle off hides the marker, including the capability
  switch. create_xlsx publishes no path. The kernel function still
  accepts one when a caller passes it.

- net: a bracketed IPv6 bypass no longer stops an HTTP client from being built (`8a8ebcff`).
  The newest published client, 0.28.1, splits `NO_PROXY` on commas. The entry
  `[::1]` becomes a mount key whose port reads as `:1]`, and construction raises
  `Invalid port: ':1]'`. The same splitter is unchanged upstream. Both client
  constructors rewrite a bracketed IPv6 entry to the bare address before they
  read the environment. The suite clears `HTTP_PROXY`, `HTTPS_PROXY`,
  `ALL_PROXY` and `NO_PROXY` (and their lowercase twins) so two shells start
  from the same empty proxy environment.

- vision: a broken local-client host no longer stops the suite from importing (`51a797b2`).
  The package builds its client at import. A proxy value `http://::1]` raises
  `Invalid port: ':1]'` from that line, and the harness imports the vision module
  for every test. The import is guarded the way the screenshot libraries are, and
  the click path says the client did not load. The suite on this tree, read by the
  worktree virtualenv, was 8930 passed, 161 skipped, 1 xfailed.

- plugins: a hot-mounted name leaves the addressable set when the mount does (`c831dfdf`).
  The manifest scan was cached on a module global for the life of the process.
  Mount and unmount drop that scan. A contributed name from a bundle that ships
  with the tree stays addressable, because this checkout publishes it on read.
  Any other contributed name is addressable while the descriptor registry holds
  the bundle, and leaves the set when unmount drops that entry.

- tools: the chat gate for the two research tools is the set each one already sat in (`90721abb`).
  `web_search` is on the chat auto-run list and is not in the read-only set, so
  the chat path runs it and the default CLI approval does not. `fetch_url` is in
  the read-only set, so the chat path and the default approval both let it run.
  Those memberships predate the worker swap. An earlier unreleased sentence said
  `fetch_url` still asks. That sentence was measuring the wrong set, and the
  sentence above replaces it.

- docs: the SDK said a permission line meant nothing (`af06fefc`). `permissions.data_roots`
  was described as "for display/intent only" while the marketplace diff already treated a new
  root as a permission change worth asking the user about, and the kernel file scope already
  honoured it. The section now says what the field grants, on which rail, with which bounds —
  read-only, an existing directory, never a home or system root, a workspace-relative name
  that cannot escape the workspace — and where the boundary still says no.

- plugins: a declared memory ceiling killed the tool that declared it (`c6c07c08`). The
  worker's bootstrap applied `RLIMIT_AS` before loading the entry, and `policy_snapshot` said
  the ceiling was enforced in the child whenever the spec declared one. Exercising that path
  measured it instead: on this macOS `resource.setrlimit` refuses every finite value — 256 MB,
  512 MB, 1 GB, 2 GB and 4 GB were tried, with both limits reported unbounded — the
  `ValueError` escaped the bootstrap, and the child died with exit code 1 before the plugin
  loaded. The bootstrap now applies the ceiling where the OS takes it and writes its verdict in
  one line, `run_worker` lifts that to `WorkerOutcome.memory_ceiling` (`applied`, `refused`,
  `unknown`, or empty when nothing was declared), and the `memory_mb` row states what was
  observed rather than what the code intended. The same measurement found the second half of
  the bug: `python -c` does not put the script's directory on `sys.path` the way `python
  script.py` does, so the capped form of the worker could not have found a module sitting beside
  the launcher. Both forms agree now, which the confined test runs on purpose.

- browser: the guard the watch route calls was left in the working tree (`6be3edeb`).
  `ed64a3ed` committed `server/routes/browser_watch.py`, and that route's
  first act is `manager.has_session(session)` — the check that a name from
  the URL does not open a browser. The method was written into
  `core/browser.py` and never staged, so the commit at the time called a
  method the tree at the same commit did not have: a fresh checkout
  answered the unknown session with an `AttributeError` (a 500) instead of
  the coded 404, which is the one branch that exists to refuse a caller.
  Why the suite missed it is the reusable part: every case in
  `tests/test_browser_watch_route.py` drives a fake manager, so a method
  missing on the real class is invisible to all of them, and the full run
  executes the working tree rather than the commit — the instrument was
  the right shape and pointed at the wrong object. This adds the check
  that would have failed: the three names the route reaches for are
  asserted on `PlaywrightBrowserManager` itself with the shape each needs,
  `has_session` synchronous because the guard runs before any await,
  `start_watch` and `stop_watch` coroutines because they talk to the
  engine, plus the default the route depends on. Proved in both
  directions: against the previous `core/browser.py` it fails with the
  message naming the missing method, and against the file committed here
  it passes.

- approval: the enumerated licence reads the runtime the gate reads (`ac7cb427`).
  `chat_no_confirm_tools()` promised "the set the gate actually uses" and
  consulted two of the licence's four conditions: the stored sign-in and
  the name. `chat_tool_requires_confirm()` consults those plus the
  runtime containment of `execute_code` and the user's ask-more category,
  so the two disagreed whenever a cell was not carrying the turn or a
  category was set to prompt. Measured in the CI-shape run
  (`pytest tests/ -n auto`, worker gw2): the enumerated set listed
  `execute_code` while the gate answered that it requires a dialog, and
  the bounds gate that exists to catch exactly this pair failed. In a
  single process the same test passes, because the cell state it depends
  on was the one the earlier test in that worker left behind — an
  order-dependent read of a security decision, worth fixing for the
  behaviour rather than for the flake. Severity stated honestly: no
  production path dispatched from the enumerated set, since
  `core/tools/approval.py` re-exports it and the chat path asks the gate,
  so this was a latent hazard and not a live bypass — the kind that
  becomes live the first time a caller trusts the list. The set now
  applies the same three runtime checks in the same order as the gate,
  and the fourth condition (the opt-in confidence floor) is documented as
  unreadable from a set because it arrives with the caller's
  `ApprovalPolicy`. The bounds test is rewritten around the cause instead
  of the symptom: it steps through all eight shapes of the three runtime
  conditions, each installed through the environment
  (`core.cpython_cell.code_runs_uncontained`,
  `core.security_config.load_security_config`, the profile dict), because
  the file's own rule is that the gate's decision is never stubbed, and it
  stops writing the module dict directly, which is how a neighbouring test
  could decide what the pass started from.

- chat: the composer gives the chat its room back (`95ead535`).
  An empty composer took 184 px of a 742 px window: a 48 px floor under one line of
  text and a control rail wide enough to wrap into a second 44 px row, and the
  transcript kept whatever was left. The growth rule moved to its own module and is
  stated in lines of the input ramp — one line plus its padding when empty, six
  lines plus the same padding at most — so a multi-line draft stays readable while
  it is edited. It measures before paint and re-measures when the column re-wraps,
  because a draft can change shape without changing text and the message dependency
  alone never noticed. The rail keeps every control at the size it was audited for
  and now fits one line, with the wide gap moved off the columns onto the rows a
  wrapped rail still needs, and the field takes its floor from the width breakpoint
  and the coarse-pointer query so a thumb never gets the thin line a mouse does.
  Measured in the served build: the composer box 184 to 106 px, one control row
  instead of two, transcript viewport 305 to 383 px on the same conversation.

- panel: a CSV opens as the table it is, with its bytes beside it (`dd782d5f`).
  One name, two answers: the artifact card has drawn a spreadsheet suffix as rows
  since the preview module put it in its table kinds, while the workspace column
  asked its own classifier and got a plain type — a code block of commas. The
  server already answers a table for the same path. The column's opener now carries
  a table plan with two views, so a CSV keeps both readings the way Markdown keeps
  the page and the source: the rendered view asks the server and shares the one
  table renderer, the source view stays the copyable bytes, and where the server
  declines the table view falls back to those bytes rather than an empty frame. The
  generic rule is in one place now, so the next two-view format adds a plan branch
  and no new surface code.

- mount: a bundle recorded as mounted is serving again after the process restarts (`a75deb13`).
  The mount records are persisted and the descriptor registry is not, so a fresh
  process started with the record of every mounted bundle and none of its tools,
  while the Extensions surface read the record and kept saying mounted — an
  instrument asserting what it had not read, and a user looking at a tool the model
  was never offered. The first read of the tool set now replays the records through
  the transition that mounted them, so the name scan, the contract pin, the atomic
  swap, the rollback and the per-mount audit row are the same code an HTTP mount
  runs, plus one line for the pass as a whole. The hook sits on the shared read
  rather than one startup path because the command line, the terminal and an
  imported server all reach the tool set through it and only a server would
  remember to call a startup step. The replay acknowledges nothing on the user's
  behalf: a local bundle edited between runs comes back running the new bytes, a
  bundle accepted under a signature record whose files then moved stays refused and
  reports that as the reason its tools are missing, and a bundle that left the disk
  is reported instead of raising mid-turn.

- gate: the undeclared-family refusal has the sentence its register promised (`b7600c11`).
  The denial reason arrived with the family gate and the parity table was never
  given the entry, so the whole-register comparison has been red from the moment
  that commit landed. Nothing noticed, because every test that drives the refusal
  asserts the marker and the code — which the format string supplies regardless of
  the table — and only that one test asks what the model is actually told. It was
  found by the broad selection run, not by a slice. The sentence is the register's
  own text with its wrapper and the standing next-step clause, so the table is a
  transcript of the producer again rather than a second wording.

- lockfile: a rebuild carries the accepted tool pins instead of forgetting them (`d26c1eff`).
  The lockfile builder describes what is on disk and emits no tool field at all,
  so the two release-time rebuild call sites wrote a lock that remembered nothing
  a reader had ever accepted. That silently cleared the mount pin: after any
  marketplace or version change the next mount looked like a first mount, and a
  bundle that had changed its description or parameters mid-air was refused by
  nobody. Measured on this tree as a pinned entry losing its tool array to a bare
  build-and-write round trip. The rebuild now reads the previous lock and carries
  each surviving bundle's pins onto its fresh entry, borrowing only the tool
  field — version, hash, signature and dependencies still come from the disk, so
  a stale lock cannot mask a stale bundle. A bundle the rebuild does not list
  keeps nothing, because it left the disk.

- shell: the workbench is resolved as a window, not as a webview window (`eae937d9`).
  The accessor that returns a webview window answers only while every webview
  attached to the window carries the window's own label, so the moment the browser
  pane attaches its child webview the shell stops finding its own workbench:
  minimize reported a missing main window, hide and show went dead, the Dock reopen
  handler never ran, and the two badge commands were refused at argument
  extraction. One accessor now resolves the workbench as a window and every
  window-level site routes through it — the global shortcut reveal, the five
  window commands, show and hide, the setup clamp and its re-check thread, the
  blur fallback, the tray click, the resize floor and the reopen branch. The Dock
  commands take a window argument, which the platform hands out from the calling
  webview in both states. No retries, no swallowed absence, no per-call-site
  special case; two tests pin the decision, one of them failing if any line
  resolves the workbench through a webview handle again. Live-verified with the
  pane attached, and what that run could not attribute to our code is recorded: a
  visibly miniaturised window still answers the minimized query with false.

- plugins: the countdown icon is drawn on the warm-ink ground (`f028d493`).
  The mark shipped as a bare stroke at 64 px, so the icon constitution caught it:
  no ground, no ink weight, a picture no other plugin wears. Redrawn on the grid
  the constitution uses, with the same rounded ground and inset edge as its
  siblings, the body and crown in the primary ink and the remaining trough in
  signal red, so the wedge rather than the outline carries the meaning at 16 px.
  The drawing test pinned the shipped set at sixteen directories; this is the
  seventeenth first-party entry and the inventory figure moves with it, while the
  four drawing assertions stayed untouched. The catalog was regenerated, since its
  hash is the plugin directory's content.

- store: the pure chat helpers stop booting the catalog (`67a538c5`).
  Thirteen dashboard suites died at import: a component test stubs the i18n
  library with the one hook it uses, and the real module still reached them
  through the chat helpers. The wave that put the composer-mode vocabulary in that
  file made the edge a product edge, not a test artefact. The mock was the wrong
  thing to widen: the file is a table of session shapes and mode names, and only
  its compaction indicator needs a translated string. That indicator moved beside
  the action that writes it, the helpers now import nothing that runs, and no test
  file was touched and no per-file mock added.

- shell: the registered command list reads through its own door (`e7d9d968`).
  The guard that wraps the whole handler list sat between the registration call
  and the list, so the bridge pin that looks for those two side by side stopped
  finding a registration that had not moved — it reported a shell that registers no
  commands for one that registers thirty-one. The list is read, not only run: the
  options module walks it to prove every surface command the door keys on exists,
  and the same walk in Python compares the two sides of the bridge. Naming the
  wrapped registration gives both readers one place to look and the door keeps its
  position. The pin now asserts the door as well as the list, so taking the wrap
  off fails here instead of shipping quietly, and it says so when the walk reads
  only part of the list rather than passing on an empty parse. The surface bridge
  had no pin at all, which is the gap that kept the rename question unanswered;
  both directions were proved by hand against a renamed command and a removed
  wrap.

- shell: the surface door reads the webview, and the window grants nothing (`54f66d24`).
  The caller rule compared the label of the calling window, and a window label
  mis-attributes: the browser pane is attached as a child of main, so a request
  from that webview arrives under main's label. The guard reads the calling
  webview label now, and it wraps the whole registered command list, so a
  command added next week is covered without anyone remembering to guard it.
  The capability file ships an empty permission list because `core:default`
  expands to `core:window:default` and `core:webview:default`, which together
  carry `allow-get-all-windows` and `allow-internal-toggle-devtools` among
  their entries. The documented limit stays honest: the guard covers commands,
  not the event channel, and a `local: true` window still points at a loopback
  http URL. The resize floor and the Dock reopen rule moved to their own file,
  and a window-server failure answers with the curated refusal while the
  engine's own text goes to the log.

- plugin-ui: every path component is refused as a symlink (`2c162621`).
  The asset read decided containment with `realpath`, which follows every link,
  and then opened the file — so an author who swapped a checked directory for a
  link was walked out of it between the check and the read. The read walks the
  same segments itself now: the plugin root opens as a directory descriptor and
  every component after it opens on its parent's descriptor with `O_NOFOLLOW`,
  so a step that is a link dies at that step. The two mechanisms are named
  apart where both live, because they answer different questions. The policy
  assembly became its own responsibility beside the reading, and the surface
  family off loopback rides its own per-client budget: the middleware hands a
  nonce-shaped GET to the route on its shape alone, and a run of guesses used to
  spend the shared budget the whole API depends on.

- plugin-ui: an attacker-authored surface gets an opaque origin (`b4775433`).
  The surface document is served with a sandbox directive that leaves
  `allow-same-origin` out, which is the token that makes its origin opaque, and
  the browser suite measures that per engine instead of assuming it, recording
  an engine it cannot drive as unmeasured. The credential moved from a query
  string to a path segment inside the mount URL, because a browser attaches a
  path prefix to every sub-resource a document derives while a query belongs to
  one URL only: one mint now covers the document and everything it loads, and a
  hand-written request that keeps the credential out of the path arrives with
  none. The module states its own limit where the mechanism lives — an opaque
  origin confines what the document reads and what it may mutate, not the
  request it sends — and #62 bounds that reach.

- composer: a retired mode is retired from the menu, never from its ceiling (`360e6b8c`).
  The load-time migration rewrote the stored retired value onto the Operator tile,
  which widens approvals under three profiles: that mode auto-approves every tool
  whenever the profile is not strict. The clamp built to cover it reacted one step
  too late, because by hydrate time every turn had already run as Operator, and
  its profile write reached the whole device since the endpoint has no session
  scope. Retirement now happens to the tile alone: the stored value keeps its wire
  spelling, resolves to the compatibility name for the edit family, and the
  surfaces call it by its section wording, pinned per profile.

- supply-chain: the engine register probes the crate the wheel embeds (`ae2f1a6d`).
  Every row named the wasmtime-wasi crate, and the audit asks the databases only
  about the package, ecosystem and probe triples written there. The engine that
  executes guest code is the wasmtime crate itself and no line ever named it, so
  an advisory against it could reach this register as nothing. The row for
  RUSTSEC-2026-0379 copies its fix events out of the record, and at the pinned
  version the probe returns zero records: the change adds the question that was
  never asked and claims no live exposure. Verified as every advisory identifier
  resolving, both packages answering with a clean exit, and the supply-chain and
  runtime-floor suites green.

- settings: the Version & Updates row runs the update the header runs (`6dbd1d12`).
  Measured on the served app: the header knew there were new commits on main since
  this build while the Settings row answered with its own heading and nothing
  else. Each surface ran its own instance of the update hook, and an instance kept
  its own state, so the surface that mounted second inherited the live gate the
  first one had closed — it asked no question, held no answer and drew no action,
  and its sheet offered a check again where the header offered the update. The
  machine moved onto the module that already owned its gate: every mount
  subscribes to one state and calls one set of runs, and the two readings a
  surface draws from an answer live beside it, so the row and the header's sheet
  cannot disagree about one answer. Measured live in a throwaway checkout four
  commits behind: one click applied the update and the row read the new commit
  beside it. On a branch checkout the same row states the closure instead of going
  quiet.

- run: the ledger names the session it belongs to and the file it wrote (`c2658b22`).
  The register could not show a chat turn because nothing in the ledger said which
  session a turn ran in, and the phase that promised a path carried only an opaque
  id. Measured on this machine: after a real run that produced a file, the
  workspaces endpoint answered with empty lists — the turn was on disk, unreadable
  as a task. The start line now carries the session, both producers of a file
  frame (the detector over the answer text and the marker table of a tool result)
  write the paths, and the projection is separated from the read so a caller
  holding the lines gets the same view without a second pass over the file. Still
  content-free: a tool, a call id, an argument digest, a duration, a status, a
  failure class, a session and a path.

- api: The `/v1` surface names a refused method (`fcb88daa`). `POST /v1/models` is a wrong verb
  on a path that exists, and it answered `code: not_found` — a client reading that concludes the
  model list has gone. The two doors now agree: a refused verb carries `method_not_allowed`, and
  `not_found` is reserved for the path that is unknown.
- workspaces: The register fills while the turn is still running (`9f73eec2`). Measured on
  the machine that ships Ephe: after a real run that produced a file, `GET /api/workspaces`
  answered `{"workspaces": [], "runs": []}` while the transcript above it showed the file. The
  read stopped at the git-worktree register, which no chat turn writes, and the ledger line
  that would have tied a run to its task carried neither the session nor the path — the
  `changed` phase promised one and held an id. A turn now records its session when it opens
  and its written path when it lands.
- panel: A CSV opens as the table it is, with its bytes beside it (`2df5fb9a`). The workbench
  card has drawn a `.csv` as rows since the server put the suffix in its table kinds, while the
  workspace column asked its own classifier and got a code block of commas. The column now keeps
  both readings the way it keeps a Markdown page and its source — the table asks the server and
  shares the one table renderer, the source stays copyable bytes — and where the server declines,
  the view falls back to those bytes instead of an empty frame.
- cli: A row stops claiming a match it never read (`ec493c65`). With the server stopped, the
  doctor printed `Desktop app — the only bundle for com.ephe.ephe, matching the backend` two
  rows under its own `Ephe server — not running`: an absent answer left the comparison
  unrun, and the sentence went out anyway. The row now names the version it compared when a
  backend answered and says plainly when none did. The same instrument already refuses this
  shape for the bundle registry, and the rule is the same one — a read that failed is said
  out loud.
- api: A refused method now says what it means (`b5d42de1`). `POST /api/file` and `HEAD /api/file` used to answer 405 with the code `not_found` and no `Allow` header — a client reading that concluded the file did not exist, while the path was there and only the verb was refused. The answer now carries its own code `method_not_allowed`, an `Allow` header naming the methods the path actually supports, and a message that tells the caller which verb to retry with. A real 404 keeps answering `not_found`, so the two refusals stay distinguishable.
- settings: Version & Updates runs the update the header runs (`3cc69216`). Two paths to one answer had become two products: the header's three dots named the new commits and offered `Update now`, while Settings - Version & Updates showed its own heading, no version, no distance and a sheet that only knew how to ask again. The page a person reaches when something is wrong now holds the same answer as the header, carries the same `Update now`, and does the same thing with it. Where an update cannot run there the page says why and what to do next — a checkout on another branch, local changes to set aside first, a build installed from a release that updates by replacing the app. Measured live: one click on that row took a checkout from `5823b1c` to `dca40ce` and the row then read `Updated`; the same row on a branch checkout reads `This Ephe runs from a checkout on another branch, so it will not pull the default branch under it.`
- chat: The composer takes one line and the conversation keeps the screen (`9338bec5`). An
  empty box asked for 184 px of a 742 px window: a field two and a half lines tall with the
  controls stacked in two rows under it, so before anyone had written a word there was more
  chrome than conversation. The field now opens at one line and grows to six as the draft
  needs it, the control row keeps every button at its 44 px and fits one line, and the box
  costs 106 px — 14 % of the window. The conversation gains exactly that room: the same chat
  on the same screen measures 78 px taller and shows one message more.

- browser: the pane that shows a web page stops showing anything else (`fc147137`,
  `493f996`). `browser_open` parsed any address it was handed and `on_navigation` answered
  true for every navigation a loaded page asked for, in any frame; measured on the shipped
  engine class, that callback is asked about the main frame, an iframe's own source, and the
  inert documents a page builds for itself. So a page could walk the pane into `file:` and
  read host content through a surface that only meant to show the web. One rule now gates
  both doors: http and https, plus the page's own `about:blank`, `about:srcdoc`, `blob:` and
  `data:` documents. `file:`, `javascript:`, the operating-system handlers, the schemes the
  shell registers itself, and an `http(s)` host that is one of the engine's own `*.localhost`
  origins are refused. A refusal is a code the surface turns into its own sentence with the
  address beside it, and it offers no gesture that would hand the same address to the
  operating system. The bridge strip also moved to the hook that reaches every frame, and the
  read says plainly what it does not achieve: the shell installs `__TAURI_INTERNALS__` as a
  non-writable, non-configurable property, so name deletion cannot remove it in any frame,
  and what confines an invoke is the engine's remote-context rule, the caller guard these
  commands now read, and the scoped channel still to come. `cargo test --lib browser::` 9
  passed / 0 failed; `pnpm exec tsc -b` 0; the dashboard suite 1714 tests passed / 0 failed.

- sandbox: a plugin worker could reach Ephe's own API (`380bb9f0`). A confined plugin tool
  opened a TCP connection to the loopback port this server listens on and read `200` from
  `/api/health` and `/api/memory/list` with no token offered — measured twice, once in the
  research pass and once on the production rail with a backend started by the driving
  process. The boundary held the filesystem tightly (eleven environment names in the child,
  none of them `EPHE_*`; `PermissionError` on the repository, the engine key, the memory
  store and the browser cache) and said nothing at all about sockets, because the profile was
  reused from the connector rail and the HTTP layer trusts a loopback peer. One rule per
  platform closes it for this rail: `(deny network*)` under Seatbelt, `--unshare-net` under
  bubblewrap, asked for only by `sandbox.supervisor.confined_argv`, so an MCP server that
  legitimately is a network client keeps its network. After the change the same child answers
  `PermissionError` and the test's own listener reports it accepted nothing, while the run
  still returns `ok` over stdio. What is still open is the larger half of the door: any local
  process may call the API without a token, and that needs a decision about which callers must
  carry one rather than another rule for children.

- auth: a byte the token comparison cannot read is refused, not a server error (`bf872fe1`).
  `hmac.compare_digest` raises `TypeError` on non-ASCII text, and both of this gate's
  comparisons take their value straight off the wire — the `?token=` a phone gets from the QR
  link, and the same parameter on a WebSocket handshake. One percent-encoded byte therefore
  produced a 500 where the answer is 401, and on the WS path an unhandled exception where the
  answer is a closed handshake. `tokens_match` encodes both sides first; the offered value is
  encoded with replacement on purpose, because a token this server issues is
  `secrets.token_urlsafe` and anything that does not survive a strict encode is not it.
  Proved in both directions: against the previous file the new tests fail with the
  `TypeError` at `server/middleware.py:310`.

- plugins: one unreadable folder no longer takes the Extensions page down (`e7d2cc2a`). A
  plugin directory at mode 000 made `scan_plugins` raise `PermissionError` out of
  `mfile.is_file()`, and the settings route, the store view and the runtime all read that
  scan, so a half-finished install or a volume mounted by another user answered 500. The trap
  is that `Path.is_file()` and `Path.is_dir()` swallow the errors their authors expected and
  let the rest through, so the fix is to ask those questions in a form that answers a boolean
  and to keep the read inside the try it already needed — not a blanket `except Exception`
  around the loop. The error string names the class and carries no host path, because it
  reaches a browser. Measured against the running app: the request that produced the 500 now
  answers 200, and a valid plugin beside the broken one still loads.


## [0.5.7] - 2026-11-03

The folder Ephe writes to now names itself, and every writer answers to it.

The product has said Ephe forgets since the first sentence, and nothing on the machine could show which files actually stay. The device folder carries that list in code now: fifty-seven entries, each saying whether it is a folder, a file or the socket the desktop shell binds, what a person loses with it in plain words, and which file in this tree writes it. `ephe device` reads the declaration — what is present, how much room it takes, and what the folder holds that no row names — and clears it on the word, dry run first, the way `ephe prune` works. The audit log, the cell guest and the signing anchors are marked kept by the declaration itself, and an undeclared leftover is kept too: a verb that deletes files it cannot name would claim more of the folder than the code accounts for.

The other half is what that list made visible. Seven of the ten state accessors the ephemerality contract asks resolved into the real home while `EPHE_CONFIG_DIR` pointed elsewhere, so a run told to keep to itself still wrote the session, the usage ledger, the feedback memory, the profile, the search index and the persona into the owner's folder; twenty-five more sites each carried their own copy of the root's rule, agreeing with the helper on the day they were written and owing that agreement to nothing afterwards. All of it folds onto `config_root()`, and the four expected failures the suite had been carrying as unpaid work are gone. Measured on the machine that ships Ephe: 44 of 57 declared entries present, 2240.9 MB, 6 entries nobody declared.

Two readings travel with them. The column that lists a Word file, a sheet or a deck now opens it: the workbench card has turned those three into a real table, running text and a slide list since R4/A5, and the column asks the same question by path through a new door — with one guard answering both doors, so the two routes cannot disagree about what they will show. And a reload of an open file reaches the server instead of answering from the shell's own cache, which had kept showing the bytes of a document already deleted on disk.


### Added

- core: The device folder declares what it keeps (`079d0f94`). Fifty-seven rows, each naming
  the entry, whether it is a folder, a file or the socket the desktop shell binds, the plain
  words for what a person loses with it, and the file in this tree that writes it. Retention
  has to answer to the same list, a row's writer has to exist, and the code has to reach
  nothing the rows miss — three tests, so the declaration cannot drift from the disk.
  `ephe doctor` renders it as a row that never decides the exit code.
- cli: `ephe device` reads that declaration and clears it (`3ac061aa`). The entries present,
  what each holds, the room between them, and the entries the folder keeps that no row names.
  Dry run first, the way `ephe prune` works: without `--apply` nothing is unlinked. The audit
  log, the cell guest and the signing anchors are marked kept by the declaration, and an
  undeclared leftover is kept too — a verb that deletes files it cannot name would claim more
  of the folder than the code accounts for.
- panel: The column reads the office file it listed (`38e33fde`, `8635f627`). A Word
  document, a spreadsheet and a deck arrived as a name, a size and a download, because no
  browser draws those three as content. The workbench card has turned them into a real table,
  running text and a slide list since R4/A5; the column now asks the same question by path
  through `GET /api/file/preview`, and one guard answers both doors — the streaming route and
  the preview route call the same function for the expansion, the relative resolve, the
  real-path probe, the credential-shaped name and the size ceiling, and a test asks each door
  the same two refusals. Proved against a live server: a sheet came back as its rows with the
  sheet name, a document as its text, `/etc/passwd` as 403, a missing file as 404.


### Fixed

- files: A reload reaches the server instead of answering from the cache (`4aa51a81`). The
  file route sent `ETag` and `Last-Modified` with no `Cache-Control`, so the desktop shell
  answered a re-read of an open file from its own cache by heuristic freshness: a document
  deleted on disk kept showing its old bytes while the same URL had already turned to 404. A
  reload that cannot fail is a reload that did nothing. The route now answers `no-store`, and
  the test writes, rewrites and unlinks the same path across three reads.
- core: Every state writer answers to the device root (`3579e36e`, `e50922dd`). Seven of the
  ten accessors the ephemerality contract asks resolved into the real home while
  `EPHE_CONFIG_DIR` pointed elsewhere, so a run that was told to keep to itself wrote the
  session, the usage ledger, the feedback memory, the profile, the search index and the
  persona into the owner's folder anyway. Twenty-five sites also carried their own copy of
  the root's rule, each agreeing with the helper on the day it was written and owing that
  agreement to nothing afterwards; they are folded onto `config_root()`, and the folder built
  from the home directory now exists in the one file that defines it. Measured on a machine
  that runs Ephe: 44 of 57 declared entries present, 2240.9 MB, 6 entries nobody declared.
- plugins: The code-shell pack says the same thing in all three places (`e4b6e7b1`). Its body
  and its `allowed_tools` named `execute_code` while `tools` — the list the chat turn takes as
  its whitelist — left it out, so `/fix` advertised an instrument it was never offered and a
  boot warning was the only trace. A new test loads every shipped pack and refuses such a
  disagreement; the pack's own gate for that tool is unchanged.


## [0.5.6] - 2026-11-03

The column opens the file you clicked, and the doctor names the app your click reaches.

The workspace tree already listed every file and then handed it to the browser pane, so a README arrived with an address bar and a PNG arrived with a download. One question is asked in one place now, and every format has an answer: the page a Markdown means or the source that made it, highlighted code, plain words, the picture, the player, the frame, the office container named with the gesture that reaches it, and a file nothing can draw described by name and size. Open files sit in a strip of their own with the part of an editor worth keeping — a single click looks, a kept file stays until the person closes it.

The other half of this release is the instrument. The symptom, reported over weeks: "I press Update, it says current, I restart, and nothing is new." Measured: twenty-one bundles answered for `com.ephe.ephe` on the machine that ships Ephe, and a click resolves an identifier rather than a path, so the updater wrote the new version where it always does while the relaunch reached somebody else's copy. `ephe doctor` now names the app it can open, reads the LaunchServices registry rather than the index that cannot see the Trash, says when a read failed instead of claiming a clean machine, and `--fix` forgets the copies that were answering. The pile has a maker: the installer moves the app it replaces into the Trash, and the registry keeps answering for it there.

Two readings travel with them: the shell asks for the update it can actually bring, and the toast rail steps aside when the right column is open.


### Added

- workspace: Every file the column names, the column opens (`d16f66c1`). The tree listed
  the folder and then handed the file to the browser pane, so a README arrived with an
  address bar and a PNG arrived with a download. One question is now asked in one place —
  the plan answers for markdown, source, plain text, pictures, sound, video, PDF, the
  office containers and the file nothing can draw — and the open files sit in a strip of
  their own with a preview slot: a single click looks, a kept file stays until the person
  closes it. The suffix tables moved into one module the workspace column and the artifact
  card both read, instead of two lists that had drifted apart.


### Fixed

- update: The shell names the update instead of a reload that cannot bring it — with the
  new version already written into the `.app`, the toast told the person to reload the
  window, and a reload re-reads the bundle the window is already running from (`3ac7541a`)
- doctor: The report names the app a click opens and every other bundle answering for the
  same identifier. macOS resolves an identifier rather than a path, and twenty-one bundles
  carried `com.ephe.ephe` on the machine that ships Ephe — leftovers of mounted disk images
  and Tauri builds inside worktrees. The updater had written the new version where it always
  does; the relaunch reached one of those other copies, so "updated" and "nothing changed"
  were both true at once, and no surface could see it (`9521e399`, `629e23b5`)
- doctor: The bundle scan reads the LaunchServices registry. The row above asked Spotlight
  instead, and Spotlight does not index `~/.Trash` or `/private/tmp` — the two places old
  copies collect. Measured the same evening on the machine that ships Ephe: the row said
  "the only bundle for com.ephe.ephe" while the registry named seventy-four, seventy-two of
  them in the Trash and one in `/private/tmp`, every one reachable by a click. The dump is
  read as records so an identifier and its path stay paired, a path that no longer exists is
  dropped because it cannot be opened, and the places are counted so seventy-three copies
  read as two folders. A read that fails now says it failed: the first version called a
  helper that used `re` without importing it, the bare `except` swallowed the NameError, and
  the doctor reported a clean machine (`149ddee2`, `7800e7b9`).
- toast: The rail steps aside when the right column is open (`431aef78`). The stack anchors
  top-right and the panel is a fixed column whose tab bar sits at the top of that same edge,
  so every capture of the panel showed the restore message printed over the row of tabs — the
  control the reader needs next, covered by news of something that had already happened. The
  rail reads the panel's own width broadcast and moves to its left edge, and the phone layout
  keeps its centring.
- doctor: `ephe doctor --fix` forgets the desktop bundles a click can reach. The pile has a
  maker: the installer moves the previous `/Applications/Ephe.app` into the Trash, and
  LaunchServices keeps answering for a bundle it has already seen wherever it is moved to, so
  every install adds one more copy the Dock icon can choose — 72 of them measured on the
  machine that ships Ephe. The script now unregisters the copy it trashes, and the repair
  clears a pile already there. Nothing is deleted: the files stay, and a bundle the registry
  forgot comes back with `lsregister -f` (`1301b457`, `a1785b32`).


## [0.5.5] - 2026-11-02

One column on the left, and three instruments that stopped reporting what they do not know.

The frame's rail had a neighbour: the chat's task column, 288 px open and 56 px folded, carrying its own New task and Search beside the places the rail already named. The rail took the two verbs and the column became the body of the rail's Task row — one click opens the register, the next folds it to nothing, and the choice is remembered per person. Measured before: 112 px of chrome stood in front of any content.

The update window rendered the changelog block whole, so the notes of a version ended in `(3614f87a)` — the register's address, read by a person deciding whether to install. The header promised `Checking the engine` on a screen whose strip said `Disconnected`, because the engine is asked through the backend and the backend was the thing that was gone. And a boot whose local cache could not be read skipped both server restores with it and came up saying `No tasks yet` while the machine's own store held the history; the read now has its own failure path.

Three readings from the previous round travel with them: a task row names its last activity rather than its birth, the marketplace's data ships inside the wheel, and the context figure has one home per screen.

### Changed

- shell: The left edge is one icon sidebar. The frame rail took the task column's two frame
  verbs — New task and Search — and the column itself became the body of the rail's Task row:
  one click opens the register, the next folds it to nothing, and the choice is the person's
  from then on. Measured before: 112 px of chrome stood in front of any content, and the same
  two verbs were on the screen twice (`c263c3ab`, `cf7c3f6b`)

### Fixed

- sidebar: A row names the last thing that happened, not the hour the task was opened — a
  session answered at 14:16 and still read `3 hours` (`91473a8e`)
- packaging: The shelf's data travels in the wheel: the marketplace index, the curated tier,
  the revocations and the plugin catalogues, with a guard that refuses a build leaving any of
  them out — a packaged install opened an empty shelf while the checkout the desktop runs from
  looked perfectly fine (`8fe8670d`)
- chat: The context figure is named once per screen — the ring at the send button keeps its
  arc and drops the duplicate name, the status gauge stays the instrument (`9c6d1169`)
- release: The update window's notes are the words of the changelog, without the commit
  address every entry ends with — the register reads a line by its address, the person
  deciding whether to install read a sentence that stopped in hex digits (`2d4080f3`)
- chat: A task list that cannot read its own cache still asks the machine's store —
  a boot came up saying `No tasks yet` while the history sat untouched on the disk,
  because one rejected IndexedDB read skipped both server restores with it (`e662f71b`)
- chat: An engine answer that cannot be read names itself — the header promised
  `Checking the engine` on a screen where the strip said `Disconnected`, because the
  backend that probes the engine was the thing that was gone (`8141f783`)

## [0.5.4] - 2026-11-02

The release that carries its own backend. The desktop updater had been replacing the app
bundle and leaving the Python environment where it was — measured as a 0.5.3 tree running
beside an `ephe-0.5.2` install — so the shell now asks the backend to refresh that
environment, the surface follows it, and the path ends in the restart it leads to. The
shell also writes a run ledger, because four silent exits today left nothing to read. The
side column became one contextual Workbench: a section per kind of thing a task shows, one
icon each, and the icon in front folds the body away. The shelf's marks finally reach both
surfaces, with 132 publishers' own icons behind them and each one's source, date and
digest recorded. The About page opens the sheet it names, and the chrome says the task's
name once.

### Added

- discover: The curated tier carries its publishers' own marks — 132 icons added to the
  fourteen the hero already wore, each fetched from that publisher's domain with the URL, the
  fetch date and the digest recorded in `SOURCES.json` and the brand terms stated in NOTICE
  (`be8b96c6`)

### Fixed

- server: The audio route describes its upload in the shelf language, as every other route in
  the file already did (`86521560`)
- desktop: The update now carries the backend's environment along with the code it moves, names
  which of the three outcomes it reached — refreshed, still running, refused with its reason —
  and ends in a restart the surface offers instead of a sentence about one (`1228a4c6`,
  `dd51da76`, `13b259ea`)
- settings: The Version & Updates page opens the update sheet its own Details button promises;
  measured on the installed app, that click answered with nothing at all (`81094860`)
- desktop: The shell writes a run ledger — `start`, `exit`, `restart requested` — into the file it
  already owns, because a release build registers no logger and two silent exits left nothing to
  read afterwards (`e20b55e3`)
- discover: The shelf asks the backend for its marks instead of the app bundle, so the icons the
  PWA has always shown are no longer missing in the desktop shell — the plates put a
  root-relative `/api/…` in `src`, which resolves in the browser and asks `tauri://localhost`
  for a file it never carried (`3614f87a`)
- packaging: The brand-marks register travels into both shipped copies of NOTICE, so the npm
  package and the app bundle cannot drift from the file in the repository root (`c6f80c93`)
- panel: The side column answers one question now. One icon per section that holds something —
  output, site, console, notes, changes — and only the section in front says its name; the icon
  already in front is the handle that folds the body away (`cf22d029`)
- chat: The chrome names the task once. The heading carries it and is the renameable identity;
  the run line printed the same sentence again beside `Ready` (`e0c547aa`)
- panel: A document the workspace holds loses the browser row around it — name, folder and one
  word for what it is take the place of reload, back, forward and a `%2F` query — and the tab
  stops calling itself Browser while its own tooltip says it renders files and artifacts
  (`476a436f`)

## [0.5.3] - 2026-11-02

The live-verification round on 0.5.2, run the way a person uses the app. Five surfaces that
contradicted themselves are fixed, and each was seen in the running build rather than only in a
test: the shelf labels an author's own language instead of rewriting it, the context figure has
one home per screen, an empty workspace register names the folder the settings answer with, the
composer mode chip says the mode it shows, and every artifact kind the index can store has a word
in both bundles. Two tool rows and the search row's own marker read in the shelf language, the
knowledge sub-pages keep their addresses pinned beside their labels, and the links in the
marketplace, the setup page and the update dialog finally leave the desktop shell — proven by
clicking one and reading the browser's own window title. The changelog addresses a rebase merge
rewrote now move by themselves, agreed by patch id, before the tag is taken.

### Added

- **Self-organised learning.** A turn now has three phases beyond the answer:
  before the first tool call the workspace's manifests become a compact map
  (stack, versions, its own dev/test/build commands, the pins that change how
  they run) under `.ephe/learning/map.json`; a failed tool round is named by
  class — command-not-found, port-in-use, permission-denied, missing module,
  timeout, network, compile error, failing test, missing file — with the
  assumption it broke and the correction that follows, in front of the next
  model call; and a correction that ended the run is written as a readable rule
  to `.ephe/learning/heuristics.md`, where the new inspector in Settings →
  Memory lists it, edits the action and deletes it. The store is a plain text
  file the user owns; the newest rules ride along in the prompt, older ones move
  to `heuristics-archive.md`, and `sol.enabled` turns the whole loop off.

The 0.5.1 surface wave is named below (`cdb26e6`, `b4aacec`, `7ea5684`,
`5ca2ad9`, `c8e9993`, `c9e0ba5`, `6c13716`, `47f4666`, `56226d7`, `4a8583b`,
`934a7b2`, `d967a5f`, `a012491`, `1c1a7b3`, `cf90dd9`): the TUI footer counts
the helpers and reads the audit chain, every tool states whether it runs without
asking, one click at setup picks the engine this computer can hold, the welcome
mission cards start the run, the swarm deck sees its own run, its cards carry
the gate and the steer, an agent's line carries what the engine charged, and the
envelope states what the merge actually read; a state write wakes the live
stream instead of waiting for the tick, the proof ledger opens the payload behind
its line, a refusal arrives with a correction, an artifact adoption lands whole
or not at all, the model matrix shows whether the machine can hold a model, no
text renders below 12 px at any scale, and the Windows caption corner is
reserved where the shell announces it.

The 0.5.1 repair wave is named below (`6e50458`, `2f2d59d`, `c655497`, `1383522`,
`b1edb54`, `295a7b7`, `a32c997`, `1283589`, `19851ea`, `f5e97d2`, `e83e55b`,
`e1d7d5a`, `10642bd`): every Lucide glyph sits on the 1.5 px raster, the fleet and
the cell share one multiplexed stream, the status row keeps one line at every
width, a card's own JSON block is cut from the answer text, DeepSeek DSML tokens
become real tool calls, the child PATH gains the Homebrew binaries, the tool dial
ships 25 rounds with a one-click continuation, the system prompt names the active
workspace, the brand's breathing dot trail is gone from the empty state, and seven
phantom crate versions no longer block a fresh desktop build.

The 0.3.0 typecheck fix is named below (`0486444`): the status bar drops the
CodebaseIndexStatus import it no longer reads, which tsc refused as unused.
The 0.3.0 index-dialog fix is named below (`7214003`): the dialog opens only from
the status pill, so no unsolicited modal covers the workspace on load; the index
routes gain tests for a reentrant job, a raising worker, a vanished span and the
search bound.
The 0.3.0 plan-lookup fix is named below (`ae59b01`): the command body reuses the
Path the workspace listing returned instead of resolving the raw name a second
time, so the request string never becomes a filesystem path in that route.
The 0.3.0 index-scope fix is named below (`b16b7fd`): the index routes take no
directory from the request and cover only the configured workspace, and `/project`
matches its plan name against the workspace listing, so no request string becomes
a filesystem path.
The 0.3.0 security fix is named below (`7826a96`): the py/path-injection markers sit
on the three lines that build the candidate path from the workspace argument, which
is where the analyser anchors them; the containment checks are unchanged.
The 0.3.0 route fix is named below (`5148e27`): `Path` is imported at module scope
for the helper's annotation, and the three resolve sites name the containment check
that lets their value out (`# codeql[py/path-injection]`).
The 0.3.0 UI fix is named below (`426be55`): the index pill reads the declared
`bg-surface-interactive` hover role, and the twelve `codebase.*` leaves move the
locale ceilings by their measured size.
The 0.3.0 changes are named below (`bd27cd6`): a workspace is indexed locally into
SQLite from Python, TypeScript, JavaScript and Rust declarations with ignore rules
and mtime-only re-parsing, a status pill and dialog show the index, `query_codebase`
answers symbol questions with spans and source, any Markdown plan whose phases are
headings and tasks are boxes runs phase by phase with sandbox gates and atomic
markers, the coding loop checks `.ts`/`.tsx` and `.rs` as well, and a failed shell
result names its cause with the next step.

The 0.2.1 fix is named below (`2542d57`): Quick Look opens through
`QLPreviewPanel` in-process, because `qlmanage -p` started a process that opened
no window on macOS 26.
The 0.2.0 changes are named below (`0f7093d`, `1d175b7`, `2761c4a`): Quick Look
and the dock run live in the shell, Apple Vision reads the text off an attached
image on this machine, and a written file is checked in the Seatbelt sandbox
before its result returns, with two repairs per turn before the model has to
report the failure.
The QD-009 changes are named below (`8928483`, `a6ba822`, `bca257a`, `62bed3e`,
`3155870`): the setup screen's repair announcement is reset between cases, so the
gate no longer depends on suite order; the bundle carries its build commit and the
chat compares it with the backend's `/api/health.git_sha`; only `run_shell` may be
taught a remembered command shape, and a bare interpreter is refused; a helper that
was cancelled, or whose process ended, reads as interrupted and ages off the fleet
board instead of showing as live work; copying a code fence writes plain text and
HTML into the native pasteboard, and an artifact row in the desktop shell can
reveal or open its file behind a canonicalized path fence.
The 0.1.12 changes are named below (`1f823cb`, `3374a70`, `105700d`, `8a5d3a6`,
`8935b9f`, `2ec63d4`, `4690a19`, `9fee126`, `80e6590`, `038c1d0`, `15233c1`,
`2ef9745`, `5f1d8a5`, `50bcb8f`, `c4c2fad`): a settings write merges instead of replacing a section
and refuses unknown keys, the co-pilot reads a workspace and can be taught a
command shape, git runs inside the shell sandbox, the installer ships the cell
runtime, and /api/health names the commit the backend runs. Dictation stops on
the second click, records the container the shell can actually record and says
why a transcription failed; the speech-model consent sits in Settings → Audio,
and the voice extra keeps PyAV below the release that broke faster-whisper's
decode. The status bar and the composer's ring read one context number, a replay
card shows its own run, the plan counts a step once and keeps narration out of
its title, an ask payload no longer becomes a `data.json` card, the cell line
says "sandbox off" when no guest can run, the attachment hint names a file once,
typed dashes survive the composer, the companion is visible on the welcome
screen, a scheme-like colon in `EPHE_MOBILE_HOST` is refused, and the updater
manifest names the artifact the bundle writes.
The 0.1.11 changes are named below (`337903e`, `0f02bc6`, `043ee1e`, `976ee78`,
`2aa10a5`, `fef5644`, `38923b9`, `c4550c2`, `5af85c2`, `fb8593e`, `721fe91`,
`3902468`, `ede0927`, `3ad5cd6`, `0968644`).
The 0.1.10 changes are named below (`f16963e`, `278d717`, `7c468f3`,
`e629e6c`, `afadd56`, `0d251e2`, `c9f0591`, `fb85bb9`, `9242ba4`, `38a9640`).
The 0.1.8 fixes are named below (`999d75c`, `ece2522`, `6dce8df`, `c2f49ab`,
and the packaging gate's `6d0d7ba`).
The 0.1.7 changes are on main as `a6c97fc`, `8f86bfe`, `f4415e9`, `6869f8c`,
`7f793d0` and `5d67f19`; the tag names the same work as `a6c97fcb`, `8f86bfec`,
`f4415e9d` and `9f8f4b03`, because v0.1.7 was cut from a rebased copy of main.
The six 0.1.6 fixes are folded into their own section (`408d1e2`, `be4f90f`,
`4c85103`, `c8476be`, `a7930fa`, `86d933b`).
- sol: Name a failed round and keep the rule that ended it (`75e99b8f`)
- ui: The learned rule arrives as a card and lives in settings (`989e8b07`)
- chat: The stream shows the rule the turn proved (`e1030324`)
- chat: The run surface reads as one calm log, and no turn goes silent (`189f755c`)
- capabilities: User-editable tool switches and sub-agent allow-list (#69) (`4c5f8b43`)
- brand: The paper moth as the product mark, cut from the owner reference (#70) (`6c79a287`)
- brand: The moth as a living figure — five states, one glyph, one unfold (#71) (`692c59c2`)
- brand: The seal on a landable change set, the moth on setup (#72) (`a1b702ee`)
- persona: The seed persona states the four rules the product leans on (#73) (`fb62ea2e`)
- tui: The paper moth in braille for the header and the greeting (#74) (`e00e2dee`)
- update: Untagged merges reach the user on every surface (#78) (`1923d68f`)
- companion: The pet goes where the hand puts it (#79) (`6d261775`)
- update: One click takes the merges, not only the releases (#82) (`d6bb1ddd`)
- artifacts: A deck opens in the chat, and the studio plan is written (#83) (`891b4a8b`)
- companion: The paper moth is the default species (`677b1b6c`)
- sol: Count the two runs a rule has to beat (`6722785c`)
- chat: One calm run line and one preview surface (`fa849d88`)
- tools: Start the project's own dev command (`24fe8108`)
- cli: A bare ephe opens the terminal app and the installer leaves a command (`0462557a`)
- sol: Keep a rule only when the next attempt beat the last one (`1c65f53a`)
- update: Let the user choose between releases and every merge (`43a7f4da`)
- settings: Open the active tab's sections beneath its row (`25df732e`)
- update: Name the commit and the channel in the details (`5b618f68`)
- settings: Version & Updates on the About page (`55ad6d77`)
- settings: Give every area the blocks it is built from (`c0e4b163`)
- audit: Per-tool call counts as a read-only route (`739385fb`)
- discover: Put capabilities on a page of their own (`c0041a52`)
- discover: Retire the in-Settings market shelves and their copy (`ab2bf6b9`)
- discover: The breadth door — registry mirror, curated tier, source routes (`36ca2b02`)
- discover: One bootstrap frame for the shelf (Y1) (`59b8ded4`)
- discover: The shelf reads calm and deep (S3 + Y4) (`dd4222ed`)
- discover: Verify before enable, rehearse before download (S4 + Y2) (`8eb9451f`)
- discover: The task word finds the entry (Y3) (`83483e7d`)
- secrets: Type the key where the connector is chosen (Y5) (`e3d7b1c9`)
- settings: Five groups that fold, and a vault you can see (Y6) (`8c31296d`)
- discover: The shelf renews weekly and names its sources (Y7) (`5a28fa3a`)
- discover: The best-liked entries lead, and a pick argues for the shelf (`584c7676`)
- discover: The shelf reads as a store, one subject at a time (`a95d5369`)
- ui: The transcript reads at 16, notices stay off the composer, and the tool catalogue reads in families (`addbbc82`)
- discover: The featured tier lists verified publishers first, with their own icons (`19f74fb9`)
- shell: One frame, one rail, and a tab bar for the phone (`c104eb32`)

### Added

- settings: One glyph per row and one stroke across icons (`3fd47db`)
- composer: Drop the standing sentence above the action row (`001163c`)
- design: Hold the ten colour roles and the 12 px floor as a gate (`4a2bff4`)
- composer: Hold the action row on one line at 390 px (`552271a`)
- composer: Show the context fill in numbers with a compact action (`d6c9c2b`)
- sidebar: Name the four surfaces instead of one catch-all (`a10642e`)
- header: Give the engine state one home in the top bar (`c55028b`)
- header: Fold the run line into the one 40 px chrome row (`c46e3d7`)
- composer: Name the mode chip as the profile it is (`a200ec2`)
- proof: One tool result, two readers (`375d2ce`)
- welcome: Three missions a newcomer can name (`e34b8e3`)
- engine: A model row states what it costs in memory (`f3a0fb7`)
- engine: One matrix row per model, chosen where it is read (`514fb35`)
- settings: State the boundary and the register in behaviour (`07ca34b`)
- swarm: A deck for the helpers instead of a flat feed (`f93926d`)
- artifacts: Adopt from the workbench rail too (`ecedeb2`)
- swarm: Steer a running helper from its card (`7e14d68`)
- custody: Say where the two digests part (`5cfcb60`)
- core: Every sqlite handle waits instead of failing (`685d5a6`)
- custody: The self-signature refusal names itself (`0daed69`)
- approval: Three named actions instead of a checkbox (`0e03f37`)
- swarm: The seal counts the tools the guard grants (`0c1c3ba`)
- chat: The answer carries its earned proof (`26e6858`)
- sidebar: A fresh session says it is ready (`17bd3b0`)
- settings: The type scale becomes a choice, not a constant (`dcee90a`)
- mcp: Each server card states the boundary it runs under (`f4bc4c0`)
- settings: The find gesture filters the register (`4d6b252`)
- shell: The desktop top row keeps clear of its own window buttons (`ee1c266`)
- agents: Import an AGENT.md folder from the agents area (`c90c46f`)
- core: A Merkle certificate for one release or pull request (`fedae28`)
- companion: The countdown is the user's, down to zero (`dd8196c`)
- index: A write refreshes its own file, nothing else (`1fb72b0`)
- custody: One gate for who may sign, one rule for path conflicts (`daea998`)
- shell: The window buttons keep their corner, and give it back in fullscreen (`0517dfa`)
- plugins: Give every first-party plugin its own warm-ink icon (`31e21a7`)
- settings: Audit all four icon maps and render 16px nav glyphs (`e0e8560`)
- marketplace: Guarantee the tile, share the switch and add one-click probes (`c4f7119`)
- skills: Expandable packs, a run chip, a provenance seal and a builder (`7b14585`)

### Fixed

- shell: Drop the header inset the screenshot disproved (`e6faceb`)
- review: The four-eyes refusal answers 422 instead of a 500 (`ca99f5e`)
- proof: Stop printing an exit code no frame carries (`2ba7bac`)
- gate: A role the terminal does not carry is CSS-only, not missing (`f065f05`)
- settings: The behaviour tab survives an answer without a subagent (`ee2f911`)
- shell: The chrome row fits a 320 px phone again (`5d75d4c`)
- build: Budget the chat seed chunk (`d45cd62`)
- ui: The inspector loads as its own chunk, and the locale rows catch up (`03a363e8`)
- settings: An unreadable rule store says so, and the SOL group has a glyph (`53a81a31`)
- intro: The awakened still stands the moth on the drawn stage (#75) (`4adbdc13`)
- chat: One run clock per tool block, not one per family (#77) (`2a1405a8`)
- update: A behind build names its tip and the newest change (#81) (`0117f374`)
- review: The deck opens in the card, and the update route keeps csrf (#84) (`3d51dfe0`)
- update: One product sentence, never git's own words (`3763ba47`)
- settings: Describe the update channel in both languages (`5083a6a9`)
- deps: Move vite to the patched 6.4.5 (`30777a1e`)
- settings: Give the check button a surface, not a hairline edge (`59ccc900`)
- discover: Say what an empty shelf means when nothing was read (`8fa699c2`)
- update: The documented opt-out now closes the door (`5e810320`)
- update: The opt-out stops the fetch, the contract stays identical (`0ced8299`)
- catalog: The mirror filter reuses the language gate's own vocabulary (`db84a46f`)
- discover: Pin the opened door and keep the docs policy (`0c588b0d`)
- marketplace: Confine the source cache path and refuse credential files (`faf9c34c`)
- marketplace: Mark the owner's own index path where the query reads it (`51b39993`)
- ci: Scope the catalog sync's write permission to its job (`bd24ee34`)
- marketplace: Keep a local source index inside the owner's home (`3de9eccd`)
- ci: The sync's token is fenced, and bundled packs keep their own words (`992b8181`)
- settings: The heading folds beside its rows, and the parity walk keeps walking (`d218a918`)
- settings: The phone strip keeps every row, and the groups fold beside them (`1457d88e`)
- settings: The palette's settings row reaches the hub from every page (`8f63c70b`)
- discover: The intent hit lands on its card, not beside it (`1fed1c0c`)
- discover: The card keeps its badge, its provenance and its line (`f43a5ef5`)
- shell: A data route paints its own ground (`8d8a9ca5`)
- discover: The toolbar holds one line down to the tablet width (`221ee5c0`)
- update: The dialog stops offering a pull that cannot run, and stops leaking git (`851abd6e`)
- app: A deploy no longer leaves a dead page, and the model list stops repeating itself (`47b76ee3`)
- update: The continuous channel reads the comparison from the build's side (`9bf110de`)
- ci: The update verb names its tree, and a flaky API no longer reddens the timing report (`769bb9f8`)
- ci: The timing report writes its cause on every path that cannot measure (`e47c21c1`)
- engine: A model switch keeps the endpoint, and a half choice is never written (`eef472f2`)
- tui: The session you come back to is the one you see (`a4cd5f7f`)
- cli: The session list names only what a reader can choose (`af9e48c6`)
- tui: The status row gives up the session before the endpoint (`995a64d3`)
- locales: The German build notice uses no transliterated umlaut (`c321189f`)
- engine: The model chip and the engine page read only this app's own table (`fa55e163`)
- sync: A finished turn reaches the server mirror before the page goes away (`0e6391db`)
- discover: Every card now performs the action it offers (`fc1e83b4`)
- chat: An answer belongs to the task that asked for it (`e85961b1`)
- cli: The doctor's update row names the budget it actually used (`34cb0b0b`)
- workspaces: A row's age names the last activity when the fleet saw one (`74c8b215`)
- surface: Every confirmation names the action it performs (`24859d47`)
- cell: The guest moves to 3.13.18 and is measured on it (`1e75d98b`)
- container: The basis is measured and the builder stops shipping pip 25 (`b3be482c`)
- install: The pip path lands on the patched cell engine (`a112c987`)
- tui: A question the run asks is a card, and its JSON leaves the text (`2f13f123`)
- chat: A stored fact stops reading as a failed tool call (`bfdf94d7`)
- shell: The status row measures the column it is painted in (`babda5f9`)
- shell: The rail owns the places and the register keeps the task (`0b5ae7c5`)
- sidebar: A task row's text stops where its menu button begins (`81440800`)

### Fixed

- discover: The hero plate wears the publisher's own mark, and the one slug rule
  for `/discover/icon/<slug>` moves beside the loaders so a curated row and the
  route answer for the same shape (`8765637c`)
- cli: `ephe doctor` answers its cell line in the report's own language, and a guard pins the
  wording of both branches so a translated string is caught by a test (`b336e116`)

### Security

- deps: minimatch moves to the patched 11.0.3 — the advisory covers `< 11.0.1` and no parent
  release asks for it, so the lockfile lane overrides it and the lint run proves the toolchain
  still matches the same files (`93844868`)

### Added

- hygiene: The gate names the state this product writes itself — a session store, a capture, the
  workbench directory, the config root, and an agent lane's copy of the whole tree (`879d8e99`)
- release: A tool moves the changelog addresses a rebase merge rewrote, and takes a candidate
  only when its diff carries the same patch id (`732c2a0d`)
- knowledge: One document reader covers the paths that read PDF, Word and PowerPoint text, and a
  workbook now comes back as named cell text instead of bytes; a file with nothing extractable
  answers with a warning rather than an exception (`8286fb27`)

### Fixed

- docker: The private-state ignores match at every depth, so a dotenv under `app/` cannot ride
  into the image the way that file's own header says it cannot (`5d2ab908`)
- scripts: The moth generator reaches its source through the home directory, and the published
  tree names no person (`8117ee94`)
- memory: A stored note reads as the markdown it was written in — a table arrives as a
  table, a bold line as bold, and a long path shrinks to the card instead of widening
  it (`441a53b8`)
- status: A refused index read answers idle, so a screen with no workspace stops claiming an
  index failed that never ran (`0057dd56`)
- discover: The shelf keeps each author's own words and labels the language they are in, after
  measuring that 2 of 72 served entries were a user's German and none of the 51 first-party
  packs were (`bfcf49fb`)
- skills: The language labeler reads user text with one quantifier, and a guard refuses a stall
  on four thousand repeated letters (`ea4c0b79`)
- status: The context figure has one home per screen — the row hands the number to the composer
  from `md` up and takes it back below, instead of printing it four times (`105edc18`)
- workspaces: An empty register names the folder the settings answer with, so the page stops
  saying nothing is live while a turn works in a folder (`4adb6f32`)
- chat: A run keeps its break where a tool round ends, so an answer does not arrive as one
  welded sentence in the chat, in the stored message and in the memory note alike (`dd193942`)
- chat: The composer mode chip says the mode it shows — its accessible name no longer answers
  with the security profile, which the chip beside it already owns (`2583811a`)
- artifacts: Every kind the marker table stores has a word in both bundles, so a shelf group
  and its filter chip stop answering MANIFEST, SCORECARD, QA and EVIDENCE_LEDGER over the
  reader's language (`6f907807`, `251213bf`)
- tools: Two first-party rows read their own contract in the shelf language, and the
  poka-yoke pass now runs every tool and parameter sentence through the detector the
  Discover label uses, so a third one cannot arrive quietly (`467234f3`)
- tools: The search row names the marker its own tool writes — the prompt asked the model for
  a `Reichweite:` line that no output has ever carried (`1bfd76b4`)
- app: A blank-target link leaves the desktop shell through the operating system's browser, so
  the eleven addresses across the marketplace detail, the setup page and the update dialog stop
  being text that looks clickable and does nothing (`769f47c4`)

## [0.5.2] - 2026-11-01

The marketplace wave and the live-verification wave together: Discover now leads with the
tools people actually use, shows the publisher's own icon and opens into a product page; the
app gets one frame instead of eight per-page chrome; the sandbox guest and the container basis
move to patched interpreters and are measured rather than assumed; and every surface that asks
the reader to destroy something says what it will do.

### Added

- shell: One frame, one rail across the pages, and a tab bar for the phone (`c104eb32`)
- tui: The run's question becomes an answer card, and its JSON leaves the text (`2f13f123`)
- discover: The curated tier leads the shelf, with the publisher's own icon (`19f74fb9`)
- discover: One product, one row — a second endpoint of the same host folds into it (`19f74fb9`)

### Changed

- surface: Every confirmation carries the verb of the action it performs (`24859d47`)
- workspaces: A row's age names the last activity when the fleet saw one (`74c8b215`)

### Fixed

- chat: An answer belongs to the task that asked for it (`e85961b1`)
- discover: Every card performs the action it offers (`fc1e83b4`)
- sync: A finished turn reaches the server mirror before the page goes away (`0e6391db`)
- cli: The doctor's update row names the budget it actually used (`34cb0b0b`)
- chat: A coded success (`[memory] stored (35 entries)`) no longer paints its tool line
  as failed (`bfdf94d7`)
- shell: The status row sheds its figures by column width, after the frame took 56 px
  from every one of them (`babda5f9`)
- shell: The task register stops repeating the five places the rail carries, and keeps
  them in the phone drawer (`0b5ae7c5`)
- sidebar: The ⋯ button no longer sits over the row it belongs to. Its box reaches 30 px
  into the row and the text column stopped 10 px short of that, so the last 20 px of a title
  — and of a fresh row's label, which also took the base type step — were painted under it
  (`81440800`)

### Security

- cell: The guest moves to CPython 3.13.18 — `tarfile` link hardening, the cookiejar
  `Version` fix and the tempfile cleanup race — built from the signed archive, whose
  sigstore digest was checked against the download, and re-measured on wasmtime 50.0.1
  (`1e75d98b`)
- container: The builder reads its own basis (Python 3.12.16, OpenSSL 3.5.7) and replaces the
  image's pip 25.0.1 with the hash-pinned 26.2.2 before it resolves anything (`b3be482c`)
- install: The pip path restates the wasmtime floor the uv override cannot reach, so the
  sandbox no longer ships the engine RUSTSEC-2026-0352 was filed against (`a112c987`)
- marketplace: The minimatch advisory is a written decision in the register — development
  scope, no fix below 11.0.1, `pnpm audit --prod` as the shipping-scope proof (`b3be482c`)

## [0.5.1] - 2026-10-29

The repair wave from the live session: the status row stops colliding, a card stops
printing its own source, DeepSeek writes tool calls the loop can run, the shell finds
the user's own tools, and a capped turn offers the next ten rounds.

### Added

- **Continue after the budget.** When a turn uses up its tool rounds the server sends
  a `budget` frame with the cap it counted and the ten rounds one click adds; the
  transcript shows a Continue card and the click runs a normal turn with the larger
  budget.
- **Active workspace anchor.** The system prompt names the project (name and absolute
  path) up front, so the model starts in the right tree instead of searching for it.

### Changed

- The generation dial's default is 25 rounds, matching the chat class default.
- An image or link that points at a workspace file resolves through the guarded
  preview route instead of 404ing on the app origin.
- The status row hides its secondary figures in steps (md, lg, xl) instead of wrapping
  to a second line under a squeezed column.

### Fixed

- The status bar no longer paints "pricing not set" over the remaining-token figure.
- An AskUserQuestion or plan block no longer appears as raw JSON above its own card.
- DeepSeek deployments that write DSML tokens into the content now run the tool call
  and stream only the prose.
- A Finder-launched app finds node, npm, git and pnpm again: the child PATH gets the
  Homebrew bin dirs in front, and no inherited entry is dropped.
- The empty state no longer looks like it is loading: the four breathing dots beside
  the brand name are gone.

### Security

- The archive parser is lifted above the zip-cloaking advisory (GHSA-m665-v7pm-7grj):
  `tauri-plugin-updater` moves to 2.14.1 and the resolved `zip` crate from 4.6.1 to
  9.1.3, above the 9.0.5 floor, and the advisory register enforces that floor (`cf344a2`).
- The cell keeps its session workspace locked until its worker has finished, including
  under cancellation and shutdown, so a queued reset cannot erase an active guest's
  files (`a233c71`).

### Changed

- The CI resolvers pin uv 0.13.6 and request CPython 3.13.18 and 3.12.16 in the
  cold-install lane; `.python-version` declares 3.13.18, and the lockfile check reads
  pnpm in the application directory it was given (`db2f752`).

### Fixed

- The `/project/index` accept response samples the job state before its worker thread
  starts, so a small project no longer reports `ready` while it is still indexing
  (`2aa599c`).

## [0.5.0] - 2026-10-28

The market and studio wave: every plugin wears its own icon, the settings screen spends
one glyph per row, and a plugin or skill reaches its example in one click.

### Added

- **Plugin icon constitution.** All 16 first-party plugins carry a hand-built warm-ink
  SVG on the 96 grid (3.5 px stroke), including separate drawings for the two pairs that
  once shared a byte-identical file; `plugins.svg.test.ts` refuses a reused picture or a
  trace of the retired forest palette.
- **Cross-map icon audit.** `auditSettingsIconCollisions` reads the field, type, section
  and generation maps together and reports zero collisions; section headers moved to
  Library, Cable and Wrench, the generation levers to Coins, ListOrdered and
  SlidersHorizontal, and the fallback to Variable.
- **Skills Studio 2.0.** A pack expands from six skills to all of them, every skill
  carries an 18 px family glyph, the trigger is a run chip that opens a fresh chat, and
  the provenance seal shows "verified recipe" with the full content hash one disclosure
  down. A builder card writes a new skill through `POST /api/skills`.
- **Marketplace 2.0.** Every market card draws the shared `PluginIcon` with its monogram
  fallback and the shared `PluginSwitch`; each card and each installed plugin offer a
  one-click example that opens a fresh, disposable chat. The catalog shows the SHA-256
  seal of the index it read.
- **16 px navigation.** Settings search hits and nav rows render 16 px Lucide glyphs on
  the 1.5 px stroke raster.

### Changed

- Every badge on the market and skills surfaces moved from `text-ui-2xs` (11 px) to
  `text-ui-xs` (12 px); numeric chips use tabular figures.
- The locale ceilings take the measured step for the seventeen new leaves in both files.

### Fixed

- A failed market icon no longer disappears: the tile falls back to the plugin monogram.
- A skill pack can no longer hide its seventh skill behind a dead `+N` span.

## [0.4.0] - 2026-10-28

The control wave: the co-pilot's countdown is the user's, a write keeps the codebase
index current, and the surfaces that carry proof state what they actually measured.

### Added

- **Companion countdown as a setting.** `appearance.companion_countdown_seconds`
  (0-10 s, half-second steps) replaces the fixed 2.5 s pause; the studio shows the
  value live, 0 s acts on the next tick, and the co-pilot also offers the codebase
  index when a workspace has none.
- **Incremental re-index on write.** `reindex_single_file` updates the changed file
  after `write_file` / `edit_file` and refuses a path outside the workspace.
- **Proof ledger and approval card.** Each finished turn lists its runs with duration
  and the sha256 of the payload the reader holds; waiting approvals offer allow once,
  remember for the session, and deny.
- **Sandbox strip on every MCP card**, reading platform, file root and net/pid
  sharing from `core/mcp_sandbox.py`.
- **One custody gate.** `evaluateCustodyGate` decides self-signature once, and the
  cross-workspace conflict radar gains the ordered name `detectWorkspaceConflicts`.
- **Type scale 13/14/15 px**, the ⌘F register filter inside settings, a
  fullscreen-aware window-button inset, and the AGENT.md import in the agents area.

### Fixed

- The four-eyes refusal answers 422 with `self_sign_forbidden` instead of a 500.
- The expert sentence under a tool group says `passed` — no frame carries an exit code.
- The Behaviour tab survives a capability answer without a `subagent`.
- The chrome row fits 320 px again (the inset rides the `md:` arm; the run line clips).

## [0.3.0] - 2026-10-28

Phase 1 of the sovereign software factory: the workspace is indexed locally, any
Markdown plan runs phase by phase, and the self-repair loop covers the languages
the shell itself is written in.

### Added

- **Local codebase index.** `core/semindex/` extracts Python (AST), TypeScript,
  JavaScript and Rust declarations into SQLite (`.ephe/index.db`), skips build
  trees and `.gitignore`/`.epheignore` paths, and re-parses only files whose mtime
  changed. `project_map.py` renders a compact architecture summary, `query_codebase`
  answers symbol questions with file, line span and source, and
  `POST /api/project/index`, `GET /api/project/index/status` and
  `POST /api/project/search` are the routes behind the dialog.
- **Indexing dialog and status pill.** The status bar reads
  `Indexiert (N Symbole)` and opens a dialog with the file progress while the index
  builds; an unindexed workspace asks once per session.
- **Generic phase engine.** `core/project_runner.py` runs any Markdown plan whose
  phases are headings (`## Phase 1:`, `## Stage 2`, `## Step 3`, `## Milestone 4`)
  and whose tasks are `- [ ]` boxes: gates run in the Seatbelt, every marker is
  written atomically and line-exact, `[ ]` becomes `[>]`, then `[x]` or `[!]` with a
  failure line, and the macOS dock shows the phase progress. `/project <file>` and
  `ephe project <file>` are the entry points.
- **TypeScript and Rust checks.** Edits to `.ts`/`.tsx` go through esbuild and edits
  to `.rs` through `rustc --emit=metadata`, so the self-repair loop covers the
  languages the desktop shell is written in.
- **Shell diagnosis.** A failed `run_shell` result names a missing package, a missing
  binary, a taken port or a sandbox refusal, and appends the next step.

## [0.2.1] - 2026-10-28

### Fixed
- Quick Look opens through `QLPreviewPanel` instead of `qlmanage -p`: the CLI's
  process started and opened no window on macOS 26. The panel is driven on the
  main thread with the file's URL, and the path still passes the canonicalized
  root fence first (`2542d57`).

## [0.2.0] - 2026-10-28

### Added
- **Quick Look.** An artifact row in the desktop shell previews its file in the
  native panel with the space bar or the eye button. The path passes the same
  canonicalized root fence as every other file verb, and a browser keeps its
  inline preview (`0f7093d`).
- **Dock status.** While a turn streams the dock icon carries the plan's ratio
  as a badge and a progress bar, both cleared when the turn ends
  (`0f7093d`).
- **Apple Vision OCR.** An attached image's text is read by
  `VNRecognizeTextRequest` on the Neural Engine — no tokens, no upload — and
  appended to the outgoing turn as a named block, so a text-only engine still
  knows what a screenshot says (`1d175b7`).
- **Self-repair after an edit.** `write_file` and `edit_file` check the written
  Python, JavaScript or JSON in the Seatbelt sandbox before their result
  returns. A failure comes back with the checker's own output and the directive
  to repair it in the same turn; two repairs per turn, then the model reports
  what still fails (`2761c4a`).

### Changed
- The install URLs and release prose move to `v0.2.0` in all three READMEs and
  the start docs.

## [0.1.13] - 2026-10-27

### Added
- Copying a fenced code block in the desktop app writes `text/plain` and
  `text/html` into the native pasteboard, so a paste into Notes or Mail keeps
  the formatting while a terminal receives clean text. A browser keeps its
  `navigator.clipboard` path, and an older shell falls through to it
  (`62bed3e`).
- Workbench artifact rows in the desktop shell offer **Reveal in Finder** and
  **Open with the default app**. Both commands canonicalize the path and accept
  only a regular file inside the workbench, the configured project or the usual
  save folders; a refusal is one sentence beside the row (`62bed3e`).

### Changed
- The running window knows the commit it was built from: Vite stamps
  `__EPHE_BUILD_SHA__` and the chat compares it with `/api/health.git_sha`, so a
  `dist` older than the tree serving it says so instead of passing for current
  (`8928483`).
- The co-pilot offers "remember this command shape" only for `run_shell` and
  only after a `warn_only` finding; bare interpreters (`sh`, `bash`, `python`,
  `node`, …) can no longer be remembered (`a6ba822`).

### Fixed
- A helper run that stopped no longer reads as running: a snapshot reloaded
  after a restart is `interrupted`, a cancelled helper finishes its own record,
  and the fleet ages a run without a recorded finish off the board. The helper
  directory keeps the history and names the state (`bca257a`).
- The setup screen's repair announcement is reset between test cases and the
  assertion waits for the store, so the release gate no longer depends on suite
  order (`cf07347`).

## [0.1.12] - 2026-10-27

### Added
- The co-pilot reads a workspace: `ls`, `cat`, `head`, `tail`, `wc`, `stat`,
  `du`, `pwd`, `which`, `file`, `rg`, `grep` and `find` without a destructive
  predicate are classified for itself, still behind the forbidden tokens,
  operators and path escapes. A command shape the user vouches for can be
  remembered on the panel (`3374a70`).
- The installer ships the sandbox extra (`ephemora-cell`) and falls back with a
  visible notice when a platform has no wheel for it (`8a5d3a6`).
- `/api/health` names the commit the backend runs, and the desktop installer
  warns when the backend tree lags behind `HEAD` (`8935b9f`).
- Settings → Audio carries the speech-model consent, next to whether the model
  is already on disk (`4690a19`).

### Changed
- A settings write merges into the stored section and refuses unknown section
  or field names with 400 (`1f823cb`).
- The status bar and the composer's ring read one context derivation, so used
  and free keep the same denominator (`038c1d0`).
- The plan block counts a step once, splits a checklist the writer flattened
  onto one line, and titles a narration step by its first sentence (`5f1d8a5`).
- The cell life line says "sandbox off" instead of "0 ms/call · idle" when no
  guest can carry a call (`80e6590`).
- The companion is visible on the welcome screen, and `welcome_only` means the
  welcome screen (`15233c1`).

### Fixed
- Dictation ends on the second click, latches a short tap even when the
  microphone grant arrives late, and records a container the shell can actually
  produce (webm/opus, webm, mp4, ogg, wav). A failed start releases the stream,
  and a refused transcription reaches a toast (`2ec63d4`).
- The voice extra pins PyAV below 19, whose release removed the
  `metadata_errors` argument faster-whisper still passes — a fresh install
  decoded every upload into an error (`4690a19`).
- A replay card shows the steps of its own turn; the trajectory route answers
  newest-first and the card indexed it as if oldest-first (`038c1d0`).
- An echoed `ask_user` payload no longer becomes a `data.json` artifact card
  (`15233c1`).
- The composer hint names an attachment once, and typed dashes survive the
  WebView's substitutions (`15233c1`).
- `EPHE_MOBILE_HOST` written with a scheme-like colon is refused, and a host
  that names its own port keeps it (`9fee126`).
- The updater manifest and both upload paths name the artifact the bundle
  writes (`Ephe_aarch64.app.tar.gz`) (`2ef9745`).

## [0.1.11] - 2026-10-27

### Added
- The setup screen repairs a stored key that belongs to another engine: it
  names the active engine, the engine the key is bound to and where the key
  came from, and offers keep, re-enter the key, pick another engine or cancel.
  A loopback start enters setup mode instead of exiting, and chat answers 409
  until the binding is rewritten (`337903e`, `0f02bc6`).
- The desktop bundle declares the six privacy purposes it can request
  (microphone, Desktop, Documents, Downloads, removable and network volumes),
  and `docs/TCC.md` records the signing identity, the TCC diagnosis and the
  rebuild test (`043ee1e`).
- A boundary test keeps `core/` and `server/` free of AppKit, Cocoa,
  Foundation, Quartz, WebKit, objc and pyobjc imports and dependencies
  (`e0ce875`, `a9392e9`).
- The README contract runs as a CI Gates step and as a dedicated offline job,
  so a stale install tag or a dropped section fails a check (`fef5644`).
- The desktop shell carries the menu bar macOS users look for: Ephe, File, Edit,
  View, Window and Help, with New Session (⌘N), Settings… (⌘,), Check for
  Updates…, Close Window (⌘W), Quit Ephe (⌘Q) and the standard Edit entries. The
  tray menu and the bar share one route table, and the surface answers Settings
  and Documentation (`721fe91`).
- The companion works as a co-pilot over five surface targets: a waiting tool
  approval, an open question, a context past 90 %, files a turn just wrote, and
  a failed call. Three modes choose how much it does (`perch`, `scout`,
  `copilot`), a visible 2.5 s countdown precedes every act it takes by itself,
  Escape or Cancel stops it, and the last ten acts stay readable in its popover
  with the reason each one was taken. Risky commands are never approved for the
  user, and the crawl costs no engine tokens (`3902468`).
- The companion can be summoned from anywhere: the header switch, the
  `/companion` command and ⌘⇧C flip the same register key (`3902468`).

### Fixed
- A key file replaced without re-binding no longer offers "keep the key": that
  repair requires a key whose fingerprint matches `engine.key.binding.json`
  (`976ee78`).
- The e2e boot set closes at the panel-ready boundary, so a polling tick that
  fires while a slow runner reads the DOM no longer counts as a boot request
  (`04048ba`).
- ⌘W and the red button hide the main window instead of destroying it, so a Dock
  click or the tray icon can bring it back; a quit that ends through the run loop
  now stops `caffeinate` too (`721fe91`).
- The timing report reads the workflow matrix before judging a leg, so a dropped
  Python version is named by the offline test that guards it rather than by the
  nightly report that noticed it first (`5af85c2`).
- A co-pilot countdown the user stopped stays stopped: the dismissal is recorded
  against the prompt token it was counting for, so a re-render of the same
  waiting approval cannot offer the act again, while the next run of the same
  command — a new token — is still served (`ede0927`).
- Only `run_shell` can earn an automatic approval now, and a command that names
  an absolute or home path, expands `${VAR}`, or passes a writing or
  reconfiguring flag to an allowlisted program (`--output`, `--config`, `-c`,
  `-o`, `--rootdir`, `--override-ini`) stays a warning (`ede0927`).
- The setup repair becomes a target the companion can actually see: the setup
  screen announces the card while it is up, and pointing at a repair the chat
  cannot show marks the setup intent and takes the user to the screen that can
  (`ede0927`).
- The way out names the way back in: `uninstall.sh` closed with a reinstall URL
  pinned to `v0.1.3`, eight releases behind the product it had just removed, and
  now names the tag this tree ships — the same answer `scripts/readme_check.py`
  gives, so a release bump that forgets the script fails a test (`0968644`).
- A mobile host that names another protocol is refused instead of fetched:
  `EPHE_MOBILE_HOST=ftp://…` or `gopher://…` reached the LAN probe's
  `urlopen` with that scheme, and a scheme without an authority came back as a
  malformed http URL. Only `http` and `https` with a host answer now
  (`0968644`).
- The memory ranking's full-text leg binds its row limit as a parameter rather
  than writing the number into the SQL (`0968644`).

### Changed
- The header perch carries the co-pilot as the composer does — mode row,
  finding, countdown, cancel and receipts — and the loop runs in whichever
  surface the behavior chose, so a prompt is never approved twice and the
  dormant surface no longer sweeps the highlight the live one set (`ede0927`,
  `3ad5cd6`).
- CI: PR-only `cancel-in-progress` across the dual-trigger workflows, bounded
  `verify.yml` timeouts, and a concurrency group on `bench-trend.yml`
  (`2aa10a5`).
- The READMEs and the start docs name `v0.1.11`, drop the stale `v0.1.3`
  prose, document the engine-key binding sidecar, and name the tested Node
  runtime (`38923b9`).
- The README contract reads every release tag named in prose, so a stale
  `v0.1.x` fails the same way a stale install URL does (`c4550c2`).
- CI installs Python 3.13.18 where the interpreter comes from `actions/setup-python`,
  while the matrix keeps naming the leg `py3.13` so the required check names and
  the timing budgets stay what they are (`fb8593e`).
- A fresh install starts without the companion (`appearance.companion_enabled`
  defaults to false), and when it is summoned it parks in the right outer gutter
  instead of leaning into the reading column while the engine writes
  (`3902468`).

## [0.1.10] - 2026-10-26

### Added
- An attachment picked through the desktop's native dialog arrives as a data
  URL or text and never as a path, so the composer shows its thumbnail, its
  name and its lightbox again (`0d251e2`, `c9f0591`).
- A release gate refuses a tag that does not sit on `main`: every `v*` tag is
  checked for ancestry against the trunk, and the pre-publication tags that
  cannot carry one are recorded in a baseline (`e629e6c`, `afadd56`,
  `fb85bb9`).

### Fixed
- The desktop version check waits for a cold backend instead of reading
  "unknown" from its first empty answer, and the refresh runs off the UI thread
  with an 8 s deadline (`f16963e`, `278d717`).
- The e2e boot set counts the health heartbeat once, so a late poll no longer
  reads as a second boot request (`9242ba4`).
- The provenance gate answers "cannot decide" in a shallow checkout instead of
  reading older tags as diverged, and the release test gate fetches the full
  history (`38a9640`). The v0.1.9 run failed on exactly that shallow read.

### Changed
- The Rust shell job bounds each apt acquire and retries the install once,
  instead of hanging for up to 19 minutes on an unresponsive mirror (`7c468f3`).

## [0.1.9] - 2026-10-26

Tagged on `main` as `4c76d46` and never published: its release test gate
checked out a shallow clone, read every older tag as diverged and failed the
suite, so no artifact was served. The work above ships in 0.1.10 with that gate
fixed (`38a9640`).

## [0.1.8] - 2026-10-26

### Fixed
- After the desktop app itself is replaced, the shell compares its own version
  with the backend's, updates the backend along the root this machine
  configured, and re-reads it. A version that still differs is named with both
  figures, so the two halves cannot sit on different releases unnoticed
  (`999d75c`, `ece2522`).
- A `tool_done` frame that names no call id keeps its result and its reader
  reason, so a failed tool shows its reason line again (`c2f49ab`).

## [0.1.7] - 2026-10-26

### Fixed
- `fetch_url` returns the page text and no longer answers a prompt through a
  local model, so a hosted engine no longer fails a fetch behind a card that
  said Completed (`a6c97fcb`).
- A tool call the backend marks failed is shown as Failed with its reason; an
  approval refusal keeps `denied`, and the card no longer turns one into the
  other (`8f86bfec`).
- Tool names and statuses wrap instead of clipping, and the family hint lives
  in the card body instead of a hover popup over it (`8f86bfec`).
- An attached image shows a thumbnail that opens a lightbox; text and binary
  files show their name and size, removal names the file, and a file that is
  being read or cannot be read says so (`8f86bfec`).
- Fetch failures and refusals carry reader codes in both languages, and the
  English line of every code is the engine-facing entry (`f4415e9d`).

### Security
- The `pnpm` pin moves to 11.11.0 (`GHSA-vx52-2968-3vc6` covers 11.10.0). The
  lockfile is byte-identical after `pnpm install --frozen-lockfile`, the audit
  answers "No known vulnerabilities found", and `lockfile_check.py` passes.
- The advisory note for `zip` now states what was measured: the macOS and Linux
  targets do not carry the crate, the Windows target does, and no Windows asset
  has been published. The three RustSec lines and their recheck date stand.

## [0.1.6] - 2026-10-25

### Fixed
- On macOS the header menu no longer offers minimize and maximize over the
  native traffic lights, so the window has exactly one button group; the
  Windows and Linux menus are unchanged (`408d1e2`).
- A restored transcript with no messages no longer appears as a sidebar row
  (`be4f90f`).
- A stored assistant row that opens with the working-memory preamble is shown
  as context; it can no longer read as an answer (`4c85103`).
- The side conversation has one name in each language: `Seitengespräch` in
  German, `Side conversation` in English (`c8476be`).
- The setup page announces progress in a status region and failures in an
  alert region; the tools page labels its fields visibly and announces results.
  Both pages carry axe checks (`a7930fa`).
- A skill that can write files now declares a read tool: `api-tester` gains
  `read_file`, and a contract test holds every skill to the rule (`86d933b`).

## [0.1.5] - 2026-10-25

### Fixed
- A turn whose stream loses its terminal frame keeps its partial answer, names
  a stable reason code, and the next message goes out without a reload.
- The artifact route serves the screenshots the product writes under
  `~/.ephe/sessions/images`; a file card that cannot render names the concrete
  cause and states it once.
- The run ledger writes one terminal line per turn, carrying the failure class
  when the turn failed.
- The "Set up engine" action no longer appears on a turn that failed after the
  engine answered; the composer chip already offers setup when no engine is
  configured.

All four in `cbd5e7e`.

## [0.1.4] - 2026-10-25

### Added
- Chat artifacts render inline: images with a lightbox, PDF in a frame, video and
  audio with controls, tables and Mermaid fences, and a file card for the rest.
  A missing image now says so and offers a retry instead of leaving alt text.
- A running turn reports its tool, round and search query, with a heartbeat;
  the search call is bounded to four calls or 60 s and ends with an answer.
- The marketplace card carries the on/off switch. A package that needs consent
  shows one inline consent block instead of a modal.
- A remote image in an answer is fetched through the guarded proxy and stored.

### Security
- The artifact route refuses deny roots and credential-shaped names, decides
  inline media from an allowlist and supports range requests.
- Skill archive paths go through `path_guard.within` instead of a string prefix.

### Fixed
- The hosted macOS runner's uv interpreter is recognised under the Seatbelt
  profile, and `ephe_cli.py` reaches its coverage floor; the PR gate no longer
  skips the required macOS check.
- A failed search reaches the engine fenced as untrusted data like a successful
  one, and an all-refused search is reported as a failure instead of "No results
  found".
- The cask, scoop and npm manifests name 0.1.4, so the release gate judges them
  against the release it ships.
- `generate_image` and `take_screenshot` say when they produced nothing, so the
  answer cannot claim an image the turn never registered.

### Removed
- `plugin_store.install_package` and its tests; the live path is
  `plugin_install._safe_extract`.

### Dependencies
- lucide-react 1.60, framer-motion 14.5.

## [0.1.3] - 2026-10-22

The marketplace and its Extension Center, on top of the 0.1.2 security and
interpreter fixes.

### Added
- Marketplace v2: a canonical bundled index of the first-party plugins, local
  and signed HTTPS sources, exact-version resolution, compatibility and
  revocation checks, and a plan that pins version, hash, trust and the
  permission delta before anything is downloaded.
- Install, update, rollback and remove with a one-slot previous version. An
  update keeps the switch state, a rollback restores the previous version and
  its state, and enabled dependents block a removal.
- The Extension Center: Installed, Discover and Updates views, source
  management, signed/unsigned/bundled trust states, plugin detail, and an
  explicit review for an unsigned artifact or a permission-adding update.
- Local Agent Center and Agent Teams: per-agent model, read-only tool grants,
  instructions and limits; one leader with up to four members, four
  orchestration modes, budgets and cancellation.
- Route-backed settings (`#/settings/<section>`) and desktop window-state
  persistence.

### Security
- A remote index needs a trusted signature, a remote artifact needs a signed
  directory, an unsigned local artifact needs explicit trust, and a revoked
  version is refused at install, update and enable time.
- Remote index and artifact fetches pin the checked public address, keep the
  host in the TLS SNI, refuse redirects and trust no proxy environment.
- Closed local web-surface issues: foreign-origin terminal access, file-route
  access to protected credential paths, child-process credential inheritance,
  and lifecycle state write failures.

## [0.1.2] - 2026-10-22

A security and interpreter release.

### Changed
- Python 3.10 is no longer supported; `requires-python` is `>=3.11`.
- wasmtime moves to 48.0.0.

### Added
- The plugin platform: registry, lifecycle state machine, switch contract,
  signature, package, dependency, secret, network-guard and audit gates.
- The CPython WASI guest and the cell runtime with fuel, memory, disk and
  network limits.

### Security
- Dependency and TLS updates close the open audit advisories for this line.
- A signed artifact older than the installed one is refused instead of
  replacing it.
- The interactive terminal, file routes, child-process environment and plugin
  state writes were hardened.

Earlier release notes are available in the GitHub release history.
