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
| Planner | Kernel loop; a plugin names the plan strategy since PLAN-P1 | `core/plugin_planner_contract.py:161` `validate_planner` → `core/plugin_runtime.py:356` `plan_strategies` → `core/ephe_plan.py:84` `plan_strategy`, clamped at `:157` `_step_budget`; the loop stays `core/react.py:170` `react_loop` | a step schema with a reader: the guard text still instructs one shape, so nothing fails a plan that ignores a declared field | L (first cut landed) |
| Evaluator | Kernel grader; the bundle supplies cases and, since EVAL-P1, names presets of the kernel's own kinds | `core/plugin_golden.py:249` `grade`, `:193` `load_golden`, `:163` `_declared_kinds`, `:579` `measure_matrix`; contract `core/plugin_evaluator_contract.py:224` `validate_evaluator`, `:260` `evaluator_kinds` | a grader or a new `expect.kind` a manifest could add: the vocabulary stays the kernel's five primitives, and a preset resolves only inside the suite that declares it | L (first cut landed) |
| UI | Plugin for the surface, kernel for the shell; the placement first cut landed | `core/plugin_ui_capabilities.py:302` `validate_ui`, `server/routes/plugin_ui.py:73` router, `app/src/lib/surfacePlacement.ts` placement resolver, `core/plugin_surface_host.py` slot record | the shell's own pages and component slots: a bundle declares one placement from the closed list (`floating-window`, `canvas-overlay`, and `dock-panel` once a dock exists) and still cannot register into the app's tree or name a slot the shell does not own | L (first cut landed) |
| Runtime | Kernel by design | `core/plugin_runtime.py:360` `tool_gate`, `core/plugin_lifecycle.py` state machine, `core/plugin_lifecycle_mount.py:92` `mount` | a turn hook: `components.hooks` is reserved; the live hook API is the process-wide `~/.ephe/hooks.json` (E5); a bundle has none | L |
| Commands | Plugin | `core/plugin_manifest.py:231` `manifest_commands`, `core/plugin_commands.py:26` | none | — |
| Skills | Plugin (pack tree the manifest lists) | `core/plugin_manifest.py:217` `active_skill_roots`, `core/skills.py:638` | none; a pack is a directory with `SKILL.md`, never code | — |

The start suspicion held for planner, evaluator and runtime, and not for tools, commands,
skills or the surface half of UI. Memory was the class with a kernel seam already written
and a hardcoded enrolment list on top of it, which is why it moved first. Planner was the
class whose seam was a constant — `MAX_PLAN_STEPS` read at every plan construction — so its
first cut is the budget and the step vocabulary, and its second cut is the reader those
fields still lack (`capabilities.planner`, PLAN-P1, below).

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
   inspectable live; ephe ships at most one HTML document per bundle, placed by
   `components.ui.type` among the placements the shell owns (its window, the overlay
   stack, and a docked region once one exists), with the capability list for that
   document and no registration API.
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

## The next cut: `capabilities.planner` (PLAN-P1)

Planner was the cheapest of the three Ls because of where it decides: not in the loop, in a
constant. `core/ephe_plan.py` reads `MAX_PLAN_STEPS` in every constructor and `EpheStep`
fixes which fields a step carries, so a bundle can name a plan dialect around a plan the
kernel still builds. A strategy answers two questions and no more: how many steps may this
plan grow to, and which fields does a step carry here. The loop, the repair budget per
step, the abort on an exhausted budget, the checkpoint anchor, the rendered block and the
SSE payload stay the kernel's — the client parses `{"state", "done", "total", "steps"}`,
and a strategy cannot add a fifth key to it.

