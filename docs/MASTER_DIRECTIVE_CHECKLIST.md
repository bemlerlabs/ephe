# Master directive checklist (2026-10-29)

One page that holds every directive the owner has given, with what the tree
shows today. An entry is `[x]` only with evidence in this repository; everything
else is `[ ]`, including the entries whose state nobody has re-measured.

Sources: the two master-directive documents of 2026-10-29 (areas A–V, directives
1–22) and the chat run-surface order (`docs/CHAT_RUN_SURFACE_SPEC.md`).

## Chat surface (this wave)

- [x] Finished step is one line (`Ran N tools`); proof/status/one measurement on open.
- [x] Running step opens itself with `Running · <elapsed>` and folds back when done.
- [x] `Step x / y` pill over the transcript while a plan runs.
- [x] No template placeholders or duplicate measurements in the run rows.
- [x] No silent turn: a `progress` beat every 3 s without other frames.
- [ ] Inline diff card inside an open group (the tool card stands in for it).
- [ ] Replay removed from the transcript and reachable in the sidebar. Still
      renders inside the assistant turn (`bubble/assistantExtras.tsx:45` mounts
      `ToolReplayKader` under every finished message).
- [ ] Expert view trimmed to the same anatomy (no replay bar, no token rows in the bubble).
- [x] Composer and transcript: no light border. Neither `ChatInput` nor
      `bubble/` carries a white or near-white border; the `bg-white` hits under
      `dashboard/` are document and QR previews (`artifacts/preview.tsx`,
      `agent/previewFrame.tsx`), which are white by nature.
- [ ] Long-run proof: hours-long run without a stall (needs a measured run).

## Engine, tools, plugins

- [x] Loopback listener allowed in the shell sandbox (bind/inbound on
      `localhost:*`; outbound still denied), proven by a real `sandbox-exec` run.
- [ ] "Look at my project and start it" end to end: the workspace's own start
      command is chosen (SOL's map already names `dev: …`), started in the
      background instead of blocking a tool round, and the URL is reported.
- [ ] One editable capability surface: built-in tools, plugin tools, skills and
      MCP entries with an editable allow-list (read-only whitelist included).
      No route or surface carries it today.
- [x] Multiplexed SSE endpoint `/api/events/multiplex` exists; the 5 s polling
      loops in `CellLifeLine`/`useFleet` are gone.
- [ ] Warm CPython worker with a production caller (engine has no cancellation;
      see the L2 entry in the QD-014 review).
- [ ] Windows DPAPI / Job Objects; macOS signing + notarisation.

## Brand and repository assets

- [ ] Paper-moth mark replaces the bee on every surface (app icon, tray, PWA
      manifest, empty state, setup, custody seal, README). Landed so far: the
      TUI header and boot card (`ui/terminal_mark.py`), the intro still, the
      first-run tour guide and its engine core, and the chat companion. Icons,
      tray and README are the open rows.
- [ ] Bee survives only as the swarm sub-agent badge. No source file under
      `app/src` names a `bee-3d*` asset any more; the files still sit in
      `app/public/onboarding/` unreferenced.
- [ ] Master asset adopted from the owner's `paper-moth.webp` (paper, crimson
      thread) and rendered at 16–24 px from a vector cut.
- [ ] Repo screenshots and GIFs recaptured from the built app after the wave.

## Prompt and persona

- [ ] The system prompt is audited and extended for the current model class
      (not re-measured in this wave). It is built in `core/persona.py` and
      `core/chat_prompt.py`; there is no `persona.md` or `soul.md` in this tree.

## Updates (verified 2026-10-29)

- [x] A merge between two tags reaches the user: the check compares the build's
      commit against the default branch (ancestry, `core/update_check.py`) and
      reports `channel: "main"` with the commit range. Ahead and diverged
      checkouts are left alone.
- [x] Four surfaces carry it: the PWA and desktop dialog (`UpdateDialog.tsx`,
      compare link instead of an install the updater cannot perform), the TUI's
      boot line (`ui/app.py`), and the `ephe doctor` Update row, which never
      decides the exit code.
- [x] The pet is the user's: a drag on the moth moves it anywhere in the chat
      pane, the offset is remembered as a fraction of the viewport and clamped
      to the clipping ancestor, and a double click brings it home
      (`shell/useCompanionDrag.ts`).

## Packages A–V (master directive)

| Package | State |
|---|---|
| A tokens/typography | done in v0.4.0 (10 ink tokens, 12 px gate); re-verified by `globals.tokens.test.ts` |
| B chat layout / 40 px bar | done in v0.4.0 |
| C swarm deck | done in v0.4.0 |
| D mid-flight steering | done in v0.4.0 |
| E proof dual-reader + approval | done in v0.4.0 |
| F composer ergonomics | done in v0.4.0 |
| G settings areas | done in v0.4.0; SOL adds its own section (2026-10-29) |
| H icon constitution | done; cross-map audit green (`auditSettingsIconCollisions === 0`) |
| I macOS/Windows shell | macOS safe area done; Windows DPAPI open |
| J custody/fleet | done in v0.4.0 |
| K sidebar/TUI parity | done in v0.4.0 |
| L backend turbo | multiplex + SQLite done; warm cell open |
| M Hermes/AGENT.md bridge | done in v0.4.0 |
| N competitive synthesis | design benchmark only |
| O 10-year moat | Merkle proof tree done; shadow cells open |
| P progressive disclosure | done in v0.4.0 |
| Q plugin SVGs | 15 distinct SVGs, Warm-Ink palette (`sha256sum` all unique) |
| R cross-map icons + 16 px nav | `registerNav` 16 px / 1.5 px; audit zero collisions |
| S marketplace 2.0 | `MarketCard` uses `PluginIcon`; one-click try lives |
| T skills studio 2.0 | expandable packs, 18 px icons, run chip, provenance, builder |
| U working backwards | spec + gates in place (this page is its checklist) |
| V paper moth branding | assets and surfaces open (see Brand above) |

## Directives 1–22 (master directive)

1. Top chrome consolidation — done in v0.4.0.
2. Inline proof ledger — `ProofLedger.tsx` exists; still not part of the bubble in this wave.
3. Composer slimming — done in v0.4.0.
4. Sandbox approval card — three-way approval done; scope binding unverified here.
5. Custody/fleet visuals — done in v0.4.0.
6. Sidebar slimming + TUI tokens — done in v0.4.0.
7. Settings dedupe + VRAM matrix — done in v0.4.0.
8. Icon harmonisation — done (package R).
9. macOS/Windows native shell — macOS done, Windows open.
10. Backend turbo (SSE, WAL, warm pool) — SSE + WAL done, warm pool open.
11. Competitive edge synthesis — design only.
12. Live sub-agent/swarm deck — done in v0.4.0.
13. Mid-flight steering — done in v0.4.0.
14. Heterogeneous multi-model teams — per-member policy exists; templates unverified here.
15. Speculative shadow cells + Merkle chain — Merkle done, shadow cells open.
16. Everyone-mode progressive disclosure — done in v0.4.0.
17. package Q — done (above).
18. package R — done (above).
19. package S — done (above).
20. package T — done (above).
21. package U — in place.
22. package V — open (brand).
