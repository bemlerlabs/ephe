# Decision: page storage inside a plugin surface

- Status: decided (2026-11-09) — **Option C, the page-storage shim**. The two options
  weighed below were both rejected: A for the authority it spends, B because the owner's
  order is that an existing bundle keeps its state instead of being regenerated.
- Raised by: the paid creation run, whose three bundles wrote `localStorage` from a mounted surface
- Touches, under Option C: `server/plugin_surface_storage.py`, `server/routes/plugin_ui.py`,
  `core/plugin_state.py` (one read-only accessor), `sdk/ephe-storage.js`, and the browser
  and unit tests beside them. Under Option A: `server/plugin_surface_policy.py` and
  `app/src/components/shell/OverlayHost.tsx`; under Option B: `scripts/plugin_dod_surface.py`
  and the creator guidance.

## Decision (2026-11-09): Option C — a shim over the bridge, never the origin

The sandbox stays exactly as it is: `sandbox allow-scripts allow-popups`, no
`allow-same-origin`, opaque origin, and the isolation suite keeps measuring that a null
origin reads none of the user's authority. What the mount adds is the API:

- The route serves `sdk/ephe-storage.js` under a reserved name (a bundle file of the same
  name is ignored, like `ephe.js`).
- The document is served with that script plus a `type="application/json"` data block
  holding **this bundle's own** page store, placed directly after the doctype so it runs
  before the bundle's first script. The block is escaped (`\u003c` and friends), so a
  stored value can never close it.
- Reads are synchronous from that snapshot. Writes go over the existing `ephe.sdk`
  channel as `storage.set`; the shell already routes that message to
  `/api/plugins/{id}/client/storage`, which writes this bundle's state root and nothing
  else's. The host side needed no new method: `attachPluginClient` is bound to the frame's
  plugin id, so the page cannot name another bundle.
- A read straight after a write returns the written value (the view is updated before the
  bridge round-trip). A refused or unanswered write reverts the key, dispatches
  `ephestorageerror`, and the next call that touches the key throws a named
  `EpheStorageError`. Nothing is silently wrong.
- `sessionStorage` is a per-document memory area: a sandboxed document's opaque origin is
  fresh per document, so a session area would not have survived a reload anyway.

Stated limits (also in `docs/PLUGIN_SDK.md` §3c): the store is string-only and shares its
keys with `ephe.storage`; named-property access, `for...in` and the `storage` event are not
emulated; the snapshot is taken at load, so a sibling document's later write is not pushed
into this one; `clear()` removes the keys this document knows; and the shell's 8 KiB/64 KiB
ceilings arrive as refused writes. New bundles still use `ephe.storage` — the shim is the
bridge that keeps a bundle written against the Storage API from losing the user's work.

## Problem, with the engine's proof

Three bundles of the paid run wrote `localStorage` from their surface document. The mount
refuses the write. The document is served with `sandbox allow-scripts allow-popups`
(`server/plugin_surface_policy.py:58`), and the embedder's frame carries the same two tokens
(`app/src/components/shell/OverlayHost.tsx:39`, set on the frame at line 311). The pin mounts
a frame with that attribute against that header; with `allow-same-origin` absent from both
lists, the document's origin is opaque. An opaque origin has no storage area, and the engine
says so:

```
origin:null
write:SecurityError Failed to read the 'localStorage' property from 'Window': The document
is sandboxed and lacks the 'allow-same-origin' flag.
read:SecurityError Failed to read the 'localStorage' property from 'Window': The document
is sandboxed and lacks the 'allow-same-origin' flag.
content:12
uncaught:Script error.
```

That output is the state `tests/test_plugin_surface_storage_refusal.py` asserts: the exact
`content:12` and `uncaught:Script error.` rows, and a `SecurityError` naming the sandbox and
the missing `allow-same-origin` on both the write and the read. The pin also asserts the
mounted frame carries the embedder's sandbox attribute and that the response header names
the same directive. Its control is the parent document, unsandboxed and on the app origin,
which writes a key and reads it back, so the storage API is alive in that engine and the
refusal is the sandbox. The probe's document also still renders, which is what splits the
eval's verdicts: the `mounts` row stays green, while `no_console_errors` and
`survives_reload` go red for those three bundles.

