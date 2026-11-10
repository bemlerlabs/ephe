# Composer modes — SSoT matrix

Four modes are selectable in the header (`HeaderModeControl`, over the `SESSION_MODES` table in
`modeCatalog.ts`), and a stored session can still carry spellings no click can produce. The mode
is a **session attribute** (IndexedDB + server mirror) and is passed to the engine per request as
`mode`/`autonomous`. The composer keeps the access side: its approval profile is the ceiling
above the mode. Both routes — `/api/chat` and `/api/chat/stream` — share the same semantics via
`_mode_context` (`server/routes/chat.py`).

## The matrix

| Mode (UI) | key | Tools offered | System guard | Approval once the gate runs |
|---|---|---|---|---|
| Analyst | `analyst` | none (`[]`) | `ANALYST_MODE_GUARD` (anti-hallucination) | nothing to approve |
| Architect | `architect` | the read-only family only | `ARCHITECT_MODE_GUARD` (numbered plan) | no auto branch; the profile alone |
| Operator | `operator` | the skill list, else the whole registry | compute/page guard when the message needs one | edit family, then every tool, once the profile allows it |
| Creator | `creator` | the skill list plus the Creator calls its grants cover, else the whole registry less the calls its grants do not cover | `CREATOR_MODE_GUARD` (plugin writing) | no auto branch; the profile alone, plus the consent gate |

