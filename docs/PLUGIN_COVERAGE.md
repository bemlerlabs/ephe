# Plugin coverage — what a bundle can extend today

Read one decision line per capability class: the place where the kernel decides what
exists, and whether a manifest can put something there. Evidence is `file:line` in this
tree; effort is the size of the missing seam (S: one contract module plus tests,
M: contract + runtime registration + one lifecycle read, L: touches the turn loop, the
grader or the client shell).

## Audit

| Capability class | Today | Evidence | Missing extension point | Effort |
|---|---|---|---|---|
| Tools | Plugin | `core/plugin_tools_contract.py:137` `validate_tools` → `core/tools/dynamic_registry.py:289` `register` → `core/sandbox/runner.py:256` `run_plugin_tool`; gate `core/plugin_runtime.py:360` | none on the rail; a kernel tool has no manifest route *out*, which is the one-name-one-provider rule, not a gap | — |
| Memory | Plugin since MEM-P1 (provider); the stores stay kernel | `core/plugin_memory_contract.py` `validate_memory` → `core/plugin_runtime.py:322` `memory_providers` → `core/memory_provider.py:169` `resolve_provider`, `:256` `open_provider` | in-process provider code: only the `kepta-bridge` wire protocol is declarable, because nothing imports plugin code (ruling A1) | M (done) |
| Planner | Kernel | `core/ephe_plan.py:31` `MAX_PLAN_STEPS`, `core/react.py:170` `react_loop`, `core/chat.py:180` `chat_with_tools` | a plan strategy a manifest could name (step budget, repair budget, step schema) | L |
| Evaluator | Kernel grader; the bundle supplies cases | `core/plugin_golden.py:171` `grade`, `:120` `load_golden`, `:509` reads `prompts/golden.jsonl` | a grader or `expect.kind` a manifest could add; the vocabulary is closed inside the grader | L |
| UI | Plugin for the surface, kernel for the shell | `core/plugin_ui_capabilities.py:302` `validate_ui`, `server/routes/plugin_ui.py:73` router, `core/plugin_surface_host.py` slot record | the shell's own pages and component slots: a bundle cannot register into the app's tree, only ship one framed document | L |
| Runtime | Kernel by design | `core/plugin_runtime.py:360` `tool_gate`, `core/plugin_lifecycle.py` state machine, `core/plugin_lifecycle_mount.py:92` `mount` | a turn hook: `components.hooks` is reserved; the live hook API is the process-wide `~/.ephe/hooks.json` (E5); a bundle has none | L |
| Commands | Plugin | `core/plugin_manifest.py:231` `manifest_commands`, `core/plugin_commands.py:26` | none | — |
| Skills | Plugin (pack tree the manifest lists) | `core/plugin_manifest.py:217` `active_skill_roots`, `core/skills.py:638` | none; a pack is a directory with `SKILL.md`, never code | — |

The start suspicion held for planner, evaluator and runtime, and not for tools, commands,
skills or the surface half of UI. Memory was the class with a kernel seam already written
and a hardcoded enrolment list on top of it, which is why it is the one that moved.

## Against the Cordis model (DeepSeek Harness)

The reference is a Cordis loader: a plugin is an npm package plus a `cordis.patch.yml`
row, installed with `plugin_manager install_bundle`, with Host halves (Service, Tool,
Config as JSON Schema — `cordis_inspect_query` shows `Service`, `Event`, `Config`,
`Tool`) and Client halves registering into live Slots (`Slots`, `Builtin`, `Theme`).

1. Unit and packaging: Cordis composes npm packages through ordered patch layers
   (`insert`, `override` by id, `group`, `disabled`, `!!js`); ephe has one folder with one
   `ephe-plugin.json` and no patch dialect — a manifest is the whole contribution, and
   nothing inherits from another bundle.
2. Host half: a Cordis Host plugin exports code (`lib/index.js`, `lib/types`) and takes a
   typed Config; an ephe host half is declarative only. A tool is a `path.py:callable`
   string run in a confined worker, so a bundle cannot export a Service, an Event or a
   Config schema into the backend.
