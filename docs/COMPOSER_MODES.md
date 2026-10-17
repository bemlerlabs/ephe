# Composer modes — SSoT matrix

Four first-class modes in the composer (`ChatInput`). The selected mode is a
**session attribute** (IndexedDB + server mirror) and is passed to the engine per request as
`mode`/`autonomous`. Both routes — `/api/chat` and `/api/chat/stream` — share the same
semantics via `_mode_context`.

| Mode (UI) | key | Tools | System guard | Approval |
|---|---|---|---|---|
| Ask | `ask` | none (`[]`) | `ASK_MODE_GUARD` (anti-hallucination) | n/a |
| Plan | `plan` | the read-only family only | `PLAN_MODE_GUARD` (numbered plan) | profile |
| Edit auto | `edit-auto` | skill/profile list | compute guard (if arithmetic) | edit family auto, rest profile |
| Full access | `full-access` | skill/profile list | compute guard (if arithmetic) | everything automatically (`autonomous`) |

## Invariant sets
- Read-only family (`_READ_ONLY_TOOL_NAMES`): `read_file`, `file_search`, `list_directory`, `web_search`.
- Edit family (`_EDIT_TOOL_NAMES`): `edit_file`, `write_file`.

## Persistence round-trip (the contract)
1. The click sets `session.mode` + `debouncedSaveSession` (IndexedDB, incl. `mode`).
2. The sync payload `SyncSession` carries `mode`; the server writes it into `registry.json`.
3. `/api/sessions/restore` returns `mode`; `restoreFromServer` maps it back.
That is what makes a fresh browser (empty IndexedDB) keep the mode after a reload.

## Disentangling the indicators
- `composer-mode-selector` (grey): the **composer mode** (table above).
- `composer-permission-badge` (amber): the **approval profile** value
  (`approval_profile`): `Manual`/`Manuell`, `Session`/`Sitzung`, `Plan`/`Planen`, <!-- language-gate: ignore (the English/German label pairs the badge renders, app/src/locales/de.json:80-85 perm) -->
  `Full access`/`Voller Zugriff`. The four values mirror the four modes
  (`core/security_config.py::VALID_APPROVAL_PROFILES`), and the badge is the
  profile's own label: with both controls in the same state the chip and the badge
  read the same word, because they name one state on two axes. The two surfaces and
  the ceiling between them are stated in the UI itself (`chat.modeMenuNote`,
  `settings.profileModeNote`).

## Backwards compatibility
The old client value `agent` and an empty value => all mode factors `false`
(not-ask, manual approval) — identical behavior to before P4.

## Default rule (W34)
- `DEFAULT_COMPOSER_MODE = 'full-access'` (SSoT in `app/src/store/chat/helpers.ts::DEFAULT_COMPOSER_MODE`).
- Fresh sessions start with tools available: `ChatInput` falls back to this value
  when no `session.mode` is set; `ChatLayout` passes it through per turn as
  `mode`/`autonomous` (`app/src/components/dashboard/chat/model.ts::useChatLayoutModel`).
- There is **no** hidden fallback: the mode fallback is exactly this one shared
  constant; the engine itself fails closed without a persisted config.

## Virtualizer invariant (W33/W34)
- The spacing of the message rows lives **in the measured node** (not as an extra
  offset outside it), otherwise `top` drifts cumulatively and the rows overlap.
- `estimateSize` = 120 is only the initial estimate; per node the
  `ResizeObserver` (`observeElementRect`/`observeElementOffset`) re-measures after
  the first measurement → no cumulative top-drift.
- `getItemKey` is bound to `msg.id` (a stable node→index mapping when
  appending/revising), not to the array index.
- After a turn ends (streaming → done) the layout effect calls `measure()` and,
  when pinned, re-pins to the end.

## Tool-count difference (W34)
- `TOOL_MAP` = **64** entries (canonical edit family: `edit_file`,
  `write_file`; `apply_patch` was removed with R35).
- The filtered schemas (`get_tool_schemas()`) return **63**, because
  `run_sandboxed_code` sits behind `sandbox_is_available()` (only injected when
  `ephemera_cell` is installed / the sandbox mode is active) — the
  64↔63 difference is intended, not a bug.
