# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

The 0.5.2 wave is named below (`bcede857`, `256d626d`, `d66fb9ca`, `5428e1df`, `0f7110f9`,
`d8dee2ae`, `29016b21`, `2c698aff`, `d52669dc`): the terminal answers a question instead of
printing it, every
confirmation carries its verb, a workspace row tells when the work last moved, the app gets
one frame and one rail, the cell guest moves to a patched interpreter and is measured on it,
the container basis is read instead of assumed, and the pip install path lands on the patched
engine.

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
`7f793d0` and `5d67f19`; the tag names the same work as `a02adcf`, `b831014`,
`36640f5` and `8e0b7a1`, because v0.1.7 was cut from a rebased copy of main.
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
- shell: One frame, one rail, and a tab bar for the phone (`29016b21`)

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
- workspaces: A row's age names the last activity when the fleet saw one (`bcede857`)
- surface: Every confirmation names the action it performs (`256d626d`)
- cell: The guest moves to 3.13.18 and is measured on it (`d66fb9ca`)
- container: The basis is measured and the builder stops shipping pip 25 (`5428e1df`)
- install: The pip path lands on the patched cell engine (`0f7110f9`)
- tui: A question the run asks is a card, and its JSON leaves the text (`d8dee2ae`)
- chat: A stored fact stops reading as a failed tool call (`2c698aff`)
- shell: The status row measures the column it is painted in (`d52669dc`)

## [0.5.2] - 2026-11-01

The marketplace wave and the live-verification wave together: Discover now leads with the
tools people actually use, shows the publisher's own icon and opens into a product page; the
app gets one frame instead of eight per-page chrome; the sandbox guest and the container basis
move to patched interpreters and are measured rather than assumed; and every surface that asks
the reader to destroy something says what it will do.

### Added

- shell: One frame, one rail across the pages, and a tab bar for the phone (`29016b21`)
- tui: The run's question becomes an answer card, and its JSON leaves the text (`d8dee2ae`)
- discover: The curated tier leads the shelf, with the publisher's own icon (`19f74fb9`)
- discover: One product, one row — a second endpoint of the same host folds into it (`19f74fb9`)

### Changed

- surface: Every confirmation carries the verb of the action it performs (`256d626d`)
- workspaces: A row's age names the last activity when the fleet saw one (`bcede857`)

### Fixed

- chat: An answer belongs to the task that asked for it (`e85961b1`)
- discover: Every card performs the action it offers (`fc1e83b4`)
- sync: A finished turn reaches the server mirror before the page goes away (`0e6391db`)
- cli: The doctor's update row names the budget it actually used (`34cb0b0b`)
- chat: A coded success (`[memory] stored (35 entries)`) no longer paints its tool line
  as failed (`2c698aff`)
- shell: The status row sheds its figures by column width, after the frame took 56 px
  from every one of them (`d52669dc`)

### Security

- cell: The guest moves to CPython 3.13.18 — `tarfile` link hardening, the cookiejar
  `Version` fix and the tempfile cleanup race — built from the signed archive, whose
  sigstore digest was checked against the download, and re-measured on wasmtime 50.0.1
  (`d66fb9ca`)
- container: The builder reads its own basis (Python 3.12.16, OpenSSL 3.5.7) and replaces the
  image's pip 25.0.1 with the hash-pinned 26.2.2 before it resolves anything (`5428e1df`)
- install: The pip path restates the wasmtime floor the uv override cannot reach, so the
  sandbox no longer ships the engine RUSTSEC-2026-0352 was filed against (`0f7110f9`)
- marketplace: The minimatch advisory is a written decision in the register — development
  scope, no fix below 11.0.1, `pnpm audit --prod` as the shipping-scope proof (`5428e1df`)

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
  said Completed (`a02adcf`).
- A tool call the backend marks failed is shown as Failed with its reason; an
  approval refusal keeps `denied`, and the card no longer turns one into the
  other (`b831014`).
- Tool names and statuses wrap instead of clipping, and the family hint lives
  in the card body instead of a hover popup over it (`b831014`).
- An attached image shows a thumbnail that opens a lightbox; text and binary
  files show their name and size, removal names the file, and a file that is
  being read or cannot be read says so (`b831014`).
- Fetch failures and refusals carry reader codes in both languages, and the
  English line of every code is the engine-facing entry (`36640f5`).

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
