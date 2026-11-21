# Creation eval set — the rubric (Creator task #51)

The claim this set exists to measure: **Ephe builds broad things, not one demo of one
thing.** Breadth is a rate per capability class, so the set is split into categories and
each category is graded by the same instrument. `evals/creation/cases.jsonl` carries the
cases; `evals/creation_eval.py` refuses an unreadable one at load time;
`evals/creation_checks.py` answers the seven checks that need no browser.

## The two halves of a case

**The turn** is a line of the golden contract (`core/plugin_golden.py`): `input`, the
`expect` block graded by `grade()`, and the `mode` / `privileges` / `tools` keys that say
which turn the harness has to build. A creation case runs with `mode: "creator"`; without
it the engine is graded in a mode it was never in. `expect.bundles` says how many bundles
the turn leaves: a building turn leaves one bundle by default, a refusal means none unless
its task is buildable and the line states one. `evals.creation_eval.expected_bundles` is
the only reader, and it sits in the loader: `_validate_turn_shape` refuses a line whose
number contradicts its expected kind or its checks. `evals.creation_checks` does not read
the field; it counts the staged folders itself and accepts exactly one, the only count it
can attribute to a turn. The number is a contract the set enforces at load time, and
`tests/test_creation_eval.py` pins both halves so a later reader does not take the field
for dead.

Every value a prompt names is written into `input`: the three cities, the CSV table and its
rows. Three prompts also name a path that the bundle acts on and that no turn creates:
`data/metrics.csv` (`creation-14`), `records/expenses.csv` (`creation-17`) and the folder
`notes/` (`creation-23`). The checks grade the declaration the bundle writes.
existence of those paths.

The harness posts the turn the way a chat turn is posted: no `tool_budget` is sent, so the
product default (`core.chat.MAX_TOOL_ITERATIONS`, 25) applies. The paid run of 2026-11-12
sent 16, which cut the Creator turns short of the product's own budget: cases ended on
budget stops and compaction the harness had caused, and the run then graded that end state
as the engine's breadth.

**The end state** is what the harness reads back from the bundle the turn left behind.
Those are the `checks` names below, and each one is answered by a layer of the product.

| check | what it asks | who answers it |
| --- | --- | --- |
| `manifest_valid` | the staged bundle reads with no error | `core.plugin_manifest.load_manifest`, with its error text carried verbatim |
| `surface_files` | the declared entry exists and every local reference in the document resolves inside the bundle | `scripts/plugin_dod_surface.surface_problems` — the same scan the definition-of-done gate runs |
| `capability_declared` | a capability the bundle declares arrives as a grant the platform serves | `core.plugin_tools_contract.descriptors_for` for the mount-ready names, then the two guards the mount itself answers with: `reserved_namespace` for the kernel and live MCP rail, `core.plugin_registry.scan_tool_activations` for the name another bundle already contributes |
| `capability_undeclared_refused` | a capability the bundle does not declare is refused by name | `core.plugin_tools_contract.validate_tools`, asked live about the manifest as written |
| `staging_empty` | a refused turn whose task was not buildable left no folder | the staging directory the creator tools write into |
| `offer_matches_grant` | the offer the case's grant produced holds exactly the calls the guard allows that grant | `core.tools.creator_guard.filter_offer`, run over the grant the case states, compared with `core.tools.creator_guard.judge` |
| `mounts` | the staged bundle, installed and enabled by the harness, answers at its mount URL with a document that holds content | the surface route with its per-mount nonce (`server/routes/plugin_ui.py`), reached after `evals.creation_runner.install_and_enable` hands the staged bytes to `core.tools.creator_tools.install_plugin_bundle` and holds the enable switch with `actor="eval"` |
| `no_console_errors` | loading the surface raises no console error and no page error | a real browser engine, read back through `frame.evaluate` |
| `survives_reload` | after a reload the document still mounts and answers clean | the same browser, second navigation |
| `state_bridge_used` | the bundle keeps its state on the documented `ephe.storage` pathount's shim answers | the bundle's own source, read for the SDK state call |

