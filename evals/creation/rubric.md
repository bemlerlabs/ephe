# Creation eval set — the rubric (Creator task #51)

The claim this set exists to measure: **Ephe builds broad things, not one demo of one
thing.** Breadth is a rate per capability class, so the set is split into categories and
each category is graded by the same instrument. `evals/creation/cases.jsonl` carries the
cases; `evals/creation_eval.py` refuses an unreadable one at load time;
`evals/creation_checks.py` answers the six end-state checks that need no browser.

## The two halves of a case

**The turn** is a line of the golden contract (`core/plugin_golden.py`): `input`, the
`expect` block graded by `grade()`, and the `mode` / `privileges` / `tools` keys that say
which turn the harness has to build. A creation case runs with `mode: "creator"`; without
it the engine is graded in a mode it was never in. `expect.bundles` says how many bundles
the turn leaves: a bundle turn leaves one bundle by default, and a refused turn leaves
none. `evals.creation_eval.expected_bundles` is the only reader, and it sits in the
loader: `_validate_turn_shape` refuses a line whose number contradicts its expected kind.
`evals.creation_checks` does not read the field; it counts the staged folders itself and
accepts exactly one, the only count it can attribute to a turn. The number is a contract
the set enforces at load time, and `tests/test_creation_eval.py` pins both halves so a
later reader does not take the field for dead.

Every value a prompt names is written into `input`: the three cities, the CSV table and its
rows. Three prompts also name a path that the bundle acts on and that no turn creates:
`data/metrics.csv` (`creation-14`), `records/expenses.csv` (`creation-17`) and the folder
`notes/` (`creation-23`). The checks grade the declaration the bundle writes, not the
existence of those paths.

**The end state** is what the harness reads back from the bundle the turn left behind.
Those are the `checks` names below, and each one is answered by a layer of the product.

| check | what it asks | who answers it |
| --- | --- | --- |
| `manifest_valid` | the staged bundle reads with no error | `core.plugin_manifest.load_manifest`, with its error text carried verbatim |
| `surface_files` | the declared entry exists and every local reference in the document resolves inside the bundle | `scripts/plugin_dod_surface.surface_problems` — the same scan the definition-of-done gate runs |
| `capability_declared` | a capability the bundle declares arrives as a grant the platform serves | `core.plugin_tools_contract.descriptors_for` for the mount-ready names, then the two guards the mount itself answers with: `reserved_namespace` for the kernel and live MCP rail, `core.plugin_registry.scan_tool_activations` for the name another bundle already contributes |
| `capability_undeclared_refused` | a capability the bundle does not declare is refused by name | `core.plugin_tools_contract.validate_tools`, asked live about the manifest as written |
| `staging_empty` | a turn that was refused left no bundle behind to mount | the staging directory the creator tools write into |
| `mounts` | the staged bundle, installed and enabled by the harness, answers at its mount URL with a document that holds content | the surface route with its per-mount nonce (`server/routes/plugin_ui.py`), reached after `evals.creation_runner.install_and_enable` hands the staged bytes to `core.tools.creator_tools.install_plugin_bundle` and holds the enable switch with `actor="eval"` |
| `no_console_errors` | loading the surface raises no console error and no page error | a real browser engine, read back through `frame.evaluate` |
| `survives_reload` | after a reload the document still mounts and answers clean | the same browser, second navigation |
| `state_bridge_used` | the bundle persists through the plugin state path rather than its own page storage | the bundle's own source, read for the SDK state call |

`OFFLINE_CHECKS` holds six rows — the first five in the table plus `state_bridge_used` —
and all six are graded from the bytes a turn left in `creator/plugins/`. The remaining
three (`mounts`, `no_console_errors`, `survives_reload`) need a document in an engine and
are graded by `evals/creation_checks_browser.py`, which boots a real server on a loopback
port, installs the probe hook at document start, and reads back what the page did through
`window.__epheSurfaceReport`. Because a bench turn never approves `install_plugin_bundle`
(`core.plugin_golden.BENCH_NEVER_APPROVES`), the mount rows measure the staged bundle as
the harness installed and enabled it with `actor="eval"`; the turn made no such call. They
are the one part of the end state the harness produces on the turn's behalf. The content
rule is text-or-drawn-box because games and 3D scenes have no text; the two error channels
are page errors (captured through the hook) and console errors (captured through a wrapped
`console.error`). The instrument is proved by mutation tests: a blank document fails
`mounts`, a thrown page error fails `no_console_errors`, and a canvas-only document mounts
cleanly.

A bundle check reads one staged subject, which is the count `expect.bundles` states. Zero
subjects is a failure naming the count, and two or more is a failure naming the two
folders, because the end state of a turn has to be attributable to that turn to be evidence
of anything. The paid run of 2026-11-09 left two bundles for `creation-17`
(`csv-row-form` and `expense-entry`) and `creation-18` (`note-form` and `note-form-md`);
both prompts now ask for `one plugin bundle`, which is the count their checks grade.

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
- `state_bridge_used` proves the bundle persists through the product path. Whether the
  widget keeps *the user's own entries* is a behaviour of the generated code, and it is
  proven case by case in the end-to-end creator suite (task #31) against first-party
  bundles whose source is known here.
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
