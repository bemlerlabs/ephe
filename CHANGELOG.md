# Changelog

All notable changes to **Ephe** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)  
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

> All entries are written in English, the project's documentation language.
> Translated content keeps its version numbers, dates and measured claims.

---

## [Unreleased]

### Added
- `create_xlsx` writes real Excel formulas through a safe `=` allowlist, infers
  percent/currency/ISO-date/number formats, and adds auto-filter, zebra rows and a
  styled total row; `create_diagram` and `generate_chart` take `theme="light"|"dark"`
  with exact palettes and grouped-bar/line series, and charts embed into PDFs as
  vectors instead of raster captures (#20, #23).
- Deck composition is fully dynamic: `default_storyline(title, audience, thesis,
  source_status, source_notes)` derives eleven topic-specific slides and `parse_slides`
  carries source notes through to the deck spec, with no canned narrative (#21).
- `evaluate_quality(question=...)` verifies multi-file arithmetic against tool output:
  a compute question without a successful evidence tool is a hard issue, and claimed
  totals must match the computed stdout (#17).
- A routing gate asserts every skill pack declares at least two `when_to_use` and two
  `when_not_to_use` terms, and three packs gained the missing veto terms (#22).
- `README.zh-CN.md` and `README.es.md` reach full section parity with the English
  README, with commands, paths and product names unchanged (#18).
- The desktop window carries a real macOS `NSVisualEffectView`
  (`macos-private-api`, `transparent` + `windowEffects.underWindowBackground`,
  `trafficLightPosition {16,18}`), and the WebView carrier turns translucent only
  under `html.tauri-vibrancy`, so the browser keeps its opaque forest ground
  (`00431f81`).
- The dashboard reads as three zones — a 44px studio topbar with a draggable centre
  and a traffic-light clearance over the sidebar rail, a centred 48rem reading stage,
  and a floating composer dock with a bottom veil; tool calls collapse to a one-line
  pill with a leading status mark and a run-time read, and the assistant answer drops
  its outer card for the full reading width (`00431f81`).
- The first open cuts five camera setups — wide establishing, low stream track, the
  close-up with two heartbeats and the firefly spiral, the shrinking vortex frame and
  the macro portrait — and the rendered film carries a deterministic 48 kHz stereo
  score as AAC and Opus (`c53f7a63`).
- The companion outlives the onboarding: the live actor `c53f7a63` sits in the welcome hero
  and above the composer, with five settings (enabled, form, behaviour, sound, size),
  a click-flight wing flutter, a D-pentatonic spark burst and blinking eyes.
- The sprite extraction uses real alpha matting: `binary_fill_holes` on the Vision mask,
  `distance_transform_edt` background estimation and foreground colour decontamination
  write 2120 × 1504 Retina layers with premultiplied Lanczos-4 upscale (`d0feafe3`).

- The onboarding carries the live guide: a 60 fps spring-flown bee that follows the
  pointer with its pupils, flies to a click or a control, flaps in 3-D and performs the
  finale into the header (`72118913`).
- The first open is a live 60 fps choreography on the clearing keyframe: a spark falls
  into the moss, runs a spline over the stream, spins into a fire tornado and becomes the
  bee while her wings open and a honeycomb shockwave leaves the vortex; the same
  component renders the 12.8 s MP4/WebM through a frame-exact seek (`81566049`).
- The guide and the intro carry the actor cut again from the awakening frame: both eyes
  sharp, no seam across the belly, wing layers with no cheek or belly pixels, and the
  forehead flame back in the actor, the large icons and its own animated layer
  (`81566049`).
- The tour keeps the keyframe stage, shows the engine-core frame in step 2 and the finale
  frame before the workspace; the guard step previews a real approval card; the first
  answer recommends the matching starter card (`b2a404bd`).
- The runtime trust layer: protected roots are refused before any dialog, a
  credential-shaped file needs approval even for a read tool, redaction runs before the
  model context, the SSE stream, the run ledger and the audit log, and every tool result
  carries the call id it answers (`614645c9`).
- Every run writes an append-only JSONL ledger with the five-phase projection
  (`Now`, `Waiting`, `Changed`, `Result`, `Next`); `/api/health` names the instance, pid,
  root, version, contract and owner, and the desktop shell adopts only a backend it
  started (`614645c9`).
- Settings → Session store offers **Delete all chats**: one confirmed gesture clears the
  backend store and the browser's copy (`f52fa12d`).
- setup: Say which key answered an engine probe (`315e94c2`)
- engine: Carry what an endpoint said about each of its models (`7896500f`)
- engine: One searchable model picker, and setup is its first host (`42c57562`)
- engine: The picker takes its two remaining hosts, and setup keeps its own choice (`1f05377f`)
- engine: The hero where the contract puts it, the setup plates where a reader needs them, and an engine that answers without tools (`215bda6f`)
- composer: The chip menu is the shared picker's third host (`48f1bfd8`)
- instructions: The words that steer Ephe are visible, bounded and reviewable (`aef59944`)

### Changed
- The app adopts the npm minor/patch group: Radix primitives, TanStack Virtual, the
  Tauri plugins and CLI, i18next, PostCSS, Prettier and typescript-eslint move within
  their major lines, and the lockfile is refreshed.
- The fire-spirit bee is a 3D volume rig: a sphere head with rim light and warm bounce,
  a fur collar, a lantern belly with honey cells and three chitin bands, four independent
  wing groups, an amber iris with pupil tracking and the v2 crown on the small cut; every
  icon and Tauri bundle is regenerated from it (`72118913`, `2ab2a4fc`).
- The live guide is the cut-out 3D actor from the hero keyframe, with two wing layers
  turning on their shoulder origins; it perches left of the panel, holds a clicked
  control for 1.35 s, hovers at its anchor and leaves a continuous trail, and the large
  icons render from the same sprite (`d009f25d`).
- The task dock sits at the bottom-right of the chat column, where there is room; on a
  failed turn the header reads "Stopped with an error" instead of a worked-for time, and
  the restore notice is one toast that updates in place and auto-dismisses (`f52fa12d`).
- A first start without a stored language follows the browser's language (`f52fa12d`).
- The tour's primary button, selected card and switch use the bee's honey gold instead of
  the coral brand pair, with dark ink on the button (`81566049`).

### Fixed
- `tests/test_tui_context_meter.py` pins `EPHE_TOKEN_COUNTER=calibrated` and resets the
  tokenizer cache per test, so an installed tiktoken no longer changes the fixture
  counts; `skills-lock.json` follows the three metadata edits.
- The intro and tour resolve only defined tokens, with 44 px coarse-pointer floors, and a
  failed language chunk keeps the boot catalog readable instead of painting key paths
  (`8c434261`).
- The welcome sentence stays beside the new recommendation, and the small bee cut carries
  the v2 crown so the 32 px icon paints the brand red (`9033eb21`, `2ab2a4fc`).
- Leaving the tour without an engine records the setup skip, and the carry step's footer
  advances without an import (`b2a404bd`).
- A first start with an empty local store follows the browser's language *and* bundles
  that catalog as the fallback, so a German webview no longer paints key paths
  (`dfe6e883`).
- The header and overflow E2E specs follow the compact header, and the port-hygiene
  register names the shifted line (`f9281f89`).
- Redaction preserves a gate denial's code, the stricter tool wire accepts every fixture
  id, and the SEC-1 credential corpus is an allowlisted synthetic fixture (`757a685a`).
- The engine error box offers "Set up engine" beside Retry and renders known connection
  failures in the UI language; the error stays on the turn through a reload (`f52fa12d`).
- Audit round: the setup offer starts in capitals, the replay frame localizes its step
  count, the empty workbench says its sentence once, the output-directory hint reads
  "where the file is created first", and Custom Ollama follows the app's vocabulary
  (`f52fa12d`).
- The import route accepts no filesystem path: the native picker records the chosen
  folder behind a one-time token, the route imports only that selection, and a missing,
  expired or reused token is refused (`d72e0d43`). Closes CodeQL alert #12
  (`py/path-injection`).
- The mobile sweep's twelve target and input defects are fixed: every measured control
  reaches 44 px on a coarse pointer and every input 16 px, with the desktop probe
  unchanged (`d9f13df7`).
- The first-open locale keys fit their weight budget, the German surface allows the
  loanword Skills, the tour stylesheet reads only defined tokens, and the frozen API
  contract names the tour and import routes (`f80273b4`).
- The shell stops its backend before an in-app update relaunches it, so the new
  version does not inherit the old Python process (`57b6ed14`).
- The published tree carries the bee generator the in-app mark imports, and the
  compact band is the bee's flat cut (`a983f037`).
- The in-app mark is the bee: the chat welcome, the setup screen and the sidebar
  inline the same figure as the app icon and the first-open scene (`2de03359`).
- The desktop update compares the running bundle's version with the release, so a backend
  from another checkout cannot answer for the shell; the dialog shows the release notes
  without a fold and a small ember while the bundle transfers (`afc28891`).
- `uvicorn[standard]` is declared, so a fresh install ships a WebSocket server: the terminal
  pane and the HMR tunnel connect instead of being refused (`pyproject.toml`, commit `eb48c7e0`).
- The desktop publish names its author, so a runner with no git config can publish a change
  set (`core/atomic_publish.py`).
- The task store resolves through the config root, so an isolated run stops reading the
  owner's task ledger (`core/tasks.py`).
- `install.sh`'s error trap uses `${#BASH_LINENO[@]}`, which bash 4 and 5 accept
  (`install.sh`).
- hygiene: Prune verb, ALLOWED_ROOTS, provenance, workspaces cap, db import, trajectory window (`2d1bb8ca`)
- embedder: Fetch the fp16 weights and feed empty modality slots (text-only) (`2b252d54`)
- ci: The advisory probe survives an empty ignore-flag set (`29c65d85`)
- ci: The tests leg activates the pinned pnpm; the arch baseline follows the tree (`e6b13f46`)
- arch: Keep verify_tools.py under the 400-line wall (`b5011732`)
- ci: Restore the arch baseline freeze and cover the prune decline branch (`536e6cbd`)
- ci: The installer trap, the managed root, the guard's argv read and the hint query hold on linux too (`03b3a3a8`)
- publish: Commit-tree names its author, so a runner without a git config can publish (`b9effebb`)
- hooks: A declared deletion no longer ends the pre-commit hook in silence (`d9dca03b`)
- ui: The terminal wears the product's palette, and the claims say what the product does (`975de3e1`)
- ci: The release pipeline pinned an action commit that does not exist (`81e441a8`)
- update: A beta can be offered an update, and a click asks the feed live (`8c7a7d14`)
- desktop: The updater flag belongs to the release build, not to every build (`98d678cd`)
- brand: The mark reaches its colour by role, and the gate can reach the mark (`54e06417`)
- brand: The ears are leaves, and the geometry test reads them instead of naming them (`2ca741dd`)
- i18n: The engine and key hints state the behaviour instead of promising an absence (`65ba8e0d`)
- cn: A type step survives the merge, by rule rather than by a list of names (`d0a72872`)
- theme: Open on the forest, because the paper register was rejected as the product's face (`ad4d4694`)
- ci: The two legs that were red on the public mirror (`ff6ce8e7`)
- licence: The claims match the licence, and the copies that ship follow it (`baf7af5e`)
- licence: The notice is accurate, the installer says what it installed, the grant is signed (`53520bab`)
- licence: The Additional Use Grant is None, and every sentence that promised production use now tells the truth (`e748c600`)
- engine: A tool block is never cut in half, so a long run stops being refused (`e17ba89d`)
- licence: The licensor is Bemler Labs, with no legal form and the mailbox the owner gave (`9d2cf1bc`)
- ci: A token lands with its consumer, and these ten had not (`6bd166b2`)
- ci: The verify job activates pnpm before it asks setup-node to cache pnpm (`798049ca`)
- engine: The key file's rename is observable on every Python (`7a9db58f`)
- e2e: The onboarding helper clears the first-run flag too (`a5660ffa`)
- ci: The export sheds only what the target's own index carried (`b3fca7c8`)
- e2e: The frame budget carries the host's own noise (`8af1f3d3`)
- docs,cli: The project says what it is (`921d26d7`)
- docs,ci: Comments that describe a repository the reader is not in (`407409a0`)
- test: The symlink-loop case pins the invariant, not macOS's answer to it (`1acf857c`)
- ci: The export takes its file list from HEAD, like its contents (`8f72db94`)
- release: The updater-manifest switch uses the input the action still has (`e85fc8a8`)
- setup: The engine screen chooses nothing for the user (`a19dc77b`)
- dist: The package surfaces point at the release that exists (`a0604f59`)
- dist: The npm scope is the org that exists (`2ff5722e`)
- docs: The two gates the audit found red (`928b49c8`)
- public-surface: The private material the shipped pages carried (`7aa11022`)
- docs: The README token the command parser read as a subcommand (`e529d807`)
- public-surface: A sibling tool's name out of two shipped dashboard tests (`d8ecc33a`)
- publish: The exclusion list is enforced, and a reference is judged where it acts (`9b14ef58`)
- publish: The ignore traps, and the guard that names them (`ab466305`)
- publish: The registers the published gates read stay in the publication (`8ebbb0e9`)
- publish: The published suite passes on the tree it is published with (`545cc19c`)
- publish: The lint exclude holds where the tree carries its own policy (`e45d5c1b`)
- publish: The marker the lint guard asks for is named on purpose (`dc9d4786`)
- tests: The two suites the publication made red (`917aa82d`)
- engine: A tool result answers the call the engine issued (`faf987f8`)
- packaging: Point the templates at the published beta.9 assets (`1734b9d8`)
- design: Put a control's edge on the control token (`f57fcd10`)
- setup: Read the given probe key off one stripped value (`0ba0f2be`)
- settings: A partial answer is a state, and the tab keeps its state (`44e9b698`)
- design: Put the boundary token on every edge the sweep still measured (`26f47056`)
- design: Set accent text in the step the sheet already calls AA on paper (`1cd1c3fb`)
- design: Put the status badge and the setup hints on an ink paper supports (`8460b467`)
- design: Bend the paper warning tone to the floor the contract already asks for (`ccc02129`)
- design: The two memory buttons the sweep measured last (`2b470919`)
- build: The entry stylesheet carries the picker now, and the row says so (`c785d2ca`)
- evidence: The capture driver reads the Playwright this tree installs (`e890c1cb`)
- engine: The refusal OpenRouter sends is a refusal of the tool array (`5a865bba`)
- chat: The model line stops printing an empty pair (`ce503c14`)
- packaging: The scoop notes name the release their hash belongs to (`de1c4728`)

### Changed
- The permanent toolbar row is now a task dock at the bottom-left: it appears once a
  session has messages and there are several tasks, a plan or a git project, and shows
  the tasks, the plan steps, the branch and the four panel destinations; it collapses to
  a pill and can be dismissed for the session (`86b2abf9`). Below 1024px it starts as the
  pill, and a collapsed or opened choice survives a task switch (`c3f94ed4`). The dock
  floats over the transcript instead of across the composer (`d9727166`).
- The chat header keeps identity, the panel toggle and one named overflow; New Session,
  navigation, update, theme, shortcuts, the library and the window controls live in the
  menu, and the header identity draws the bee (`18e0acd6`).
- The welcome screen names one engine condition — ready, unreachable, key-refused or
  no-model — and offers the matching next step, with a retry for an unreachable engine
  (`84957d58`).
- Workspace rows read state, task, the why drawn from the payload's own waiting and
  last-event fields, one next action, the change summary and labelled clocks; change sets
  lead with outcome and approval condition before files and digests (`a16074fd`).
- README.md is a 255-line front page; the reference material moved into `docs/` with the
  34 anchors repointed (`a649b5f8`, `1dce8ad9`).
- The six demo clips and the hero were re-recorded against the current UI in English, from an
  isolated data root (`docs/media`, `docs/screenshots/hero-banner.png`).

### Tests
- The clock gates stand down on a GitHub-hosted runner, which is not a characterised machine
  (`tests/timing_segment.py`, `772ddd66`).

### Added

- The first open runs from the six-second scene into a greeting and four stops — usage,
  engine, activation, carry-over — with the bee as guide, then the desk; progress lives in
  `~/.ephe/tour.json` and `?tour=1` replays it (`d6cd8d42`, `263e91a7`).
- embedder: EmbeddingGemma 2 with a consent-gated downloader (`abe0f85d`)
- plan: The guard states the shortest step and its example honours the floor (`a3fde9e0`)
- plan: The card is readable while the answer streams, and its gate opens when it ends (`a368b992`)
- The wave-a batch — gate hygiene, the change-set revert, doc truth, and the plan-card lane (`443bbdd5`)
- tui+cli: The bars paint, one version, one preview convention, and the pipe works (`2479d37e`)
- brand: The mark is a forest spirit, and the creature ships in every cut (`8e3df053`)
- update: A live question, a signal that breathes, and a progress that reports what happened (`7664b8fb`)
- tokens: The reading scale exists, and the primitives that can express it (`38a7e7d2`)
- sidebar: The task rows are a list, and only the running one carries the accent (`f84ec459`)
- settings: The register gets its section rule and the rows move onto the reading scale (`09db34aa`)
- update,first-run,glass: A restart the user decides, an intro built from code, and a glass forest (`55efa4b8`)
- public: A contributor's gate, the user's own build script, the public check — and the sweep this commit carries (`dfbcd20d`)
- ci: The publication is built and guarded, not hand-cut (`3d53a689`)
- shell: The agentic workbench bar and the run rail (`d2398c5e`)
- brand: The fire-spirit bee figure and its first-run scene (`56386946`)
- brand: The bee icon set across every shipped surface (`ceae3a55`)
- dist: The package pipeline renders, publishes and ratchets (`d56eee24`)
- publish: The exclusion list, the report and the gate run (`607e908a`)
- cell: The runtime moves to 1.1.0, re-measured the way the fence asks (`803b48e5`)
- ui: The shell ships one type step larger, and the floor is 12 px (`a174e9a4`)

### Security

- security: The channel test fixture carries a placeholder, not a live token (`e826a40c`)
- security: The CodeQL alerts — containment where reachable, by-design notes, ReDoS rewrites (`287a696b`)
- security: The alert sweep, the lockfile guard and the harness read hold on linux; the reader and relpath tests keep their contracts (`2c35309b`)
- security,privacy: The policy says how to report, not which gates we run (`56390c61`)
- security,privacy: The hardening pass, the sweep, and the prose both trees carry (`7746e52c`)
- security: The secret scan reads a CSS custom property name as a name (`26c5a948`)
- security: The key is write-only, and every bind that leaves the machine is authenticated (`a3cd537d`)
- security: One confinement primitive, and a refusal list for the user's own folders (`c6f2ca8e`)
- security: The three path-injection sites say why they are safe, in the line (`891f197d`)
- security: CORS grants the product's own origins, and a shell command needs an approval (`3bec7792`)
- security: This server's own origin stays allowed, under both loopback spellings (`4016f7d8`)
## [0.1.0-beta.10] – 2026-10-19

### Added
- A provider's per-model facts are carried only when the endpoint states them: context
  window, input/output price per 1M, free, tools and vision, each nullable, with no
  inference from a name and no `-free`/`:free` suffix logic anywhere; the probe answer,
  the provider list and the settings option payload carry the same record (`7896500f`).
- One searchable model picker serves all three hosts: search over id, name and provider,
  four filters and four sorts, Favorites → Recently used → provider sections, metadata
  rows that print an em-dash where the engine said nothing, a local star and recent list,
  and a combobox keyboard path that becomes a full-screen sheet with a close control on a
  phone. A remembered model is restored, more than one model preselects nothing, and the
  composer chip menu mounts the same body with its `kind`/model/endpoint contract intact
  (`42c57562`, `1f05377f`, `48f1bfd8`).
- The setup page says which token answered a probe — `given`, Ephe's own store, a key
  found beside Ephe (`foreign`) or none — so "reachable" can no longer stand in for the
  user's own key (`315e94c2`).
- The brand contract is applied where it starts: the setup card mark (48 px) and the
  welcome hero fallback (64 px) show the shipped 3D hero render on its own dark ground in
  both themes, the `minimal` form keeps the vector, and a test walks every mark placement
  so a vector cannot return above 47 px (`215bda6f`).
- An engine that answers without tools no longer fails mid-loop: a stated
  `supports_tools: false`, or the first refused tool array for an `(endpoint, model)`, is
  remembered for the process and the turn answers without it, with "answers only, no
  tools" on the model row. Unknown keeps today's array (`215bda6f`).
- Custom instructions: a bounded user layer (4,000 characters) enters the prompt as its
  own provenance-marked stage ahead of the project rules, absent when empty and truncated
  with a marker beyond the cap, editable in Settings → Behaviour with a live counter
  (`aef59944`).
- Workspace rules read `.ephe/rules/*.md` in addition to `AGENTS.md`, sorted by name,
  provenance-marked per file and capped per file and in combination. Files under a deny
  root, symlinks leaving the directory, unreadable and empty files are skipped and named.
  The context popover now shows the prompt stage by stage and every rule file with its
  status, from the same resolver the prompt reads (`aef59944`).
- Approval overrides in the one direction the threat-model review allows: read-only and
  network categories can be made to ask every time; nothing can release a category that
  already asks, and `--yes` does not override a forced prompt (`aef59944`).
- Generation settings expose the engine's reasoning effort (unset stays the request
  shape every earlier version sent), and the dials now show the stored generation block
  (`aef59944`).
- The context popover reads a gradient as the ground it paints, so glass and gradient
  surfaces are measured against what is really beneath them (`24ea7edf`).

### Changed
- The engine probe and the provider/probe model types moved into files of their own
  (`core/model_probe.py`, `app/src/lib/api/providers.ts`), bringing the whole-tree
  architecture count back from 55 to the baseline of 49 errors (`cb43552a`).
- Settings keeps a partially answered read as a state of its area instead of treating it
  as a failure, and a tab keeps its state when the panel re-opens (`44e9b698`).

### Fixed
- OpenRouter's routing refusal ("No endpoints found that support tool use") is
  recognised as a refusal of the tool array, so the turn is rebuilt without it instead of
  ending in a 500 (`5a865bba`).
- The welcome model line prints an em dash instead of a malformed `Model: ()` when the
  engine named neither a model nor a tier (`ce503c14`).
- Six light-theme findings of the theme sweep: control edges sit on the control token,
  accent text stays at the AA step paper supports, the status badge and setup hints use an
  ink paper supports, and the paper warning tone meets the floor the contract asks
  (`f57fcd10`, `26f47056`, `1cd1c3fb`, `8460b467`, `ccc02129`, `2b470919`).
- Packaging templates point at the published beta.9 assets, so a snapshot renders the
  current release instead of a stale one (`1734b9d8`).
- The given probe key is read off one stripped value, so a pasted key with surrounding
  whitespace answers the probe (`0ba0f2be`).

### Tests
- The theme-parity sweep measures every surface in both themes at 1280 and 390 and its
  register ratchets to text 16, boundary 8, no render error; the edge comparison reads
  what lies outside the element (`15d73e2d`, `f34ce3b1`, `3972cbf4`, `bff7ef1b`).
- The desktop bundle test accepts the RPM face of the version, so a Linux build reports
  the same number as the app (`a80a0e2d`).
- The light gates run on GitHub-hosted runners and the secret scan is pinned to its
  hosted runner (`35b7303e`, `75160367`).

### Security
- The Swift extraction helpers are withheld from the public snapshot (`85e35188`).

## [0.1.0-beta.9] – 2026-10-17

### Added
- The first open cuts five camera setups — wide establishing, low stream track, the
  close-up with two heartbeats and the firefly spiral, the shrinking vortex frame and
  the macro portrait — and the rendered film carries a deterministic 48 kHz stereo
  score as AAC and Opus (`c53f7a63`).
- The companion outlives the onboarding: the live actor `c53f7a63` sits in the welcome hero
  and above the composer, with five settings (enabled, form, behaviour, sound, size),
  a click-flight wing flutter, a D-pentatonic spark burst and blinking eyes.
- The sprite extraction uses real alpha matting: `binary_fill_holes` on the Vision mask,
  `distance_transform_edt` background estimation and foreground colour decontamination
  write 2120 × 1504 Retina layers with premultiplied Lanczos-4 upscale (`d0feafe3`).

- The onboarding carries the live guide: a 60 fps spring-flown bee that follows the
  pointer with its pupils, flies to a click or a control, flaps in 3-D and performs the
  finale into the header (`72118913`).
- The first open is a live 60 fps choreography on the clearing keyframe: a spark falls
  into the moss, runs a spline over the stream, spins into a fire tornado and becomes the
  bee while her wings open and a honeycomb shockwave leaves the vortex; the same
  component renders the 12.8 s MP4/WebM through a frame-exact seek (`81566049`).
- The guide and the intro carry the actor cut again from the awakening frame: both eyes
  sharp, no seam across the belly, wing layers with no cheek or belly pixels, and the
  forehead flame back in the actor, the large icons and its own animated layer
  (`81566049`).
- The tour keeps the keyframe stage, shows the engine-core frame in step 2 and the finale
  frame before the workspace; the guard step previews a real approval card; the first
  answer recommends the matching starter card (`b2a404bd`).
- The runtime trust layer: protected roots are refused before any dialog, a
  credential-shaped file needs approval even for a read tool, redaction runs before the
  model context, the SSE stream, the run ledger and the audit log, and every tool result
  carries the call id it answers (`614645c9`).
- Every run writes an append-only JSONL ledger with the five-phase projection
  (`Now`, `Waiting`, `Changed`, `Result`, `Next`); `/api/health` names the instance, pid,
  root, version, contract and owner, and the desktop shell adopts only a backend it
  started (`614645c9`).
- Settings → Session store offers **Delete all chats**: one confirmed gesture clears the
  backend store and the browser's copy (`f52fa12d`).

### Changed
- The fire-spirit bee is a 3D volume rig: a sphere head with rim light and warm bounce,
  a fur collar, a lantern belly with honey cells and three chitin bands, four independent
  wing groups, an amber iris with pupil tracking and the v2 crown on the small cut; every
  icon and Tauri bundle is regenerated from it (`72118913`, `2ab2a4fc`).
- The live guide is the cut-out 3D actor from the hero keyframe, with two wing layers
  turning on their shoulder origins; it perches left of the panel, holds a clicked
  control for 1.35 s, hovers at its anchor and leaves a continuous trail, and the large
  icons render from the same sprite (`d009f25d`).
- The task dock sits at the bottom-right of the chat column, where there is room; on a
  failed turn the header reads "Stopped with an error" instead of a worked-for time, and
  the restore notice is one toast that updates in place and auto-dismisses (`f52fa12d`).
- A first start without a stored language follows the browser's language (`f52fa12d`).
- The tour's primary button, selected card and switch use the bee's honey gold instead of
  the coral brand pair, with dark ink on the button (`81566049`).

### Fixed
- The intro and tour resolve only defined tokens, with 44 px coarse-pointer floors, and a
  failed language chunk keeps the boot catalog readable instead of painting key paths
  (`8c434261`).
- The welcome sentence stays beside the new recommendation, and the small bee cut carries
  the v2 crown so the 32 px icon paints the brand red (`9033eb21`, `2ab2a4fc`).
- Leaving the tour without an engine records the setup skip, and the carry step's footer
  advances without an import (`b2a404bd`).
- A first start with an empty local store follows the browser's language *and* bundles
  that catalog as the fallback, so a German webview no longer paints key paths
  (`dfe6e883`).
- The header and overflow E2E specs follow the compact header, and the port-hygiene
  register names the shifted line (`f9281f89`).
- Redaction preserves a gate denial's code, the stricter tool wire accepts every fixture
  id, and the SEC-1 credential corpus is an allowlisted synthetic fixture (`757a685a`).
- The engine error box offers "Set up engine" beside Retry and renders known connection
  failures in the UI language; the error stays on the turn through a reload (`f52fa12d`).
- Audit round: the setup offer starts in capitals, the replay frame localizes its step
  count, the empty workbench says its sentence once, the output-directory hint reads
  "where the file is created first", and Custom Ollama follows the app's vocabulary
  (`f52fa12d`).
- The import route accepts no filesystem path: the native picker records the chosen
  folder behind a one-time token, the route imports only that selection, and a missing,
  expired or reused token is refused (`d72e0d43`). Closes CodeQL alert #12
  (`py/path-injection`).
- The mobile sweep's twelve target and input defects are fixed: every measured control
  reaches 44 px on a coarse pointer and every input 16 px, with the desktop probe
  unchanged (`d9f13df7`).
- The first-open locale keys fit their weight budget, the German surface allows the
  loanword Skills, the tour stylesheet reads only defined tokens, and the frozen API
  contract names the tour and import routes (`f80273b4`).
- The shell stops its backend before an in-app update relaunches it, so the new
  version does not inherit the old Python process (`57b6ed14`).
- The published tree carries the bee generator the in-app mark imports, and the
  compact band is the bee's flat cut (`a983f037`).
- The in-app mark is the bee: the chat welcome, the setup screen and the sidebar
  inline the same figure as the app icon and the first-open scene (`2de03359`).
- The desktop update compares the running bundle's version with the release, so a backend
  from another checkout cannot answer for the shell; the dialog shows the release notes
  without a fold and a small ember while the bundle transfers (`afc28891`).
- `uvicorn[standard]` is declared, so a fresh install ships a WebSocket server: the terminal
  pane and the HMR tunnel connect instead of being refused (`pyproject.toml`, commit `eb48c7e0`).
- The desktop publish names its author, so a runner with no git config can publish a change
  set (`core/atomic_publish.py`).
- The task store resolves through the config root, so an isolated run stops reading the
  owner's task ledger (`core/tasks.py`).
- `install.sh`'s error trap uses `${#BASH_LINENO[@]}`, which bash 4 and 5 accept
  (`install.sh`).
- hygiene: Prune verb, ALLOWED_ROOTS, provenance, workspaces cap, db import, trajectory window (`2d1bb8ca`)
- embedder: Fetch the fp16 weights and feed empty modality slots (text-only) (`2b252d54`)
- ci: The advisory probe survives an empty ignore-flag set (`29c65d85`)
- ci: The tests leg activates the pinned pnpm; the arch baseline follows the tree (`e6b13f46`)
- arch: Keep verify_tools.py under the 400-line wall (`b5011732`)
- ci: Restore the arch baseline freeze and cover the prune decline branch (`536e6cbd`)
- ci: The installer trap, the managed root, the guard's argv read and the hint query hold on linux too (`03b3a3a8`)
- publish: Commit-tree names its author, so a runner without a git config can publish (`b9effebb`)
- hooks: A declared deletion no longer ends the pre-commit hook in silence (`d9dca03b`)
- ui: The terminal wears the product's palette, and the claims say what the product does (`975de3e1`)
- ci: The release pipeline pinned an action commit that does not exist (`81e441a8`)
- update: A beta can be offered an update, and a click asks the feed live (`8c7a7d14`)
- desktop: The updater flag belongs to the release build, not to every build (`98d678cd`)
- brand: The mark reaches its colour by role, and the gate can reach the mark (`54e06417`)
- brand: The ears are leaves, and the geometry test reads them instead of naming them (`2ca741dd`)
- i18n: The engine and key hints state the behaviour instead of promising an absence (`65ba8e0d`)
- cn: A type step survives the merge, by rule rather than by a list of names (`d0a72872`)
- theme: Open on the forest, because the paper register was rejected as the product's face (`ad4d4694`)
- ci: The two legs that were red on the public mirror (`ff6ce8e7`)
- licence: The claims match the licence, and the copies that ship follow it (`baf7af5e`)
- licence: The notice is accurate, the installer says what it installed, the grant is signed (`53520bab`)
- licence: The Additional Use Grant is None, and every sentence that promised production use now tells the truth (`e748c600`)
- engine: A tool block is never cut in half, so a long run stops being refused (`e17ba89d`)
- licence: The licensor is Bemler Labs, with no legal form and the mailbox the owner gave (`9d2cf1bc`)
- ci: A token lands with its consumer, and these ten had not (`6bd166b2`)
- ci: The verify job activates pnpm before it asks setup-node to cache pnpm (`798049ca`)
- engine: The key file's rename is observable on every Python (`7a9db58f`)
- e2e: The onboarding helper clears the first-run flag too (`a5660ffa`)
- ci: The export sheds only what the target's own index carried (`b3fca7c8`)
- e2e: The frame budget carries the host's own noise (`8af1f3d3`)
- docs,cli: The project says what it is (`921d26d7`)
- docs,ci: Comments that describe a repository the reader is not in (`407409a0`)
- test: The symlink-loop case pins the invariant, not macOS's answer to it (`1acf857c`)
- ci: The export takes its file list from HEAD, like its contents (`8f72db94`)
- release: The updater-manifest switch uses the input the action still has (`e85fc8a8`)
- setup: The engine screen chooses nothing for the user (`a19dc77b`)
- dist: The package surfaces point at the release that exists (`a0604f59`)
- dist: The npm scope is the org that exists (`2ff5722e`)
- docs: The two gates the audit found red (`928b49c8`)
- public-surface: The private material the shipped pages carried (`7aa11022`)
- docs: The README token the command parser read as a subcommand (`e529d807`)
- public-surface: A sibling tool's name out of two shipped dashboard tests (`d8ecc33a`)
- publish: The exclusion list is enforced, and a reference is judged where it acts (`9b14ef58`)
- publish: The ignore traps, and the guard that names them (`ab466305`)
- publish: The registers the published gates read stay in the publication (`8ebbb0e9`)
- publish: The published suite passes on the tree it is published with (`545cc19c`)
- publish: The lint exclude holds where the tree carries its own policy (`e45d5c1b`)
- publish: The marker the lint guard asks for is named on purpose (`dc9d4786`)
- tests: The two suites the publication made red (`917aa82d`)
- engine: A tool result answers the call the engine issued (`faf987f8`)

### Changed
- The permanent toolbar row is now a task dock at the bottom-left: it appears once a
  session has messages and there are several tasks, a plan or a git project, and shows
  the tasks, the plan steps, the branch and the four panel destinations; it collapses to
  a pill and can be dismissed for the session (`86b2abf9`). Below 1024px it starts as the
  pill, and a collapsed or opened choice survives a task switch (`c3f94ed4`). The dock
  floats over the transcript instead of across the composer (`d9727166`).
- The chat header keeps identity, the panel toggle and one named overflow; New Session,
  navigation, update, theme, shortcuts, the library and the window controls live in the
  menu, and the header identity draws the bee (`18e0acd6`).
- The welcome screen names one engine condition — ready, unreachable, key-refused or
  no-model — and offers the matching next step, with a retry for an unreachable engine
  (`84957d58`).
- Workspace rows read state, task, the why drawn from the payload's own waiting and
  last-event fields, one next action, the change summary and labelled clocks; change sets
  lead with outcome and approval condition before files and digests (`a16074fd`).
- README.md is a 255-line front page; the reference material moved into `docs/` with the
  34 anchors repointed (`a649b5f8`, `1dce8ad9`).
- The six demo clips and the hero were re-recorded against the current UI in English, from an
  isolated data root (`docs/media`, `docs/screenshots/hero-banner.png`).

### Tests
- The clock gates stand down on a GitHub-hosted runner, which is not a characterised machine
  (`tests/timing_segment.py`, `772ddd66`).

### Added

- The first open runs from the six-second scene into a greeting and four stops — usage,
  engine, activation, carry-over — with the bee as guide, then the desk; progress lives in
  `~/.ephe/tour.json` and `?tour=1` replays it (`d6cd8d42`, `263e91a7`).
- embedder: EmbeddingGemma 2 with a consent-gated downloader (`abe0f85d`)
- plan: The guard states the shortest step and its example honours the floor (`a3fde9e0`)
- plan: The card is readable while the answer streams, and its gate opens when it ends (`a368b992`)
- The wave-a batch — gate hygiene, the change-set revert, doc truth, and the plan-card lane (`443bbdd5`)
- tui+cli: The bars paint, one version, one preview convention, and the pipe works (`2479d37e`)
- brand: The mark is a forest spirit, and the creature ships in every cut (`8e3df053`)
- update: A live question, a signal that breathes, and a progress that reports what happened (`7664b8fb`)
- tokens: The reading scale exists, and the primitives that can express it (`38a7e7d2`)
- sidebar: The task rows are a list, and only the running one carries the accent (`f84ec459`)
- settings: The register gets its section rule and the rows move onto the reading scale (`09db34aa`)
- update,first-run,glass: A restart the user decides, an intro built from code, and a glass forest (`55efa4b8`)
- public: A contributor's gate, the user's own build script, the public check — and the sweep this commit carries (`dfbcd20d`)
- ci: The publication is built and guarded, not hand-cut (`3d53a689`)
- shell: The agentic workbench bar and the run rail (`d2398c5e`)
- brand: The fire-spirit bee figure and its first-run scene (`56386946`)
- brand: The bee icon set across every shipped surface (`ceae3a55`)
- dist: The package pipeline renders, publishes and ratchets (`d56eee24`)
- publish: The exclusion list, the report and the gate run (`607e908a`)
- cell: The runtime moves to 1.1.0, re-measured the way the fence asks (`803b48e5`)
- ui: The shell ships one type step larger, and the floor is 12 px (`a174e9a4`)

### Security

- security: The channel test fixture carries a placeholder, not a live token (`e826a40c`)
- security: The CodeQL alerts — containment where reachable, by-design notes, ReDoS rewrites (`287a696b`)
- security: The alert sweep, the lockfile guard and the harness read hold on linux; the reader and relpath tests keep their contracts (`2c35309b`)
- security,privacy: The policy says how to report, not which gates we run (`56390c61`)
- security,privacy: The hardening pass, the sweep, and the prose both trees carry (`7746e52c`)
- security: The secret scan reads a CSS custom property name as a name (`26c5a948`)
- security: The key is write-only, and every bind that leaves the machine is authenticated (`a3cd537d`)
- security: One confinement primitive, and a refusal list for the user's own folders (`c6f2ca8e`)
- security: The three path-injection sites say why they are safe, in the line (`891f197d`)
- security: CORS grants the product's own origins, and a shell command needs an approval (`3bec7792`)
- security: This server's own origin stays allowed, under both loopback spellings (`4016f7d8`)

### Quality wave

- The desktop vibrancy and three-zone studio work recorded under Unreleased ships in
  this tag (`00431f81`), and `a55545b2` names it in the changelog.
- `create_xlsx` writes real Excel formulas through a safe `=` allowlist, infers
  percent/currency/ISO-date/number formats, and adds auto-filter, zebra rows and a
  styled total row (#20).
- Deck composition is fully dynamic: `default_storyline(title, audience, thesis,
  source_status, source_notes)` derives eleven topic-specific slides and `parse_slides`
  carries source notes through to the deck spec, with no canned narrative (#21).
- `create_diagram` and `generate_chart` take `theme="light"|"dark"` with exact
  palettes and grouped-bar/line series, and charts embed into PDFs as vectors instead
  of raster captures (#23).
- `evaluate_quality(question=...)` verifies multi-file arithmetic against tool output:
  a compute question without a successful evidence tool is a hard issue, and claimed
  totals must match the computed stdout (#17).
- A routing gate asserts every skill pack declares at least two `when_to_use` and two
  `when_not_to_use` terms, and three packs gained the missing veto terms (#22).
- `README.zh-CN.md` and `README.es.md` reach full section parity with the English
  README, with commands, paths and product names unchanged (#18).
- The app adopts the npm minor/patch group: Radix primitives, TanStack Virtual, the
  Tauri plugins and CLI, i18next, PostCSS, Prettier and typescript-eslint move within
  their major lines, and the lockfile is refreshed.
- `tests/test_tui_context_meter.py` pins `EPHE_TOKEN_COUNTER=calibrated` and resets the
  tokenizer cache per test, so an installed tiktoken no longer changes the fixture
  counts; `skills-lock.json` follows the three metadata edits.

## [0.1.0-beta.8] – 2026-10-17

### Added
- The chat's work moves into a task dock at the bottom-left: tasks, plan steps, the branch
  and the four panel destinations appear once a session has messages; it floats over the
  transcript, collapses to a pill, starts closed below 1024px and keeps the chosen state
  across a task switch (`86b2abf9`, `c3f94ed4`, `d9727166`).
- The empty chat names one engine condition — ready, unreachable, key-refused or no-model —
  and offers the matching next step, with a retry for an unreachable engine (`84957d58`).

### Changed
- The chat header keeps identity, the panel toggle and one named overflow; New Session,
  navigation, update, theme, shortcuts, the library and the window controls live in the
  menu, and the header identity draws the bee (`18e0acd6`).
- Workspace rows read state, task, the why drawn from the payload's own waiting and
  last-event fields, one next action, the change summary and labelled clocks; change sets
  lead with outcome and approval condition before files and digests (`a16074fd`).
- The design contract and the screen spec live in `docs/DESIGN.md` and
  `docs/SCREEN_SPEC.md`, and a parity guard compares the PWA and desktop shells across
  11 routes and 19 platform reads (`b4ce026e`, `c25b51cf`).

### Fixed
- Every measured control reaches 44 px on a coarse pointer and every input 16 px across the
  six mobile surfaces, with the desktop probe unchanged (`d9f13df7`).
- The import route accepts no filesystem path: the native picker records the chosen folder
  behind a one-time token and the route imports only that selection (`d72e0d43`). Closes
  CodeQL alert #12 (`py/path-injection`).
- The first-open locale keys fit their weight budget, the published gates reach their
  registers, and the frozen API contract names the tour and import routes (`f80273b4`).

## [0.1.0-beta.7] – 2026-10-17

### Added
- The first open runs from the six-second scene into a greeting and four stops — usage,
  engine, activation, carry-over — with the bee as guide, then the desk. The marker is
  device-level (`~/.ephe/tour.json`), activation writes the real settings, skills and
  web-research plugin, carry-over imports through `/api/import` on the desktop, and
  Settings → About replays the tour (`d6cd8d42`).

### Fixed
- The shell stops its backend before an in-app update relaunches it, so the new version
  does not inherit the old Python process (`57b6ed14`).

## [0.1.0-beta.6] – 2026-10-17

### Changed
- The in-app mark is the bee: the chat welcome, the setup screen and the sidebar
  now inline the same figure as the app icon and the first-open scene, and the
  one-ink template cut follows it (`2de03359`).

## [0.1.0-beta.5] – 2026-10-17

### Fixed
- The in-app update compares the release with the version of the bundle it will replace,
  through the signed updater, instead of trusting the local backend's number. A backend
  from another checkout (the reuse branch, a dev server) could answer an older version and
  make the panel offer an update the shell already had, or hide the one it did not
  (`afc28891`).
- `core/_version.py` prefers the checkout's `pyproject.toml` over an older `ephe`
  distribution installed in the same interpreter, so a source run reports the tree it is
  running (`afc28891`).
- The Homebrew cask and the Scoop manifest name the hashes measured from beta.4's published
  assets, so an install from the tree checks out against the release it names (`24f70fe9`).

### Changed
- The update dialog states the version transition, shows the release notes without a fold,
  names the release date, and offers "Later"; while the bundle transfers the card tilts a
  few degrees and an ember breathes, and both stop under reduced motion (`afc28891`).

## [0.1.0-beta.4] – 2026-10-17

### Fixed
- A tool result names the call the engine issued. The shared tool loop appended
  `{"role": "tool"}` without an id and the provider relied on position; when no block was
  open it invented one, and an OpenAI-compatible engine refused the turn with "tools must be
  a response to a preceding message with tool_calls". A result whose block is gone now
  travels as a user message, so a resumed history stays legal (`faf987f8`).
- The message-action row wraps instead of running out of the viewport at 390 px.

### Changed
- The shell ships one type step larger: the two floor steps move up (10/11 -> 11/12) and the
  base 14 -> 15 px, through the Appearance setting's single lever. Measured on the rebuilt
  shell: text below 12 px falls from 148-194 runs per screen to one, and horizontal overflow
  is zero at 1440x900 and 390x844 (`a174e9a4`).
- The cell runtime is pinned to Ephemora Cell 1.1.0 and re-measured against the fence: the
  wheel read from the artifact, `RLIMIT_FSIZE` still the per-file write cap, and the four
  lifecycle beats proved on the release (`runtime=cpython-cell/3.13.16 net=none`, `803b48e5`).
- The published tree is a filtered subset: the user and contributor documents, the product
  and its tests. Sources that only the workshop needs are absent, no published file names
  something the tree does not carry, and the exports' own language and prose baselines are
  pruned to it (`e45d5c1b`, `dc9d4786`, `917aa82d`).

### Added
- `docs/QUICKSTART.md`: install, start, the engine table, the first question, and the five
  failure modes with the real flags.
- A Mermaid topology diagram in `docs/ARCHITECTURE.md`, and the legend `FEATURE_STATUS.md`
  never explained (active, experimental, planned).
- Package manifests for Homebrew and Scoop, rendered by the release workflow with hashes
  measured from the assets it just built, and the npm wrapper under `@ephemora/ephe`.

### Removed
- Sixty-one captured screenshots under `out/` left the index: the tree's own ignore rules
  say a capture of a live session does not travel, and they were tracked anyway.

## [0.1.0-beta.3] – 2026-10-16

### Security
- CORS grants the origins the product uses and nothing else. It used to grant **any**
  `http://localhost:<port>` with credentials, which is every page a local service happens to
  serve; the PWA is same-origin here and the dev server proxies `/api`, so a front end that
  does need its own origin names it in `EPHE_DEV_ORIGINS`.
- `POST /api/shell` and `POST /api/shell/pty` run a command only when the call carries
  `approved=true`. The CSRF header proves the request came from a page that can set headers;
  it never proved that a person decided, and the route refused nothing without that.
- `GET /api/settings` no longer returns the stored engine key. It reports whether a key is
  held and its last four characters, the way the image section already answered.
- Every bind that answers beyond loopback arms the LAN pairing token, a named LAN address
  included: `--host 192.168.1.20` served every `/api` route without one.
- `/charts` serves the artifacts directory and is authenticated like the API; it used to
  serve the whole system temp directory outside the check.
- The two folder settings refuse the filesystem root, credential directories, system roots
  and the product's own state directory. `core/path_guard.py` holds the one confinement
  comparison the workspace register and the settings surface share.
- The engine key file is created owner-only in the open, and renamed with `os.replace` so a
  watcher sees the rename on every interpreter.
- The frontend artifact upload fails when the build produced nothing.

### Fixed
- Two scripts whose import bootstrap had broken their syntax parse and run again.
- The end-to-end suite clears the first-run flag, so the keyboard and slash-menu cases reach
  the composer instead of a modal that holds focus.
- The idle frame budget compares the chat view against a control window on the same host
  rather than asserting a fixed count on any machine.
- The secret scan reads a CSS custom property name as a name, not as a credential.

### Changed
- The runner labels come from repository variables, so the workflow files here are the files
  the project is developed against.
- The frontend build runs its full step list again, the Playwright suite included.

### Docs
- Claims the tree contradicted are corrected: the CLI banner and the launch playbook name the
  licence the project ships, `CONTRIBUTING` no longer calls this repository private,
  `docker-compose.yml` and `.env.example` no longer pre-select an engine beside a promise of
  no silent default, the security policy names the supported line, and `NOTICE`, `llms.txt`
  and the benchmark note agree with the tree again.
- The security policy records why three `py/path-injection` findings are dismissed and what a
  reviewer reads instead.

## [0.1.0-beta.1] – 2026-10-15

Work that landed after the 0.0.1 baseline; the phase names follow the roadmaps.

### Added

- **The agent's own workspace (G6):** `process_manage(action='list')` enumerates the
  background register (id, status, age, output size, command) so a running job is
  found instead of remembered, and `kill` needs no id kept from an earlier answer;
  `read_transcript` exposes the model trajectory as a tool — the agent reads the same
  numbered steps `GET /api/trajectory` serves, with optional text bodies; and
  `read_cell_journal` fetches a byte range of the session's `/work` `stdout.log` /
  `stderr.log`, which is where the cell tees the output a capped result block left
  behind. All three are read-only and sit in the always-visible tool array.
- **Workbench provenance chain (R4-A3):** a turn gets its id before it starts, a
  card shows the task and the tool calls behind it, and one click walks the round
  trip chat ⇄ workbench (`f994e68c`, `1b55053b`, `8c3bb9b1`, `3bc713cf`).
- **Artifact preview (R4-A5):** `.xlsx` reads as a table and `.docx` as text in
  the browser pane; PDF, image, audio and video open through the artifact id.
- **Single desktop instance without a new crate:** `app/src-tauri/src/instance.rs`
  keys a socket on the real config path (`c37efab5`).
- **A produced file is reachable in the message that produced it** (`5db2516b`).
- `ephe code` and `ephe goal` write a machine-readable run record (`87c5c0cb`).
- **Signed skill packs (W3-14):** a pack may carry `ephe-skill.sig.json`, an
  ES256 signature over its RFC 8785 canonical payload with the same trust
  anchors as plugins; the loader reports signature state and
  `GET /api/skills/{name}/verify` checks a pack against its current content,
  and an install that ships a record which does not verify is rejected.
- **Eval suite at 3x with a judge and a pass^3 gate (`13918ff7`):** the suite
  grows 54 → 162 cases, every family at three reps; a judge eval on the persisted
  engine scores precision 0.8125, recall 0.8667 and f1 0.8387 over three reps
  with no flips; the pass^3 gate exits 1 on a task that flipped between reps and
  2 on an untrusted cohort or a local engine; an endstate eval scores the world
  state on disk rather than the tool trace.
- **Lazy chat panes, PWA wiring and one token scale (`fc6b1775`):** the chat
  chunk drops 208.03 → 101.18 kB gzip by splitting `AgentPanel` (107.04 kB, now
  owning xterm and the 31 agent modules) and `ArtifactRail` into their own lazy
  imports; registration, install prompt and update banner are one wired module
  gated on `SKIP_WAITING`, so a running turn is never taken over; the panel and
  session menu are real keyboard menus; the design tokens collapse to one scale
  per axis with a guarding test.
- **One error classifier across serve, chat and cli (`7df2644c`):**
  `core/provider_errors.py` is the single source for `error_code_for`,
  `http_status_for` and `exit_code_for`; the three surfaces read it instead of
  private substring lists, and the 404/405 gap in the serve contract closes.
- **Decision layer, failover chain and an observable tool budget (`5cfdad4d`):**
  `core/decisions.py` records an auditable decision for skill and intent routing,
  with the offline scorer as the default; prompt prefixes go 93.0 → 99.3%
  cacheable across turns and 8.9 → 99.9% across a day rollover; the tool budget
  is observable at both ends; compaction checkpoints carry a sha256 fingerprint,
  and failover is proved against a live HTTP secondary.
- **Wave-2 landing (`5859c35f`):** coverage closeout (cell boot 17 → 99%, the
  keychain and audit/usage routes to 100%), the provider failure taxonomy, the
  UI proof set, the e2e round trips and the hardened installer with PowerShell
  parity.
- **Mid-run steering (`39569a52`):** a turn takes a direction change at its next
  tool-round boundary — `POST /api/chat/steer` queues it, the model reads it on
  its next step, and the transcript names the round and who changed it; a stop
  lands at that same boundary instead of killing the turn mid-write, and a steer
  the turn never reaches is reported as unlanded.

- **Isolation wave — one worktree per agent run (`7dff2375`):** `core/workspace_lifecycle.py`
  registers a git worktree and a `ws/<owner>-<id>` branch for every agent run, refreshes each row's
  state from git, and deletes only inside its own managed directory. `ephe agents` prints the live
  register; `ephe reap` collects the trees whose owning process is gone, after the grace period.
- **A change set carries its paths, its digests and the why (`6ed23988`):** `core/change_set.py`
  records every touched path with its operation and a sha256 digest of that file's diff, beside a
  provenance block — the session, the agent and the reason. A set that cannot say why it exists is
  refused. `ephe changes <workspace>` prints them newest first. Publishing is atomic (`78d3e510`):
  every file of a set or none, the branch ref moving once by compare-and-swap.
- **The isolation verbs a terminal can read (`031fa352`):** `ephe agents`, `ephe changes`,
  `ephe review`, `ephe publish` and `ephe reap`, over the `/api/workspaces` surface the freeze
  records (`4773a8ca`).
- **Parallel agents and their change sets, on one page (`f53833b7`):** the app lists each
  workspace's sets with the paths they touched and who touched them (`75808527`).
- **The finished prune gets a door (`39e48a25`):** the session store's retention endpoint, which had
  no caller, is reachable from a settings row and from `ephe prune` — a dry run unless `--apply`.
- **The chat store carries tags, folders and a restorable trash (`e209a9da`).**
- **Mathematics, diagrams and code fences render on demand (`cbce90cb`, `374bef00`):** KaTeX and
  the highlighter arrive as their own chunks, so the first paint pays for neither.
- **One language per user, the other on request (`023379ca`):** the locale pair loads the chosen
  language first and fetches the other when it is switched (`49ab92f9`). The offline recipe names
  `ephe start` (`e1d8e2ca`).
- **The token counter has a name above it (`8d627af0`, `9c94ef1e`):** an explicit counter, a
  compaction ledger that keeps the decisions it made, and the counter named in the run record. A
  second engine path, a named loop end and one error taxonomy landed beside it (`eed16632`), and
  the failover note reaches the transcript (`808b4f08`).
- **Agent bounds as a pure gate (`64e281f4`):** the limits are read from the repo's own load bar
  instead of being assumed at each call site.
- **The goal panel shows the loop's goal (`cac5a850`)** instead of an echo of the first message.
- **A live eval runner and its cohorts (`4bf35db9`, `717b8882`, `35d8c36f`):** budgets per axis, the
  point-11 cohort in the repo, point 12's cohort committed so its corrected number is auditable,
  and a point that names the series it belongs to.
- **The one-command install works on a bare box (`e65c2b1a`)**, and the release pipeline can start.
- **The sidebar's thirteen rows stand in the owner's three tiers (`da1ea504`).**

### Changed

- **Observability reaches the PWA server:** `server/main.py` wires
  `make_observability_middleware`, so the request id and structured logs cover the
  app surface as well as `serve`.
- **Engine defaults:** non-thinking passthrough, a swarm parallel cap and a
  no-default-model sentinel (`45d350ec`); the shipped defaults name no model
  (`64c7bb7d`).
- **Model router names no tag:** a tier is filled from the user's env, an
  unconfigured tier stays unnamed, and `/v1/models` advertises only what is
  configured (owner decision, work item #94).
- **Cell-by-default for model code is the licence, not the name (W3-15):**
  `execute_code` is auto-run only while the pinned cell carries the run. With no
  guest (or `EPHE_CODE_EXEC=kernel`) the same Python executes on the host, so it is
  classified `MUTATING` and passes the approval gate like `run_shell` — the CLI
  `--yes`/`--dry-run`/deny levers and the chat confirmation. `classify_tool` and
  `chat_tool_requires_confirm` read the runtime through
  `core.cpython_cell.code_runs_uncontained()` and fail closed when it cannot be
  read. `docs/SANDBOX_EXECUTION.md` records the decision.

- **Every error surface names a next step (`d44f91dc`)**, and the static surfaces speak one
  language.
- **The interface reaches its own floor (`d28e6afb`):** hit targets, glyphs, the dialog, the
  renderer, the palette and the shortcuts, each against a stated number. The settings header holds
  its 24 px floor at desktop width (`b5714c5d`); the palette leads a section with its best match,
  tier first, frecency only breaking ties (`0db11cb7`); a silent backend can no longer hold the
  first paint (`dc84dd3b`); the Playwright leg owns its server on a run-time port (`fecf3de4`). The
  approval dialog speaks English, its blast-radius label moved into the bundle (`06fa3820`); the
  session menu and its test read one list (`be5e20d7`); the dev store handle is back, so fifteen
  dev-seeded specs stop skipping (`73700645`); the plan runs, a boot send survives and focus stays
  in its surface (`07afe1c8`); the palette, the composer, the profiles and the restored keys
  (`9353a1dd`).
- **Three unused i18n keys are gone, so the debt ratchet holds (`92140f71`)**; the two locale chunks
  earn their budget rows and the KaTeX duplication is measured (`a2437eea`).
- **The tool block stays contiguous and a mode is enforced where a call runs (`f191b3f0`)**; a
  refusal reads as a refusal and the artifact markers have one source (`70cf49b4`); session
  lifecycle, shell refusal and the marker source are one change (`3b6296cd`).
- **The provider's own 4xx reaches the user (`70c7a61f`, `7e62136c`)**, and a markered result
  registers while the trash stops promising (`ac3eca20`).
- **The idle budget prints readably, and the steady-frame premise has room (`840ab987`).**

### Fixed

- **Injection fence unforgeable; `--dry-run` survives `--yes`** (`f51a4da7`).
- **Memory failure paths** for auto-memory, compaction and corrections (`97de109f`).
- **Desktop engine token** is a file the app can write, read from the env or the
  user's own file (`478b8aa2`, `2b5682be`).
- **Window-fit tests pinned to the heuristic counter (`f5e568d3`):**
  `estimate_tokens` prefers tiktoken when it is importable and falls back to the
  two-bucket heuristic otherwise, and a BPE counter prices the fixture far lower
  (2407 → 33), so nothing trims and every boundary assertion fails on a runner
  that carries tiktoken. The autouse fixture now pins the counter to the
  heuristic; the fitting stays free to differ.
- **The redactor masks the whole `gh*_` token family (`3f1c964d`):** a bare
  installation token (`ghs_…`) passed unmasked while `ghp_` and `gho_` were
  caught; the pattern now covers `p/o/u/s/r`, verified six ways.
- **Tests assert the contract, not the machine's extras (`257b3bc9`):** the
  sandbox and vision probes ask the same predicate the registry asks instead of
  assuming the optional extras are installed, which is why they passed here and
  failed on every CI leg.
- **CI baselines pruned and a focus assertion that waits (`01207441`):** moving
  `app/src/lib/localesScan.ts` orphaned an entry in both ratchets, which refuse
  an entry the tree does not hold; `--update` lowers the counts (2350 → 2309
  German lines, 449 → 421 tells), and `SettingsPanel.keyboard` waits for focus
  to land instead of asserting it in the same tick.
- **The eval oracle runs on the 3.10 leg (`e647526d`):** `datetime.UTC` is
  3.11+, and the three eval-oracle tests failed to import where `requires-python`
  is `>=3.10`; the module uses `timezone.utc`.

- **A change set's diff digest is pinned to one git config (`3381fdec`)** and stays under the file
  cap; `git worktree add` runs inside the register lock (`34faf117`, `9a4749e9`); every workspaces
  refusal carries a reason code that both bundles answer (`b4033809`).
- **The tool-schema cache honours the plugin filter on every return (`bf3b1737`)**; an MCP refresh
  keeps a hand-registered tool, and the wire layer moved out with it (`11329b05`).
- **The bench metric no longer joins results across rounds (`77873094`)**, and a rep can no longer
  pass on gear it never wrote; the pass³ gate names its cohort's engine and refuses another
  machine's (`8f47ecd3`); the second harness joins the same way and says so itself (`13b936b2`); a
  live-eval case was scored on another case's turn and a fired tool moved to the end (`004c6c8f`);
  the coverage floors are back where they were measured (`004d350b`); the final-answer checker
  normalizes the type its docstring always described (`d7e94554`).
- **The documented first command, an English first contact and an honest doctor (`1f67337c`).**
- **The reader's `Event` is not named `_stop` (`cfbe508d`)**; the panel seam test reads the event its
  own action produced (`0cc8106b`); QG1's boot budget stands down when its reading is untrustworthy
  (`e0fdd5f5`); QG6 guards the round's media receipts (`a5f7af7a`); the ink window is pinned in the
  read, not in a removal nothing checks (`2b91f3e9`).

### Security

- **The desktop shell gets a Content-Security-Policy (`87bc1a31`).**
- **The mirror writes the id, the probe sends the key, and `install.ps1` has a PATH (`5ec22af5`).**
- **The supply-chain register can hold a GHSA row, and the runtime JS finding is written down
  (`cb3f4ea3`)**; the fixable Dependabot alerts are closed at the copy that carries them
  (`f7f2361a`).
- **The updater pubkey is the file's own text (`8ee302ea`)**, one layer, not its base64 again.

### Docs

- A gap audit re-checked the roadmap documents against the tree; the stale rows it
  names are corrected in those files.
- This `[Unreleased]` block gives the phases a home before the next tagged
  release, the CHANGELOG half of P4-16.
- `scripts/changelog_unreleased.py` drafts this block from commit subjects and
  guards it with `--check`.
- The stray-evidence repair was scoped too wide and is narrowed to the files it
  was meant for (`6dd5a52e`).

---

## [0.0.1] – 2026-10-06

The first release of the version line that ships as **Ephe**. It is a
baseline, not a launch: the updater channel starts here so every later build
reaches a Mac by clicking a button instead of copying a bundle.

### Added

- **Workbench** (`/artifacts`) — agent output is born in
  `~/.ephe/artifacts/<session>/`, never in the user's Downloads folder. Cards
  carry a preview, an adoption target, a 30-day retention question and a
  provenance line: which task and which tool call produced the file.
- **Adoption with a real dialog** on desktop (Save-As panel), a remembered
  folder in settings, and an honest browser download where no dialog exists.
- **Native browser pane** in the agent panel, plus a reader view for pages an
  iframe cannot show.
- **Update check** that distinguishes "current" from "could not check", with
  the reason, and a menu item next to the Apple menu.
- One-command install (`install.sh`), CLI, PWA and Tauri desktop app as equal
  surfaces.

### Reliability

- Measured on a local DGX Spark (`qwen3.8-flash-next`): 56 of 60 tasks pass a
  three-run reliability gate; 174 of 180 runs green. Four exceptions are
  documented rather than hidden — one is the benchmark's own file-search gap,
  three are single-run misses.

## [1.1.0] – 2026-09-27

### Added — Ephe Extensions 1.0

A full plugin system built on one honesty principle: **a toggle that toggles
nothing gets removed.**

- **Plugin manifest v1** (`ephe-plugin.json`): bundles skill packs, slash
  commands, helper-agent profiles, event hooks, and MCP tool servers —
  validated fail-closed, quarantined on any contract violation. Spec:
  `docs/PLUGINS.md`.
- **Plugin Store (Settings → Plugin Store)**: master kill-switch (off =
  stock Ephe), per-plugin toggles that act on the **next agent turn**,
  detail sheet (version, source, permission families, content hash), and
  10 first-party bundles shipped in-repo (`plugins/`).
- **Marketplace + CLI**: `plugin-marketplace.json` with verify-first
  installation (resolve → fetch → sha256 → zip-slip-guarded unzip →
  manifest validation); `ephe plugin list | enable | disable | install`.
- **Supply chain**: ES256 (P-256) signatures over canonical JSON with an
  enable-time **drift gate** — a signed plugin that changed on disk cannot
  be re-enabled (409 + audit line). Trust anchors: repo first-party key +
  `~/.ephe/trusted-keys/*.pub.pem`.
- **User agents**: `~/.ephe/agents/*.json` (or plugin-bundled) replace the
  hardcoded helper whitelist — `spawn_agent` resolves profiles to pinned
  tools/model/timeout; unknown labels keep stock behavior.
- **User hooks**: `~/.ephe/hooks.json` — pre_tool (transform or block),
  post_tool (transform), session/turn/compact events; fail-tolerant,
  priority-ordered, audit-logged.
- **Switcher import**: `ephe import <dir>` detects persona files, skill
  trees, tool-server configs, and settings keys by structure (vendor-
  neutral); plan-first, additive writes, imported skills land DISABLED.
  Guide: `docs/SWITCHING.md`.

### Changed — Deep settings full matrix

- 15 sections / 86 fields: `engine` and `plugins` filled, new sections
  (delegation, moa, skills, zeit, kanban), expansion knobs (memory ceiling,
  fuel budget, redaction level, shell-whitelist preset, and more).
- Workspace three-state machine: `/api/fs` reports `workspace_set`; the
  chip shows a neutral "Workspace" label without a chosen project.
- Repository polish against OSS community standards: description/topics
  refreshed, root hygiene, benchmark section with the measured trend.

### Fixed

- Skill save/delete lost cache invalidation after the plugin cache-key
  change (silent stale lists in long runs).
- Focus rings on 26 popover/menu elements (WCAG 2.4.7) + Escape-dismissal
  for five menu hosts; feedback thumbs reflect success, diff undo only
  renders with checkpoints, lying "dev tools" item removed.
- `load_trusted_public_keys` scanned `~/.ephe/trusted-keys` only with an
  explicit argument — the signature gate rejected valid keys.

### Infrastructure

- Gates at release: pytest **2390 passed / 0 failed**, Vitest **604/604**,
  tsc 0, PWA build OK; `TOOL_MAP` 67; OpenAPI 106 paths / 122 operations.
- Benchmark trend (deterministic pass³, tracked manifests): **58/60
  (96.7 %)** on `qwen3.8-flash-next`.

---

## [1.0.0] – 2026-09-22

### Changed — Release consolidation (rename + version)

- **Product name:** `MiMi Nox` → `Ephe` consolidated throughout (package name, entry points, URLs, locale tokens, Tauri `productName`/`identifier`).
- **Version:** `4.1.1` → `1.0.0` kept in sync across all four readings (pyproject, `__/version__`, `app/package.json`, locale fallback `app.version`); pinned by `test_version_string_has_one_source_per_reach`.
- **Entry points:** `ephe = "ephe_cli:main"`, `ephe-app = "ephe:main"`; wheel `include`/`shared-data` moved to `ephe.py`/`ephe_cli.py`/`share/ephe/skills`.

### Fixed — Test isolation (root cause)

- **Setup-guard env leak:** `run_server._bootstrap_engine_choice()` writes `EPHE_SETUP_MODE="1"` straight into `os.environ` (no `monkeypatch` entry → invisible to `undo()`). In a full run the value leaks into later chat tests (`409` instead of `200`, 26 failures, order-dependent). A central autouse isolation in `tests/conftest.py` pops the variable per test (directly, before and after the `yield`). Green in isolation, and with that stable in a full run.

### Added — Tests

- `tests/test_env_dual_read.py` — dual-read contract (`EPHE_*` primary, `MIMI_NOX_*` fallback).
- A naming-hygiene gate keeps retired brand strings out of product sources.

### Infrastructure

- **Tool landscape:** `TOOL_MAP` = **66**, `get_tool_schemas()` = **66**.
- **Test coverage:** 2194 pytest passed / 76 skipped · Vitest 593/593 · `tsc -b && vite build` green, SW stamp `ephe-v1.0.0-sse`.

---

## [4.1.1] – 2026-09-16

### Changed — Deep-audit wave (P1/P2, team-verified)

- **P1a approval-gate bypass:** `tool_call` (the meta-router) now passes the active `ApprovalPolicy` through `session_ctx.get_current_policy()` into the inner `execute_tool` call — no more gate bypass for mutating tools invoked via `tool_call`.
- **P1b `run_tests` whitelist sync:** `ALLOWED_COMMANDS` extended with `pytest`/`npx`/`vitest` (in step with `TEST_RUNNERS`); the default `pytest -q` and `npx/vitest run` execute again (before: `validate_shell_command` rejected them before the runner check).
- **P1c never-empty error events:** `_friendly_model_error_inner` falls back to `type(exc).__name__` when `str(exc)` is empty (mirroring `_error_msg`).
- **P1d/P2b budget consolidation:** `EPHE_TOOL_BUDGET` 60→40 = `TOOL_BUDGET_HARD_CAP`; docstring contradiction (60/40/25) cleaned up.
- **P2 docs:** `COMPOSER_MODES.md` phantom `ephemeral` removed; `EPHE_AGENT_PLAN`/`skill-tool-audit` switched to `edit_file` (R35); `findings.md` status set to committed; failover unlock path numbered.

### Infrastructure

- **Tool landscape:** `TOOL_MAP` = **64** (`apply_patch` removed with R35), `get_tool_schemas()` = 63 (difference = `run_sandboxed_code` behind `sandbox_is_available()`).
- **Test coverage:** 2218 pytest passed / 75 skipped · Vitest 581/581 · `tsc -b && vite build` green.

---

## [4.1.0] – 2026-09-14

### Added — Skill-system expansion (P0/P1 after the deep audit of 2026-09-13)

**Wave 1 (P0) — foundation maintenance:**

- **P0-1: meta-tool injection** — `get_filtered_tool_schemas()` injects `META_TOOL_NAMES` + `{memory, skill_manage}` into every filtered skill schema (progressive disclosure stays active).
- **P0-2: memory + skill_manage** — all 47 skill frontmatters extended with the persistent tools.
- **P0-3: typed evidence gate** — `_evidence_gate_post_hook` (priority=100) appends `ARTIFACT_VERIFIED: <path>` after the `*_FILE:` markers; 15 marker prefixes covered.
- **P0-4a: mcp_* → NETWORK category** in `classify_tool()`; P0-4b: cache invalidation after `save_skill` / `build_skill`.

**Wave 2 (P1) — architecture patterns:**

- **P1-1: two-tier semantic routing** — tier 1 deterministic (triggers, intent regex, tool name), tier 2 TF-IDF weighted with stem-prefix matching (>=3 characters) and a hard `when_not_to_use` veto. At least 2 word matches required.
- **P1-2: typed repair automata** — deterministic parameter repair without an LLM round-trip: missing param → inject default, enum mismatch → first valid value, unknown param → drop. Post-repair validation inside `execute_tool()`.
- **P1-3: skill-stratified sidecar budget** — `_SIDECAR_BUDGETS`: standard(1600/1200), artifact(2000/1400), source_grounded(2400/1600). `quality_profile` in the frontmatter controls the caps.
- **P1-4: session-scoped assertion ledger** — `_assertion_post_hook` (priority=200) writes `path`, `verified`, `tests_passed/failed` into `_ASSERTION_LEDGER`; `conversation_compactor._build_working_memory()` reads it structurally instead of by heuristic.

**Wave 3 (tools) — new tools T1-T4 (TOOL_MAP: 65):**

- **T1 `extract_pdf_text`** — full-text PDF extraction via pdfplumber; page markers, max_chars cap.
- **T2 `format_code`** — Python formatting via `ruff format` (Black-compatible), check_only mode.
- **T3 `run_linter`** — static code analysis via `ruff check`, optional `--fix`.
- **T4 `validate_json`** — JSON Schema validation (Draft 2020-12) via jsonschema, with a fallback basic check.

**Wave 4 (skills) — new skills + gold standard:**

- **S1 `json-helper` /`/json`** — JSON pretty-print/query/diff with execute_code.
- **S2 `api-tester` /`/api-test`** — HTTP request tester with fetch_url + validate_json.
- **S3 `code-metrics` /`/metrics`** — LOC/McCabe analysis, quality_profile=source_grounded.
- **S4 `config-setup` /`/setup`** — guided engine setup dialog.
- **Gold standard:** `## Example` JSON blocks (input/steps/output) in 10 core skills.

### Infrastructure

- `.pre-commit-config.yaml` — ruff/mypy/pytest/hooks.
- `core/py.typed` — PEP-561 marker for mypy-strict.
- **Test coverage:** 2152 tests passed (waves 1-4: +21 new tests; 22+4 pre-existing git failures, exit 69).

---

## [Unreleased] – 2026-09-11

### Changed — engine choice fail-closed + no hosts/keys in the repo (audit blocks A/B)

The engine choice belongs to the user; there is **no silent default** anymore. Anyone with a
valid `engine.json` notices no difference — without a choice the start aborts with
instructions instead of falling back to local Ollama or a remote host.

- **A1/A2 — one resolver for CLI and server:** `core.engine_config.resolve_engine_choice()`
  is the shared source (`engine.json` → engine env → interactive onboarding →
  fail-closed). `ephe start`/`tui` and `run_server.py` use exactly this path;
  non-interactively it ends with exit 1 plus a fix line, interactively (TTY) it starts the
  onboarding. Aborting the onboarding no longer secretly picks local Ollama.
- **A3 — no host, no key in the code:** `DEFAULT_DGX_SPARK_URL`,
  `DEFAULT_DGX_SPARK_MODEL`, `DEFAULT_DGX_SPARK_API_KEY`, `default_engine_choice()`
  and `is_default_dgx_spark()` are removed. DGX Spark / vLLM stay first-class as a
  **preset** (`ENGINE_PRESETS`, onboarding option 3, whose product label reads
  „Eigener OpenAI-kompatibler Endpoint (DGX Spark / vLLM)"; seed optional from <!-- language-gate: ignore (quoted product label of the onboarding preset, core/engine_config.py:141) -->
  `EPHE_OPENAI_COMPAT_BASE_URL`/`EPHE_OPENAI_COMPAT_MODEL`) and as the templates
  `engine.example.json` + `.env.example`.
- **A4 — no implicit access token:** `engine_api_key_for()` only reads
  `EPHE_OPENAI_COMPAT_API_KEY`; `ensure_default_engine_api_key()` is a documented
  no-op (older callers keep working). The engine probe in `server/routes/health.py`
  no longer sends a hardcoded bearer either.
- **New — `ephe configure`:** pick and store the engine interactively, once
  (`--force` to choose again) — the way out of the fail-closed abort.
- **A5 — engine visible + connection test in the UI:** the engine tab shows the
  active engine and tests it directly; `/api/health` and `/api/model/providers/probe`
  return a three-valued state `ok | busy | unreachable` (timeout = "busy", not
  "offline"), which the setup and settings UIs display.
- **B1/B2 — docs + hygiene:** The repository guidance and `README.md` now say "the engine choice
  belongs to the user, no silent default" instead of "offline-first by default"; the
  private tailnet hostname is removed from tests, scripts and docs (live tests take
  their endpoint exclusively from `EPHE_DGX_BASE`). Docker Compose declares the
  provider explicitly (`EPHE_MODEL_PROVIDER`).
- **Tests:** new `tests/test_engine_fail_closed.py` plus adapted engine/health/probe
  tests; no test file removed without replacement.

---

## [Unreleased] – 2026-08-21

### Added — Sprint3-G2 injection guard + opt-in sandbox execution (Ephemora Cell)

- **Merge sprint3-g2:** `core/channels/` (pairing allowlist default-empty, bot-token vault
  via keyring/0600, channel approval policy, injection guard: quarantine wrap +
  heuristics + approval safety net) + 35 offline/LIVE-DoD tests. Docs: threat model §6
  (with a note: the Telegram runtime was removed, the layer stays reusable).
- **`run_sandboxed_code`** (`core/tools/sandbox_tools.py`): LLM-generated code as WASM in
  the Ephemora Cell sandbox (no network/exec/fork, fuel/memory/timeout, preopen-deny,
  10-KB cap, execution through `run_isolated()`). Opt-in via `pip install 'ephe[sandbox]'`
  (`ephemora-cell>=1.0.0`, PyPI); without the package it fails closed and exposes no tool
  schema. MCP lane: `ephemora-cell-mcp` through `EPHE_MCP_SERVERS`. Docs: threat model §7 +
  `docs/SANDBOX_EXECUTION.md`; regression: `tests/test_sandboxed_code_tool.py` (10 tests,
  against PyPI-1.0.0).

### Changed — installer mandate: warn-only (no Ollama install, no model pull)

Per the founder mandate (2026-08-21, reaffirmed several times) the installer is **not**
responsible for the AI engine anymore. The one-command install stays flawless for the product
itself (Python runtime via uv with SHA256 verification, PWA build, data folder, server
start). The AI engine is chosen by the **end user** inside the app:

- **`install.sh` / `install.ps1`:** Ollama auto-install + model pull (`gemma4:*`,
  `nomic-embed-text`) removed. Instead: **warn-only** — the installer detects an Ollama
  already installed locally (informational) and states that the engine is chosen in the
  app. No Ollama download anymore, which also drops `OLLAMA_INSTALL_SHA256` (only
  `UV_INSTALL_SHA256` for the Python installer remains).
- **PWA `SetupPage.tsx` (new):** first-run engine selection in the app — local Ollama,
  remote Ollama (e.g. DGX/LAN), or an OpenAI-compatible endpoint — with a live probe
  against `/v1/models` and model choice. Persisted under `~/.ephe/engine.json`.
- **`tests/test_installer_cli.py`:** 9 outdated Ollama install/pull tests replaced by new
  tests of the warn-only contract (31/31 green).

### Fixed

- **DGX model drift (root cause):** `core/engine_config.py::DEFAULT_DGX_SPARK_MODEL`
  from `qwen38-27b-unsloth-nvfp4` → `qwen3.8-27b` — the old id no longer exists on the
  live DGX (verified via `/v1/models`, `max_model_len=262144`). 3 further references
  (ui/app.py, 2 tests) adjusted in sync.
- **Test pollution (root cause, 11 failures):** `tests/conftest.py` gains an
  `autouse` isolation fixture — snapshot/restore of `os.environ` and
  `core.model_provider._ACTIVE_OVERRIDE` per test. Restores hermetic testing for the
  whole provider-pollution class (instead of patching symptoms one by one).
- **CI Python matrix (2 failures):** `.github/workflows/tests.yml` now uses
  `strategy.matrix.python-version: ['3.10','3.11','3.12','3.13']` (lower bound =
  `requires-python`) — resolves the hygiene-test parity violation.

### Security / hygiene

- **Frontend lint hardening:** 4 ESLint errors fixed (`no-self-assign` in
  composerHistory, `no-empty-object-type` in Input, `no-unused-vars` in the
  WorkspaceSidebar test, `@ts-ignore`→`@ts-expect-error` in Button) + 4
  `react-hooks/exhaustive-deps` warnings in ChatLayout (root cause: `sendViaApi`
  unbound + missing `setPendingToolCall` deps). `npm run lint` → exit 0.
- **Dead re-export removed:** `SetupPage.tsx` re-exported `getSetupStatus` (a function
  from `lib/api`) that nobody imported from there (App.tsx uses the `lib/api` import
  directly). Removed → resolves `react-refresh/only-export-components`.

---

## [1.0.0-sprint2] – 2026-08-19

### Added – Sprint 1 launch trust (P0-1 / P0-2 / P0-3)

- **`ephe tool` — approval gates (P0-1, threat model E1):** deterministic tool mode (no LLM loop) with conservative defaults. `SAFE` tools (read-only) are always allowed; `MUTATING`/`NETWORK` tools require explicit release. Flags: `--dry-run` (preview, the file stays untouched), `--yes` (release), `--no` (decline), `--arg K=V` (JSON-parsed), `--json` (machine-readable). Exit codes: 0 = executed/dry-run, 3 = blocked by policy, 2 = usage. `core/tools/approval.py` + 20/20 approval tests (e2e: dry-run/yes/no/non-interactive).
- **Qwen 3.8 27B on DGX Spark as the standard engine (P0-2):** `core/engine_config.py::default_engine_choice()` — the Ephe Tech AI standard engine (Qwen 3.8 27B, `qwen38-27b-unsloth-nvfp4`), no Ollama bundling/download. Provider choice (own endpoint, Ollama, API gateway) = END-USER onboarding via `ephe tui --configure`. Persistence under `~/.ephe/engine.json`; explicit `--model`/`--api-url` flags always win; API keys are never persisted. 22 passed incl. 3 LIVE DGX smoke tests.
- **Security release gate (P0-3):** 0 install-hygiene hits, `npm audit` = 0, Lighthouse 7/7 security audits = 1.0.

### Added

- **`ephe serve`** — OpenAI-compatible engine (phase 3): `server/openai.py` (`create_openai_app`: `/v1/models`, `/v1/chat/completions` with SSE stream + `[DONE]`, auth token, localhost bind by default); `cmd_serve` (`--host/--port/--lan/--token/--model`, `--lan` generates a token, `0.0.0.0`). JCode/Codex/OpenCode use the engine as an OpenAI provider (interop, e2e: `tests/test_jcode_e2e.py`).
- **Hardware-adaptive model router** (`core/model_router.py`): single source of truth for `gemma4:12b ↔ ds4`, transparent per session + `X-Model-*` transparency headers; router wired into serve (missing model → resolve, explicit model → skip).
- **Engine start/onboarding for `ephe tui`**: default = Qwen-DGX standard engine (sprint 1); `--configure` starts the END-USER onboarding (Ollama / own endpoint / OpenAI-compatible); the choice persists to `~/.ephe/engine.json`, explicit flags always win.
- `core/engine_config.py`: `EngineChoice` + atomic `load/save/clear_engine_config`; API keys are never persisted (session env only).
- **Observability** (phase 4, item 15): `core/observability.py` — request-ID middleware (`X-Request-ID`), structured error payloads with stable `code_id`s (usage/validation/auth/stream/runtime/not_found), HTTP exception handlers; wired into `ephe serve` (OpenAI engine) AND the PWA server (`server/main.py`). Tests: `tests/test_observability.py` (11 tests).

### Security

- **install.sh: SHA256 supply-chain integrity (P0-2):** every vendor download (uv, Ollama installer) is verified against pinned SHA256 hashes before execution — a mismatch aborts the installer hard (no blind `curl | sh`). Rotation via `EPHE_UV_INSTALL_SHA256` / `EPHE_OLLAMA_INSTALL_SHA256`.
- **Docker Compose: LAN auth on by default** (`EPHE_LAN=1`) — the container binds to the host interface, which activates auth token + security headers + rate limit (conservative: never open LAN hosting without auth).

### Planned

- Multi-session management (parallel chats)
- Plugin API for external skill packages
- Local embedding model (instead of the ChromaDB default)

---

## [4.0.0] – 2026-04-03

### Added – Artifacts panel
- `core/artifact_detector.py`: regex engine that automatically detects code blocks (≥ 5 lines) in LLM output
- 14 languages supported: Python, Bash, JS/TS, Rust, Go, SQL, HTML, SVG, JSON, YAML, Diff, Markdown
- `app/src/artifact.js`: `ArtifactStore` (versioning) + `ArtifactPanel` (sliding side panel)
- Panel features: syntax highlighting (highlight.js), HTML preview (sandboxed iframe), copy/download, drag-to-resize (320–800px), session history as navigation dots
- SSE events: `artifact` and `replace_text` in the chat stream pipeline
- `main.js` switched to ES modules (`type="module"`)
- TDD suite: 11 BDD tests (Given-When-Then) in `tests/test_artifact_detector.py`

### Added – Visual computer use
- `core/vision.py`: `vision_click` and `vision_type` (PyAutoGUI + Llama vision)
- Screenshot → coordinate calculation → mouse-click execution
- HITL (human-in-the-loop) learning mode: asks for a manual click when unsure
- `core/vision_memory.py`: coordinate learning memory keyed by element label

### Added – Headless browser
- `core/browser.py`: Playwright integration (Chromium, headless)
- Cookie-banner detection via vision + automatic acceptance
- 15,000-character truncation against OOM / context flooding
- `PlaywrightBrowserManager`: singleton with concurrency safety

### Added – Background scheduler
- `core/scheduler.py`: APScheduler integration (cron-based, persistent)
- `server/routes/schedule.py`: REST API (`/api/schedule`)
- Job results persisted in `scheduled_jobs.json`
- Bugfix: route order `/results` before `/{job_id}` (prevents conflicts)

### Added – PWA & mobile
- `manifest.json`: dark theme (`#020504`), shortcuts, display overrides
- `service-worker.js` v5: cache-first for statics, network-only for API/audio
- Auto-update mechanism: "update now" toast ("Jetzt aktualisieren") when a new SW appears <!-- language-gate: ignore — the German toast label this entry records -->
- Mobile zen mode: CSS `mobile-pwa-mode` hides the desktop UI at `≤768px`
- QR-code pairing with a desktop confirmation toast
- PWA icons: real PNG icons (192×512px)

### Added – Voice UX
- `core/transcribe.py`: Faster-Whisper STT (local)
- `/api/audio/transcribe`: WAV upload → transcript
- `/api/audio/tts`: native macOS TTS (no cloud)
- Walkie-talkie mode: automatic read-aloud after voice input
- Waveform visualization during recording

### Added – Skills CRUD
- `server/routes/skills.py`: GET/POST/PUT/DELETE `/api/skills`
- Skills tab in the browser: GUI editor for own skills
- `core/skill_builder.py`: automatic skill generation via `/learn <topic>`
- Skill chips in the chat area (clickable → trigger in the input)

### Fixed
- `main.js` `_queryElements()`: missing `chatArea` and `bottombar` references → crash of all event handlers on desktop fixed
- Null guards for every optional DOM element in `_bindEvents()`
- Service worker cache invalidation: automatic version bump forces a clean refresh

---

## [3.1.0] – 2026-04-02

### Added
- Web interface as the primary frontend (FastAPI + HTML/JS/CSS)
- SSE streaming endpoint (`POST /api/chat/stream`)
- ReAct loop with reflection (automatic quality check + revision)
- ChromaDB vector store (semantic long-term memory)
- User profile (name, expertise, language, communication style)
- Error journal (`core/corrections.py`)
- 👍/👎 feedback store (`core/feedback.py`)
- Thinking-mode visualization (Gemma 4 native reasoning)
- Swarm pipeline: `/swarm` multi-agent execution
- Mobile pairing modal with QR code

### Architecture
- Single codebase: `core/` fully UI-independent
- FastAPI server as a thin SSE layer over `core/`
- Frontend communicates exclusively via REST/SSE

---

## [3.0.0] – 2026-04-01

### Added – ClawDash v3 BlackForest Edition (initial release)
- Async streaming via Ollama AsyncClient
- TUI frontend (Textual): `HistoryInput`, `ChatView`, `StatusBar`
- Slash commands: `/post`, `/debug`, `/idea`, `/explain`, `/commit`
- Extensible command registry (`COMMANDS` dict in `core/commands.py`)
- Session persistence with atomic writes (`tmpfile + rename()`)
- `--model` and `--reset` CLI flags
- Black Forest edition colour palette (`#39ff14` on `#080b08`)
- `Message` TypedDict as the shared contract between all modules
- `pytest-asyncio` test suite (`asyncio_mode = auto`)

### Architecture
- Modular structure: `core/` (pure async, no UI) + `ui/` (Textual)
- Workers communicate via `post_message()` (thread-safe)

---

*Ephe – Bad Liebenzell, Black Forest*  
*No cloud. No tracking. Straight from the Black Forest. 🌲*