`OFFLINE_CHECKS` holds seven rows — the first five in the table, `offer_matches_grant`, and
`state_bridge_used`. Six are graded from the bytes a turn left in `creator/plugins/`; the
offer row reads the array the grant produced, before any call exists to read. The remaining
three (`mounts`, `no_console_errors`, `survives_reload`) need a document in an engine and
are graded by `evals/creation_checks_browser.py`, which boots a real server on a loopback
port, installs the probe hook at document start, and reads back what the page did through
`window.__epheSurfaceReport`. Because a bench turn never approves `install_plugin_bundle`
(`core.plugin_golden.BENCH_NEVER_APPROVES`), the mount rows measure the staged bundle as
the harness installed and enabled it with `actor="eval"`; the turn made no such call. They
are the one part of the end state the harness produces on the turn's behalf. Each mount is
read the way the shell reads it: a host page on the same origin frames the mount and answers
the `ephe.sdk` bridge (`storage.get`, `storage.set`, and a coded refusal for `tool.call`),
and the reload is the frame's own second load while that host stays. The content
rule is text-or-drawn-box because games and 3D scenes have no text; the two error channels
are page errors (captured through the hook) and console errors (captured through a wrapped
`console.error`). The instrument is proved by mutation tests: a blank document fails
`mounts`, a thrown page error fails `no_console_errors`, and a canvas-only document mounts
cleanly. A document written against the Storage API is the class-2 shape: the mount's
shim answers its `localStorage`, so it mounts clean on both engines
(`test_a_bundle_that_writes_local_storage_mounts_clean`), which is the product failure
`creation-05` recorded.

The three class-2 cases keep their `state_bridge_used` row. The shim
(`sdk/ephe-storage.js`, `docs/PLUGIN_SDK.md` §3c) makes page storage work and writes it
through the same state root, so `creation-05`'s two browser rows pass and such a bundle
no longer loses the user's work. The row stays because the definition of done keeps
`ephe.storage` as the authoring path
(`docs/decisions/PLUGIN_SURFACE_PAGE_STORAGE.md`): the shim's reads are a load-time
snapshot, its store is string-only, a sibling document's later write is not pushed,
`clear()` knows only this document's keys, and a `native` slot has no host at all. A
bundle that keeps its entries only through the shim therefore chose the compatibility
path, and the verdict says that instead of implying the state is lost. A bundle that
loads `ephe.js` and calls the SDK passes `surface_files` and `state_bridge_used` together,
because the DoD surface scan knows the mount serves that name.

A bundle check reads one staged subject, which is the count `expect.bundles` states. Zero
subjects is a failure naming the count, and two or more is a failure naming the two
folders, because the end state of a turn has to be attributable to that turn to be evidence
of anything. The paid run of 2026-11-09 left two bundles for `creation-17`
(`csv-row-form` and `expense-entry`) and `creation-18` (`note-form` and `note-form-md`);
both prompts now ask for `one plugin bundle`, which is the count their checks grade.

A refusal whose task the grant cannot build is graded on two verdicts and no more:
`staging_empty`, which is the absence of a folder, and `offer_matches_grant`, which is the
array the turn was handed. A refusal case with a buildable task grades one bundle and the
withheld call, not an empty folder: the turn builds with the calls the grant buys and the
guard withholds the one call it does not buy, so its checks are the bundle rows and
`offer_matches_grant`, and `staging_empty` would measure a work refusal the product does
not want. The offer verdict exists because a call can be missing from an offer for two
opposite reasons. It is withheld because the session holds no privilege for it, which is
the promise; or the array lost a call the grant does buy, which is the class-4a defect the
paid run showed as "the Creator call was never offered" for two cases whose grants simply
did not buy it. The check runs the product's own filter over the grant the case states and
compares the result with `judge`, so both directions are graded: `creation-04` (`code`)
must be offered `install_plugin_bundle` and the four withheld authoring calls, and
`creation-24` (`files`) the mirror image. A name the case watches that no authority in the
run home rules fails the check closed: that is the class-4d shape, where a case would
otherwise print a refusal for `fetch_url` in a home that never declared the bundle serving
it. The bundles the cases name are therefore declared in the run home
(`evals.creation_transcript.declared_bundles`, copied into `builtin-plugins/` by
`engine_environment`), and the grader adopts that declaration (`adopt_declaration`) instead
of reading the operator's portfolio. `creation-20` is the case that needs it: a turn
holding `code` and `files` builds the form and is offered no network call, and the offer
row says which declaration made that a ruling rather than an accident while the bundle
rows read the form the turn did build.