This is a decision and not a bug fix because the sandbox is the isolation mechanism the
surface was designed around: `app/src/components/shell/OverlayHost.contract.test.tsx:36-48`
lists storage access among what a surface must be refused, and
`tests/test_plugin_surface_isolation_browser.py` measures per engine that a null-origin mount
reads none of the user's authority.

## What the product already offers a bundle that needs state

- `ephe.storage.get` and `ephe.storage.set` (`sdk/ephe.js:63`), documented in
  `docs/PLUGIN_SDK.md:175-176`.
- The call is performed by the host shell, never by the sandboxed page:
  `app/src/lib/pluginClientHost.ts:38-46` routes it to
  `/api/plugins/{id}/client/storage`, key-scoped to the bundle and capped at 8 KiB per value
  and 64 KiB per store (`core/plugin_state.py:255-258`).
- The surface restore path already treats that route as the page's state path
  (`core/plugin_surface_host.py:1-8`).
- The creation eval already grades a bundle on it: `state_bridge_used`
  (`evals/creation_checks.py:206`) passes only for a bundle that calls the bridge, and names
  page storage as the failing path.

So the sanctioned API shipped and the three bundles used one the boundary was built to
refuse. What is missing is a rule the creator reads before it writes the bundle, and a gate
that states the rule where the bundle is graded.

## Option A — grant `allow-same-origin` to the bundle origin

**Change.** Add the token to `_ISOLATION_DIRECTIVE` and to `SURFACE_SANDBOX`. The embedder
mounts a frame with its own sandbox list, and the pin mounts that attribute, so the change
has to cover both lists.

**Security effect.**

- The document holds the app origin, so its storage API is the shell's own store. It can read
  and overwrite the language, the panel geometry, the open tabs, the last model, and every
  other bundle's page keys.
- Same-origin reads of `/api/*` return the user's bytes. The isolation suite measures today
  that `settings`, `plugins` and `file` come back BLOCKED; under A they LEAK.
- The embedding document is same-origin, which is the condition under which the frame may
  reach it through `window.parent`.
- The other refusals (top navigation, forms, modals, downloads) still hold, so A is short of
  full shell equality; the authority the isolation suite measures is gone.

