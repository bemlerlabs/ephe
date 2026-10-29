# Chat run surface — specification (owner order, 2026-10-29)

The chat is the product. One turn must read as a calm log of what Ephe did, in
the order it happened, with the working visible on request and nothing else.

## 1. The turn, top to bottom

1. A short line of prose before each step ("Now the reflector and the
   consolidator"), written by the model in the user's language.
2. The step's tool work as ONE collapsed row: `Ran 16 tools`, chevron on the
   left. Collapsed is the default; the count is the only number on the row.
3. The running step expands on its own into a live block: a heading with the
   elapsed time (`Running · 245s`), one row per call (icon, verb, target,
   duration, status), and — when a file changed — an inline diff card with
   `+n −m`. The user may collapse it at any time; a manual collapse is never
   reopened by the surface.
4. A step pill at the bottom of the transcript (`Step 13 / 21`) with a jump
   button, while a plan is running.
5. The final answer in normal prose. No status rows, no counters, no replay bar
   inside the transcript.

## 2. What must never appear in the transcript

- Template placeholders (`{{tool}}`, `{{ms}}`, `{{args}}`) in any language.
- The same measurement twice (a duration in the proof text and again as a chip).
- Raw phase strings as user-visible rows ("Tool round 2…", "Processing
  results…", "Executing 2 read-only tool(s) in parallel…"). They may drive the
  live heading; they are never a transcript line.
- Replay, token accounting, per-run metadata and the proof ledger: those live in
  the sidebar and the artifact rail. The transcript keeps prose, tool rows,
  diff cards and the answer.
- White or light borders, light gaps or a second ground anywhere in the composer
  or the live transcript. One ground (`--color-canvas`), hairlines
  (`--color-hairline`), no pane that glows lighter than the surface beneath it.

## 3. Readability for hours of work

- Body prose at the reading size already in the register (`text-ui-input` for
  drafts, `text-ui-sm` for answers), never below 12 px anywhere.
- Line length capped (`max-w-3xl` in the transcript column), line height 1.6+.
- Muted ink for anything that is not the answer; one accent colour for the
  thing the user must decide (approval, stop, continue).
- The transcript never reflows when a tool row expands: the row grows downward
  inside the column, the composer stays fixed.

## 4. Long runs must not stall

- A turn that runs for hours must keep producing stream frames: a heartbeat
  while the engine thinks, a row update while a tool runs, an elapsed counter on
  the running step.
- No gap longer than the engine's own silence threshold without a visible
  "still working" signal; a silent minute is a defect, a silent five minutes is
  a hang.
- A stall must be reported with what Ephe is waiting for (engine, tool, user),
  and the run must be resumable without losing the turn.

## 5. "Look at my project and start it"

A request in plain words ("look at the project and start it") must lead to
the project's own start command, found in the workspace (package scripts,
Makefile, docker compose), run on a free local port, with the URL reported. The
sandbox must allow a loopback listener for this case (it currently refuses
`bind`, which reads as a failure of the request rather than of the sandbox).

## 6. Tools, plugins, skills — one editable surface

- Every capability is an entry: built-in tools, plugin tools, skills, MCP
  servers.
- The user can enable, disable and edit the allow-list per entry, including the
  read-only whitelist used by sub-agents.
- A tool the model cannot call names the reason (not offered, refused by the
  array, unknown name) on the row, not only in the log.

## 7. Brand

- The mark is the paper moth: folded paper, warm ink, crimson thread. It replaces
  the bee as the product mark on every surface (app icon, tray, PWA manifest,
  empty state, setup, custody seal, repo README). The bee stays only as the
  sub-agent badge in the swarm deck.
- The moth is rendered from a vector source at 16–24 px and from the master
  asset above 32 px; no generated image may carry the layout, type or controls.

## 8. Repository assets

- `docs/screenshots/` and the README images are recaptured from the built app
  after each surface wave (chat at 1280 and 390, settings, custody), never from
  a mockup.

## Open checklist

- [ ] Run surface rebuilt to the anatomy in §1 (groups, live block, step pill).
- [ ] Placeholder and duplicate-measurement defects removed (§2).
- [ ] No light borders in composer/transcript; contrast measured (§2, §3).
- [ ] Heartbeat and stall reporting for long runs (§4).
- [ ] Project start request recognised and served on loopback (§5).
- [ ] One capability surface with an editable allow-list (§6).
- [ ] Paper moth mark on every surface, bee as swarm badge only (§7).
- [ ] Repo screenshots and GIFs recaptured (§8).