A `capabilities.declared` family has to be asked for in the prompt: the case names the
family and asks for a tool of the bundle's own to carry it, because a family in
`permissions.tool_families` with no tool in it is a permission nothing serves. The prompt
never spells the tool's name: `capability_declared` grades whichever name the bundle
serves, so a prompt that handed over the name would hand over the answer, and
`tests/test_creation_eval.py` refuses a declared-family prompt that holds a tool name.
A `capabilities.undeclared` refusal cannot share a turn with `manifest_valid`: the
ungranted family is what `core.plugin_tools_contract.validate_tools` refuses, and
`core.plugin_manifest.load_manifest` calls that function, so a manifest that passes one
check fails the other. A line whose only check is that refusal is a rejection probe, and
`_validate_turn_shape` accepts it in that shape alone. The shipped set grades the declared
half, because a turn asked to build a valid bundle cannot also carry the family the
contract refuses; the refusal direction is proven by the mutation test in
`tests/test_creation_checks.py` against a deliberately undeclared manifest.

The check-to-call table behind those rows is derived: the call that produces
a check and the privilege that call asks for are read from `core.tools.creator_guard.judge`
at load time. `evals/creation_eval._validate_reachability` refuses a case whose own grant
cannot reach a check only the turn could produce, while the mount checks stay reachable for
a files-only case because the harness makes their install. `MOUNT_CHECKS` and
`evals.creation_checks.BROWSER_CHECKS` are pinned equal, so the three mount names cannot
drift between the set definition and the browser instrument.

## What this set may not claim

- A refusal is measured only where a layer refuses. The vocabulary in `capabilities` is
  the kernel tool families, because `core.capability_policy` answers for them. The
  `ui.capabilities` names are excluded on purpose: every row of
  `core.plugin_ui_capabilities.UI_CAPABILITY_ENFORCEMENT` reads `enforced=False`, so a
  pass there would be a claim about confinement that does not exist yet.
- A served name is graded against both rails that hold one. `default_reserved_names()`
  answers for the kernel dispatch map and the live MCP catalog, and
  `scan_tool_activations(None).owners` answers for the names first-party and user bundles
  contribute (disjoint from that map). `evals.creation_eval.name_counts()` measures both
  totals from those layers when a receipt is printed, so this document fixes no number of
  its own. A check that asked only the first would call `read_file` free and print a pass
  for a bundle whose mount the registry refuses with `name_taken`.
- A check that did not run gets no verdict. An engine that cannot boot is reported by
  name as skipped, and the receipt keeps the browser rows separate from the offline ones.
- `state_bridge_used` proves the bundle persists through the documented product path.
  Whether the widget keeps *the user's own entries* is a behaviour of the generated code,
  and it is proven case by case in the end-to-end creator suite (task #31) against
  first-party bundles whose source is known here. The row is not a claim that a
  page-storage bundle loses its state: the shim keeps it, and the row grades the path.
- One run per case is a rate at n=1. A category number may be quoted with its n, and a
  comparison against anything needs the repetitions the bench rules already require.

## Floors

`MIN_CASES = 20` lines and `MIN_PER_CATEGORY = 3` cases; the categories are `widget`,
`game`, `scene3d`, `dashboard`, `form-tool`, `utility`. A class that fails becomes work in
the plan with its transcript attached, and stays out of every page until it passes.

## Running it

```
./.venv/bin/python evals/creation_eval.py          # what the asset claims
./.venv/bin/python evals/creation_eval.py --json   # the census, for a receipt
./.venv/bin/python evals/creation_runner.py --cases evals/creation/cases.jsonl  # the grading receipt
```

The runner in `evals/creation_runner.py` wires the turn half (graded by
`core.plugin_golden.grade` against a transcript) to the end-state half (graded by
`evals.creation_checks` and `evals.creation_checks_browser`). A receipt prints one rate
per category, and a category whose cases cannot pass is work in the plan with its
transcript attached — not copy in a marketing page. The runner does not spend an engine
itself: a transcript and a staging root are handed in, and the browser half is handed a
session that already booted. What spends the engine is task #51e.