The menu carries four tiles (`app/src/components/dashboard/chat/ModeMenu.tsx`, reading
`app/src/components/dashboard/chat/modeCatalog.ts::SESSION_MODES`).
`creator` is the fourth: the tile asks for the session's consent before the session takes the
mode, and every mutation then lands on the profile's dialog. The consent gate
(`core/tools/creator_guard.py`, task #26) is what makes the key mean something at the call: the
session holds any of `code`/`files`/`network` through `GET|PUT /api/creator/consent`, a call
whose permission it does not hold is refused before the handler runs, and those names leave the
offer list, so the model is not invited to plan around a refusal. The three mode
guards are constants in `core/persona.py`; the compute and page guards (`COMPUTE_GUARD`,
`PAGE_OUTPUT_GUARD`) are triggered by the message and read no mode.

## What a stored value resolves to

Two migration points, one per side. On load the store rewrites a stored value once and
persists the result (`app/src/store/chat/session.ts`, `MIGRATABLE_LEGACY_MODES` in
`app/src/store/chat/helpers.ts`): exactly the three values the retired menu could write. Per
request, `_MODE_ALIASES` and `_resolve_mode` (`server/routes/chat.py`) turn whatever spelling
arrives into the boolean factors, and that half edits no stored data. The lookup lowercases and
turns `-` into `_`, so the hyphen wire value and the underscore spelling the alias table was
written for are one value.

| Old UI name | Stored value | Rewritten on load | Resolves to | Selectable today | What it may run |
|---|---|---|---|---|---|
| Ask | `ask` | yes, to `analyst` | the Analyst tile | no | no tools |
| Plan | `plan` | yes, to `architect` | the Architect tile | no | the read-only family |
| Full access | `full-access` | yes, to `operator` | the Operator tile | no | the operator auto branches |
| Full access | `full_access` (an underscore spelling no menu wrote) | no | the Operator tile | no | the operator auto branches |
| Edit auto | `edit-auto`, `edit_auto` | **never** | the edit-family compatibility factor | never | the edit family once the profile allows it; everything else still asks |
| — (pre-mode client) | `agent` | no | every factor false | no | whatever the approval profile allows |

`edit-auto` is **not selectable** and is **never rewritten**. It resolves to its own
compatibility factor (`edit_family_compat`) and never to `operator`; no migration on either
side edits the stored value. The reason is measurable in the gate: its auto branches are held
by `mode_auto = profile != "strict"` (`chat.py:1722`), and `strict` is the only profile that
shuts them, for every stored mode alike — so a clamp pointed at `edit-auto` alone does not
exist. Mapping the value onto the Operator tile would therefore have widened approvals under
`session`, `plan` and `full`, the three profiles that leave those branches open.
`tests/test_composer_mode_rename.py` runs the real gate over all four profiles for the kept
value, over the three open ones for that hypothetical rewrite, and pins the audit label each
stored mode emits while it is at it.

An unset `session.mode` is not one of these values: the client fills in the default (below)
before a request, so the all-false reading of an empty `mode` belongs to a caller at the API.

A stored value with no tile renders its section wording in the header control (the
`chat.modeSection.write` leaf), so the interface never shows a raw key.

## Invariant sets
- Read-only family (`_READ_ONLY_TOOL_NAMES`): `read_file`, `file_search`, `list_directory`,
  `web_search`, `ask_user`.
- Edit family (`_EDIT_TOOL_NAMES`): `edit_file`, `write_file`.

Both are set literals in `server/routes/chat.py`, and they guard different things. The approval
gate (`_sandbox_confirm`) has one family test, `name in _EDIT_TOOL_NAMES` (`chat.py:1732`), and
it carries no read-only branch anywhere. The read-only family is what an Architect turn is
**offered** (`_mode_context`, `chat.py:536`); what refuses a call in a read-only mode is the
wider `core.tools.chat_gate.READ_ONLY_MODE_TOOLS`, judged where the tool executes
(`chat_gate.py:95`, W10). `apply_patch` left the registry with R35, so the edit family is those
two names and nothing else.

## Persistence round-trip (the contract)
1. The click sets `session.mode` + `debouncedSaveSession` (IndexedDB, incl. `mode`).
2. The sync payload `SyncSession` carries `mode` (`server/routes/session_mirror.py`); the
   server writes it into `registry.json`.
3. `/api/sessions/restore` returns `mode`; `restoreFromServer` maps it back.
That is what makes a fresh browser (empty IndexedDB) keep the mode after a reload. A stored
legacy value travels this round trip verbatim unless the load-time rewrite above names it, and
the server resolves whatever arrives without editing it.

## Disentangling the indicators
- `header-mode-control` (grey): the **response mode** (the matrix above).
- `composer-permission-badge` (amber): the **approval profile** value (`approval_profile`),
  labelled `Manual`/`Manuell`, `Session`/`Sitzung`, `Plan`/`Planen`, `Full access`/`Voller Zugriff` <!-- language-gate: ignore (the English/German label pairs the badge renders, app/src/locales/de.json::chat.perm) -->
  (`ComposerAccessControl.tsx` reads `chat.perm.<profile>`).
- The two axes are now a **mapping**, and the rename is what made that visible. The profile
  enum kept its four spellings through it (`core/security_config.py::VALID_APPROVAL_PROFILES`
  = `strict`, `session`, `plan`, `full`) while three modes were renamed and one retired, so
  the mode vocabulary and the profile vocabulary share no word: the chip says
  Analyst/Architect/Operator, the badge says Manual/Session/Plan/Full access. What this
  document claimed before — that the four profile values mirror the four modes, and that both
  controls in the same state read the same word — described an identity that no longer holds.
  `plan` is the proof of the split: it is a live profile value and a stored legacy mode value
  at the same time, naming two different things.
- What joins the two axes is one gate (`_sandbox_confirm`): the profile decides whether a
  mode's auto branch may fire at all (`mode_auto = profile != "strict"`), the mode factor
  decides which branch fires, and the ceiling between them is stated in the UI itself
  (`chat.modeMenuNote`, `settings.profileModeNote`).

## Backwards compatibility
An old client that sends `agent`, or an empty `mode`, gets every mode factor `False`: the tool
list comes from the skill, no mode guard is added, and approval sits with the profile alone —
the behavior that preceded P4. A renamed spelling (`ask`, `plan`, `full-access`) and the
retired spelling (`edit-auto`) each resolve to the factor that keeps the behavior the session
was created with, so the rename moved no privilege. The approval-profile vocabulary is
deliberately unchanged: `VALID_APPROVAL_PROFILES` still reads `strict`, `session`, `plan`,
`full`, which is why the two axes are a mapping now (above).
The audit `status=` vocabulary is a second frozen surface: `autonomous`, `edit_auto` and
`full_access` still reach the log after the rename, because log consumers read them, and
`tests/test_composer_mode_rename.py` reads each label off the stored line so the freeze has a
witness.

## Default rule (W34)
- `DEFAULT_COMPOSER_MODE = 'operator'` (SSoT in `app/src/store/chat/helpers.ts::DEFAULT_COMPOSER_MODE`).
- Fresh sessions start with tools available: the header control falls back to this value
  when no `session.mode` is set; `ChatLayout` passes it through per turn as
  `mode`/`autonomous` (`app/src/components/dashboard/chat/model.ts::useChatLayoutModel`).
- `autonomous` is derived from that mode on the same call site: it is set for `operator` and
  for nothing else. It is the first branch of the gate and outranks both mode branches, so a
  stored `edit-auto` never reaches it.
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
- This section holds no figure. The pair it used to hold had drifted from the registries they
  described while nobody measured them here, so the numbers moved back into the tests that read
  them and this page keeps only where they live and what they guard.
- `TOOL_MAP` (`core/tools/registry.py`) is the dispatch registry — the name→function map
  `execute_tool` reads, aliases included. Its key count belongs to two tests and nowhere else:
  `tests/test_r60_plugin_runtime.py:115`
  (`test_the_dispatch_map_stays_the_whole_map_while_a_plugin_is_off`) and
  `tests/test_w9_self_awareness.py:85`
  (`test_the_dispatch_map_ephe_reports_on_itself_is_the_whole_map`). Both hold the same literal,
  both refuse with the repair they want, and either one prints the current figure.
- What that number guards is the completeness of the map: every name userspace can address is a
  key, and switching a plugin off must not thin it — the r60 anchor guards that half. The other
  half is Ephe talking about itself: the capability answer counts the same map, so the system
  cannot describe a thinner toolset than it dispatches.
- `get_tool_schemas()` is that tool surface after the gate: schema blocks assembled by
  `_all_tool_schemas()`, then thinned by the installed plugins and the user's own capability
  switches in `_apply_plugin_filter`. It is deliberately not the map — the dispatch aliases
  (`bash`, `read`, `edit`) carry no schema, the sandbox cell's tool is added only when
  `sandbox_is_available()` answers yes, and an attached remote tool server and a registered
  plugin descriptor contribute schemas the dispatch map does not own. The distance between the
  two is intended and depends on the machine, which is why no test pins the offer-list figure —
  `tests/test_tool_schema_pokayoke.py` states the rule that the registry owns those numbers.
