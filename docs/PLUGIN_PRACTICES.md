# Ephe Plugin Practices

Eleven practices Ephe holds its plugin platform to. This file maps each practice to where Ephe implements it, with file paths and the reasoning behind the choice.

## 1. Session Log as Source of Truth

**Status**: Implemented

The audit log and run ledger are append-only JSONL files with SHA-256 hash chaining. Every state change is persisted before the SSE event is published, so the log is the canonical record — not the in-memory bus.

**Evidence**:
- `core/audit_log.py` — append-only JSONL, hash chain, fsync
- `core/run/ledger.py` — one JSONL file per run, five phase projections
- `server/routes/audit.py` — GET /api audit exposes the log

**Why this matters**: An in-memory event bus can lose events on crash; a persisted log cannot. The SSE stream is a view over the log, not the source.

## 2. Registrations as Effects

**Status**: Implemented (2026-11-08)

When a plugin mounts, each tool produces its own `plugin.tool_registered` event on the SSE bus. The batch `plugin.mount` event rides alongside for consumers that want the whole set in one frame, but the per-tool event is the registration effect — a subscriber can react to each tool individually.

**Evidence**:
- `core/plugin_lifecycle_mount.py:340` — `_mount_notify()` emits one event per tool
- `tests/test_plugin_registration_events.py` — pins the per-tool event count

**Why this matters**: A batch event forces every subscriber to decompose the tool list. Per-tool events let a subscriber filter by tool name and react to each registration independently — the waterfall pattern starts here.

## 3. Waterfall Listeners

**Status**: Implemented (2026-11-08)

The pub/sub bus supports filtered subscriptions: a caller can ask for events from one `plugin_id` or one `event_type`, and the bus delivers only those. Plugin A can subscribe to Plugin B's `tool_registered` events without receiving noise from Plugin C.

**Evidence**:
- `core/plugin_lifecycle_events.py:28-52` — `subscribe_filtered()` with plugin_id and event_type filters
- `core/plugin_lifecycle_events.py:77-88` — `_matches_filters()` checks the event against the filter criteria
- `tests/test_plugin_waterfall_listeners.py` — verifies filtering by plugin and event type

**Why this matters**: Unfiltered subscriptions force every subscriber to receive every event and filter client-side. Server-side filtering reduces noise and lets plugins compose: B's registration triggers A's reaction, which triggers C's reaction — the waterfall.

## 4. Guards vs Restrictions

**Status**: Implemented

**Guards** are runtime checks before execution:
- `core/tools/chat_gate.py` — mode denial at execution time
- `core/tools/ask_gate.py` — approval pause gate
- `core/plugin_activity.py` — `CallGuard` for in-flight cancellation

**Restrictions** are static declarations in the manifest:
- `core/plugin_manifest.py` — `KNOWN_TOOL_FAMILIES` validates permissions at load
- `core/plugin_tools_contract.py` — validates tool claims against manifest-declared families

**Why this matters**: A restriction says "this plugin is not allowed to do X" (static, declarative). A guard says "this plugin may do X, but only if Y holds right now" (dynamic, runtime). Separating them keeps the manifest readable and the runtime checkable.

## 5. Context Ownership

**Status**: Implemented

Each async task owns its context via Python `ContextVar`:
- `core/tools/session_ctx.py` — `_CURRENT_SESSION`, `_CURRENT_POLICY`, `_CURRENT_MODE`, `_FAILOVER_NOTE`, `_MEASURED_USAGE`
- `server/routes/chat.py:579` — `_publish_tool_mode()`, published per turn at `:1174` and reset in `finally` at `:1218`

**Why this matters**: Context leakage between concurrent tasks causes cross-session pollution. `ContextVar` ensures each task sees its own values, even when multiple sessions run in parallel.

## 6. Session Projections

**Status**: Implemented

Session state is projected into derived views:
- `core/ephe_plan.py` — `EphePlan.try_from_markdown()` and `from_ledger()` project session state into a plan view
- `core/run/ledger.py` — five phase projections: `now`, `waiting`, `changed`, `result`, `next`
- `core/fleet_rows.py:75` — `ledger_view()` for fleet-wide views
- `core/trajectory.py:239` — `_with_ledger()` combines turn + run ledger projection

**Why this matters**: Raw session state is a log of events; a projection is a query over that log. The plan card, the stats panel, and the outline are all projections — different views over the same source.

## 7. Plain JSON State

**Status**: Implemented