`capabilities.planner` is one object in a version 2 manifest: `strategy` (a lowercase slug;
`checklist` and `ledger` are the kernel's own plan sources and stay reserved),
`step_budget` (a whole number inside `MIN_PLAN_STEPS..MAX_PLAN_STEPS`, read off the plan
core at load time so the contract cannot drift from the clamp), `step_schema` (a subset of
the plan core's step fields — `title`, `evidence`, `mutating`; `title` is required because
a step without one is not a step), and `description`. No permission family is asked for and
none is granted: a strategy is configuration the kernel enforces, so it opens no file, no
socket and no subprocess. The risk it carries is a tighter plan, which is why the budget
narrows the kernel's window and cannot widen it.

The shape, in four steps that each have a test:

- The contract (`core/plugin_planner_contract.py:161`): the section above, fail-closed, in
  the same list style as `capabilities.memory` — an unknown field, a reserved id, a budget
  outside the window, a field the plan core does not carry, a schema without `title` and a
  blank description each quarantine the whole bundle.
- The registration (`core/plugin_runtime.py:356`): the same manifest scan the tool gate
  reads, cached and invalidated with it, so a mount or an edit retires the table. One id
  claimed twice is contested; contested and unknown answer alike.
- The resolution (`core/ephe_plan.py:84`): the `EPHE_PLAN_STRATEGY` pin, then the one
  strategy an active bundle declares, then the kernel's own. A bundle that is switched off
  takes its dialect with it, and two bundles that declare different dialects contradict
  each other, so neither governs. Every refusal falls back to the kernel and logs a line.
- The clamp (`core/ephe_plan.py:157`): the declared budget is read again against
  `MAX_PLAN_STEPS` at every construction, so even a strategy no manifest validation saw
  cannot raise the ceiling. `MAX_REPAIRS_PER_STEP` and the abort are untouched.

What the first cut does not do is give the step schema a reader. `step_schema` is validated
against the plan core's own fields and recorded on the plan (`EphePlan.strategy`), and the
kernel acts on exactly one of them today: `title`. The reader that would make the rest mean
something is the guard text in `core/persona.py`, which still tells the model four to eight
steps and no step shorter than twelve characters. With that reader a declared schema becomes
an instruction the same turn obeys, and the row's L is spent; until then this doc says
declared and recorded, and the tests pin that no surface moved.

Verification: 23 characterisation tests in `tests/test_ephe_plan_characterisation.py`, green
before the change and after it; 47 tests in `tests/test_plugin_planner_strategy.py`, 46 of
them red before the implementation and all green after; `pytest tests/ -k "plan or plugin or
manifest"` reports 1478 passed, 1 skipped.

## The next cut: `capabilities.evaluator` (EVAL-P1)

The evaluator was the cheapest of the three Ls because its seam was a vocabulary. The
pass³ matrix, the engine resolution, the mode and privilege handling, the case schema and
the receipt are the kernel's, and a bundle's suite was already the one place a bundle wrote
its own claims. What it could not do was name a check: the five kinds were a tuple in
`core/plugin_golden.py`. A preset answers one question — which kernel primitive a case in
this bundle's suite grades with, and with which fragments — so the seam moves the
vocabulary and leaves the instrument where it is.

`capabilities.evaluator` is one object in a version 2 manifest:
`kinds` holds one to eight entries, each with `id` (a lowercase slug; the five kernel kind
names stay reserved), `from` (`contains` or `not_contains` in this cut), `any` (the
fragments, each at least three characters) and `description`. A case names the preset in
`expect.kind` and passes nothing else, so the manifest is the one place the fragments are
written. No permission family is asked for and none is granted: a preset is data the
grader reads, so it opens no file, no socket and no subprocess.

The shape, in four steps that each have a test:

- The contract (`core/plugin_evaluator_contract.py:224` `validate_evaluator`): the list
  above, fail-closed in the same style as `capabilities.memory` and `capabilities.planner`
  — an unknown field, an unknown or reserved id, a duplicate id, a base outside this cut,
  a missing or malformed argument, a fragment shorter than three characters and a blank
  description each quarantine the whole bundle. `argument_error` is the per-kind argument
  rule, and `core/plugin_golden.py` calls the same function for a case, so the two readers
  cannot drift apart.
- The resolution (`core/plugin_golden.py:163` `_declared_kinds`): the manifest beside the
  suite the loader reads, once per suite, through `validate_evaluator`. A preset resolves
  only inside the bundle that declares it, so a pass³ number never depends on which other
  bundles are installed and no id can be contested. A bundle with no readable manifest
  declares no presets, and a case that names one is refused as an unknown kind.
- The matcher (`core/plugin_golden.py:249` `grade`): the loader puts the resolved
  primitive beside what the author wrote — `matcher` holds the primitive and its
  arguments, `kind_source` names the declared id or `kernel` — and `grade` reads the
  matcher. `measure_matrix` and `pass3_matrix` rows carry both, and the anti-slop gate in
  `verify_all` tests the resolved primitive, so a declared `not_contains` preset satisfies
  it and a declared `contains` one does not.
- The two holes that were open in the case validator: `expect.any` accepted an empty
  string, so `contains: [""]` always passed, and a case could carry a hand-written
  `matcher` that no manifest declared. The first is now refused for every string kind
  (blank fragments, and a blank member beside a valid one), the second is refused by name
  at load time, and a case that names a declared kind may not restate its arguments.

What the first cut does not do is widen the vocabulary: `artifact`, `tool_use` and
`tool_refused` presets and composition (`all_of` / `none_of`) are the second cut, and the
field names for their arguments are already reserved so a manifest written for them is
refused for its `from`. A bundle still cannot add a primitive, shadow a kernel kind name,
grade another bundle's suite, satisfy the anti-slop gate with a base other than
`not_contains`, or change what the engine is asked.

Verification: 49 tests in `tests/test_plugin_evaluator_kinds.py`, 41 of them red against
the previous `core/plugin_golden.py` (the eight that were green read the new contract
module directly, which a red-first run cannot count); `ephe bench` exits 0 with the same
153 cases across the same 17 bundles, so the shipped matrix did not move; the golden,
memory and planner suites are green before and after.

## Open, in the order the table costs them

- The settings surface still offers the two kernel ids only (`server/routes/memory.py:201`
  `Literal["kepta", "kepta-bridge"]`); a declared provider is reachable through
  `EPHE_MEMORY_PROVIDER` and through the record, and the route is an S.
- The planner step schema has no reader yet, and the settings surface has no planner
  section: a bundle's own lifecycle and `EPHE_PLAN_STRATEGY` are the only switches. The
  evaluator's first cut names presets of the kernel's five primitives; `artifact`, `tool_use`
  and `tool_refused` presets plus composition are its second cut, and no surface lists a
  declared preset yet. Client slot registration's first cut has landed: both product surfaces
  honor `components.ui.type` through `app/src/lib/surfacePlacement.ts`, and `dock-panel` is a
  coded refusal until the shell owns a docked region. A runtime turn hook stays kernel; each
  remaining seam is an L and wants its own contract module before any code moves.
- A second memory transport (anything but `kepta-bridge`) is a new wire contract with its
  own tests; the vocabulary stays closed until one is written down.