3. Client half: Cordis registers components into named Slots at runtime and the tree is
   inspectable live; ephe ships at most one HTML document per bundle in a window slot
   (`components.ui`), with the capability list for that document and no registration API.
4. Configuration: Cordis validates each entry's Config against a JSON Schema at mount
   time; ephe validates the whole manifest fail-closed at load time. The two are not the
   same instrument: ephe refuses the bundle, it does not coerce a field.
5. Install versus activation: Cordis `install_bundle` writes rows and each row's `disabled`
   decides mounting; ephe installs into the catalog and keeps the bundle off until a mount
   commits. There is no ephe equivalent of a loader layer that re-enables one shipped row.
6. Trust: Cordis identity is the package name, version and engines range; ephe adds ES256
   signatures over a canonical content hash, a contract pin and a content digest per mount
   (`core/plugin_signing.py`, `core/plugin_lockfile.py`), while the loader's answer to a
   changed artifact is to read it again.
7. Isolation: Cordis `isolate` scopes *service instances* inside one host process; ephe
   keeps tool code out of the process entirely (seatbelt/bubblewrap, JSON on stdin/stdout),
   which is why a memory provider here has to be a wire protocol and not a Python entry.
8. Failure semantics: a Cordis patch row that matches nothing is warned about and skipped;
   ephe quarantines the whole bundle on one bad field and hides a name two bundles claim
   from both of them. A bad row loses a row; a bad bundle loses the bundle.

## The cut that was made: `capabilities.memory` (MEM-P1)

Memory was chosen over the evaluator for three reasons. It already had a seam — one
facade, two providers, `VALID_PROVIDERS` — so the smallest honest change was making *that
enrolment list* extensible rather than inventing a subsystem. The evaluator's grader is
the instrument that measures every other claim in this tree (golden matrices, pass³, the
Cordis comparison above), and its run path is a whole turn with engine, mode and
privilege handling, so a plugin-loadable grader would weaken the check that guards the
rest; it is also an L. And memory is the class where the owner's "one capability, one
plugin" promise costs a user nothing when the seam is wrong: the kernel default stays
`kepta`, the plugin is reachable only by explicit choice, env or record.

The shape, in four steps that each have a test:

- The contract (`core/plugin_memory_contract.py`): one descriptor under
  `capabilities.memory` in a v2 manifest — `id`, `transport` (`kepta-bridge` only), `url`,
  `scope`, `description`. Kernel ids are reserved, the URL must be http(s) without
  credentials or fragment, and `permissions.tool_families` must declare `network`.
- The registration (`core/plugin_runtime.py:322`): the same manifest scan the tool gate
  reads, cached and invalidated with it, so a mount or an edit retires the table. One id
  claimed twice is contested; contested and unknown answer alike.
- The resolution (`core/memory_provider.py:169`): `persist_dir`/`collection_name` → explicit
  → `EPHE_MEMORY_PROVIDER` → written record → fresh install, unchanged. A plugin name is
  accepted at three of those steps and never adds a step: a memory across the network stays
  an opt-in, and a record naming a switched-off bundle survives instead of being rewritten.
- The opening (`core/memory_provider.py:256`): the declared URL and nothing else; plugin
  code is never imported, and the `transport` seam is the bridge's own test hook.

Verification: 41 tests in `tests/test_plugin_memory_provider.py` (34 red before the
implementation, 41 green after) and 18 characterisation tests in
`tests/test_plugin_manifest_characterisation.py` that were green before and after
`core/plugin_manifest.py` was split under the 400-line gate (450 → 250 lines, the contract
in `core/plugin_manifest_contract.py`). `pytest tests/ -k "plugin or manifest or memory"`
reports 1525 passed, 2 skipped.

## Open, in the order the table costs them

- The settings surface still offers the two kernel ids only (`server/routes/memory.py:201`
  `Literal["kepta", "kepta-bridge"]`); a declared provider is reachable through
  `EPHE_MEMORY_PROVIDER` and through the record, and the route is an S.
- Planner, the evaluator grader kinds, a runtime turn hook and client slot registration
  stay kernel; each is an L and each wants its own contract module before any code moves.
- A second memory transport (anything but `kepta-bridge`) is a new wire contract with its
  own tests; the vocabulary stays closed until one is written down.