Plugin state is stored as JSON files with validation:
- `core/plugin_state.py:288` — `CLIENT_STORE_NAME = "client-store.json"`
- `core/plugin_state.py:299-316` — `_read_client_store()` parses JSON
- `core/plugin_state.py:345-381` — `client_set()` writes JSON with validation
- Byte caps: `CLIENT_VALUE_MAX = 8192`, `CLIENT_STORE_MAX = 65536`

**Why this matters**: JSON is human-readable, diff-friendly, and validates against a schema. Binary formats (SQLite, protobuf) are faster but opaque — a plugin state file you can't read is a plugin state file you can't debug.

## 8. Durable Events

**Status**: Implemented

Events are persisted durably before they are published:
- Audit log: append-only JSONL on disk with `fsync` (`core/audit_log.py:143-154`)
- Run ledger: one JSONL file per run (`core/run/ledger.py:1-8`)
- Plugin lifecycle: temp-file + fsync + replace (`core/plugin_lifecycle_store.py:338-398`)
- SSE bus: in-memory only, but every state change is already persisted before the publish call

**Why this matters**: An in-memory event bus loses events on crash. A durable event log survives crashes and can be replayed. The SSE bus is a view over the durable log, not the source.

## 9. Surface Placement

**Status**: Implemented (2026-11-08; the placement cut 2026-11-12)

A plugin declares where it renders through `components.ui.type`, the one placement
declaration the manifest owns (`core/plugin_ui_capabilities.py` `UI_TYPES`):
- `app/src/lib/surfacePlacement.ts` — the pure resolver both product surfaces read
- `app/src/lib/pluginDisplay.ts` — asks it once, then opens the desktop window or paints the overlay stack
- `app/src/lib/surfaceHost.ts` — the `HostSlot` record of where the shell put the surface

A `floating-window` gets the desktop's own window and the browser's framed surface; a
`canvas-overlay` is the framed surface on both; a `dock-panel` is refused with the code
`surface_dock_panel_unavailable` until the shell owns a docked region. A bundle cannot name
a slot, a position or a DOM node, and a shell that cannot host the declared placement
refuses it instead of quietly choosing another.

**Why this matters**: A placement declaration lets a bundle pick among the surfaces the
shell already owns instead of the shell guessing. The list stays closed so a bundle cannot
invent a region, move its own box or reach into the product tree.

## 10. Theme Tokens

**Status**: Implemented

The frontend uses a comprehensive token system:
- `app/src/styles/globals.css` — `@theme` block with CSS custom properties:
  - Font scale: `--text-ui-*`, `--text-scale-*`
  - Elevation shadows: `--shadow-elevation-*`
  - Radius scale: `--radius-*`
  - Motion tokens: `--transition-duration-*`, `--ease-*`
  - Z-index scale: `--z-index-*`
  - Numeric column widths: `--num-col-*`
- Test files enforce token hygiene: `globals.tokens.test.ts`, `globals.deadTokens.test.ts`, etc.

**Why this matters**: Hard-coded colors, shadows, and spacing drift over time. Tokens enforce consistency and make theme changes one-line edits.

## 11. Conversation Events

**Status**: Implemented

Tool calls, refusals, and completions are emitted as typed SSE events:
- `server/routes/chat.py:1345` — `_make_stream_callbacks()` builds the per-turn frames;
  `core/goal_loop.py:112-129` emits the three goal frames the route relays:
  - `tool_start`, `tool_done`, `chunk`, `thinking`, `thinking_chunk`
  - `activity`, `plan`, `file_result`, `artifact_check`, `stdout`
  - `error`, `done`, `sandbox_confirm`, `ask_user`, `skill_created`
  - `run_snapshot`, `failover`, `project_progress`
  - `goal_start`, `goal_turn`, `goal_check`
- A turn frame carries `turn_id`, a tool frame adds `call_id`, and every payload is structured

**Why this matters**: Untyped events force the client to parse strings. Typed events with structured payloads let the client switch on `event.type` and render accordingly — the conversation is a state machine, not a text stream.

---

## Summary

| Practice | Status | Closed |
|----------|--------|--------|
| Session log as source of truth | Implemented | — |
| Registrations as effects | Implemented | 2026-11-08 |
| Waterfall listeners | Implemented | 2026-11-08 |
| Guards vs restrictions | Implemented | — |
| Context ownership | Implemented | — |
| Session projections | Implemented | — |
| Plain JSON state | Implemented | — |
| Durable events | Implemented | — |
| Surface placement | Implemented | 2026-11-08 |
| Theme tokens | Implemented | — |
| Conversation events | Implemented | — |

**11/11 implemented**. The three rows that were open on 2026-11-08 closed with `86279bb5`, `9a0e5e41` and `cb52a2d8`; every row above is a claim about Ephe's own code, and the section it belongs to names the file that proves it.
