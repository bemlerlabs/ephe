# Decision: page storage inside a plugin surface

- Status: open, owner decision
- Raised by: the paid creation run, whose three bundles wrote `localStorage` from a mounted surface
- Touches, under Option A: `server/plugin_surface_policy.py` and
  `app/src/components/shell/OverlayHost.tsx`; under Option B:
  `scripts/plugin_dod_surface.py` and the creator guidance

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

| | A: `allow-same-origin` | B: DoD ban |
|---|---|---|
| Mount origin | the app origin | opaque |
| Bundle state | the shell's storage | host bridge, 64 KiB |
| Product change | two files | one scan plus guidance |
| Isolation suite | red | green |

## Recommendation: B

The null origin is the mechanism the surface design, the embedder contract and the per-engine
isolation measurements all rest on; it is what makes a mount a document with no authority
rather than a second copy of the app. The three bundles needed an API that already ships, and
B states that rule where a bundle is graded: one text scan, one guidance line, one
regeneration. Option A spends the whole boundary on one storage call and then requires every
test and document that describes the boundary to be rewritten around a claim that no longer
holds.

Left for the owner: which wave regenerates the three bundles, whether the DoD rule is a hard
gate or a warning, and whether a larger host-mediated store gets its own package.