**Effort.** Two product files, then every claim that leans on the opaque origin: the three
isolation-suite cases, the two embedder contract files, the "The page is sandboxed" sentence
in `docs/PLUGIN_SDK.md`, the docstring of `evals/creation_checks_browser.py`, and this pin.
`state_bridge_used` also loses its premise ("what a bundle can persist through that dies with
its mount") while still failing those bundles, so its wording needs a second decision. Half a
day of mechanism work, plus a security review that has to accept the regression.

**Tests after A.**

- green: the three bundles' writes, and their `no_console_errors` and `survives_reload` rows.
- red: `test_the_sandboxed_surface_holds_no_user_authority[chromium]`,
  `[webkit]`, `test_the_mount_response_header_carries_the_isolation_itself`, this pin,
  `OverlayHost.test.tsx` and `OverlayHost.contract.test.tsx`.

## Option B — forbid page storage in the definition of done

**Change.** Three parts:

- The DoD surface scan (`scripts/plugin_dod_surface.py`) refuses a bundle whose own runnable
  sources name `localStorage`, `sessionStorage`, `indexedDB` or `caches.open`. The vocabulary
  already exists as `PAGE_STORAGE_CALLS` (`evals/creation_checks.py:73`) and moves to the
  layer both readers can import, with `vendor/` excluded as the eval already excludes it. The
  scan grows from the entry document to the bundle's own sources.
- The creator guidance names the rule and points at `ephe.storage.*`.
- The three bundles are regenerated against the bridge.

**Security effect.** None on the mount. The boundary stays as the isolation suite measures it,
and a bundle's state reaches disk only through the host shell, inside the bundle's own key
space and byte ceilings.

**Effort.** A text scan, a DoD test, one guidance paragraph, and one creator run for the three
bundles. The bridge's ceilings are the real cost: 8 KiB per value and 64 KiB per store, so a
bundle that wants a large client-side dataset cannot be served this way. A surface in the
`native` slot has no embedding frame for the bridge to post to either (stated in
`docs/PLUGIN_SDK.md`), and its page storage is refused today for the same reason, so B leaves
that case exactly where it stands. That gap — a larger host-mediated store, and a bridge for a
native window — belongs in its own package.

**Tests after B.**

- green: this pin, the isolation suite, the embedder contracts.
- red: the DoD gate for a bundle that still ships a page-storage call; `state_bridge_used`,
  `no_console_errors` and `survives_reload` for the three until they are regenerated. After
  regeneration all of them are green.
- unchanged: the browser suite keeps reporting the refusal, so a bundle that regresses is
  caught after install as well as before.

| | A: `allow-same-origin` | B: DoD ban | C: shim (chosen) |
|---|---|---|---|
| Mount origin | the app origin | opaque | opaque |
| Bundle state | the shell's storage | host bridge, 64 KiB | host bridge, 64 KiB, via the shim |
| Product change | two files | one scan plus guidance | route, shim, docs |
| Isolation suite | red | green | green |

## Recommendation at the time (superseded by the decision above): B

The null origin is the mechanism the surface design, the embedder contract and the per-engine
isolation measurements all rest on; it is what makes a mount a document with no authority
rather than a second copy of the app. The three bundles needed an API that already ships, and
B states that rule where a bundle is graded: one text scan, one guidance line, one
regeneration. Option A spends the whole boundary on one storage call and then requires every
test and document that describes the boundary to be rewritten around a claim that no longer
holds.

Left for the owner: which wave regenerates the three bundles, whether the DoD rule is a hard
gate or a warning, and whether a larger host-mediated store gets its own package. The
2026-11-09 ruling answered the first by not requiring a regeneration: the shim serves
existing bundles, and `state_bridge_used` still asks a new bundle to use `ephe.storage`.

## Case disposition, 2026-11-10 (the eval's class 2)

The ruling and the creation eval are one direction now.

- `creation-05`'s product failure is closed. A page written against the Storage API —
  the shape the paid run left — mounts with `no_console_errors` and `survives_reload`
  green on Chromium and WebKit
  (`tests/test_creation_checks_browser.py::test_a_bundle_that_writes_local_storage_mounts_clean`),
  and in the embedded frame its write survives a read and a reload while the origin stays
  `null` (`tests/test_plugin_surface_storage_shim_browser.py`, 2 passed).
- `creation-01`, `-05` and `-08` keep the `state_bridge_used` row, and the paid run's
  three bundles still fail it. The definition of done is unchanged and still grades
  `ephe.storage`, so a bundle that keeps its entries only through the shim chose the
  compatibility path. The check now says that — page storage works and the graded path is
  the SDK — instead of implying the state is lost. No case was rewritten and no
  expectation moved: the browser rows that failed went green, the source row that failed
  was already correct.
- Accepting both paths (Option B after the fact) was rejected. The limits in
  `docs/PLUGIN_SDK.md` §3c are why the shim is a bridge: reads are a load-time snapshot,
  the store is string-only, a sibling document's write is not pushed, `clear()` knows
  only this document's keys, and a `native` slot has no host. A green row would bless a
  path whose gaps the row cannot see, and the eval grades new bundles.
- A hard DoD ban on page storage was rejected the way this record already rejected it:
  the three existing bundles have to keep working without a regeneration.
- The authoring path states the rule. `CREATOR_MODE_GUARD` names
  `<script src="ephe.js">` and `ephe.storage.get`/`set`, and says that `localStorage`
  works through the shim while the definition of done grades the SDK path
  (`tests/test_creator_guard.py::test_the_guard_names_the_state_path_the_eval_grades`).
- The surface scan knows the mount's two served names. `scripts/plugin_dod_surface.py`
  used to refuse `<script src="ephe.js">` as a file that does not ship, so the graded
  path failed `surface_files` on the one bundle that used it; the scan now resolves
  `ephe.js` at the mount root and `ephe-storage.js` at any depth, and still refuses a
  nested `sub/ephe.js` (`tests/test_plugin_dod.py`).
