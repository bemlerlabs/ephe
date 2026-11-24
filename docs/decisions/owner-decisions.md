# Owner decisions, 2026-11-07

Status: decided by the owner. This record carries the decisions as they were taken; where the
tree has moved since, the move is named at the decision instead of being folded into its text.

| Field | Value |
|---|---|
| Date | 2026-11-07 |
| Scope | this record only; no product code |
| Decides | the plugin platform's feature flag, the red-team pass, the consent notice Creator Mode asks through |

## FLAG-01 — the plugin platform gets no feature flag

**Decision.** No feature flag for the plugin platform.

**Rationale.** The plugin system is core architecture ("everything is a plugin"), so a
global off-switch would break the product. The boundaries that matter are already held
elsewhere: the sandbox, the per-privilege gates, the CSP and the audit log. The first pass over
these is internal (RT-01).

**Where it stands in the tree.** There is no platform flag to read: per-plugin enablement
is the authoritative switch (`PUT /api/plugins/{id}/enabled`, `server/routes/plugins.py:10`).
`POST /api/plugins/master` (`server/routes/plugins.py:407`) is the legacy pause control —
off pauses every plugin, on restores the per-plugin states — and it is not the platform
gate this decision refuses. The operator's brake on the switch surface is the read-only
setting `plugins.plugin_lifecycle_read_only` (`core/plugin_switch_policy.py:10`,
`core/settings_schema.py:216`); it blocks switch mutations, it disables no plugin, and it
never restores the retired `master_enabled` bypass.

## RT-01 — internal red team only

**Decision.** An internal red-team pass first. An external audit is commissioned later, or at once
if the internal pass finds a critical issue; the first round has no external audit behind it.

**Scope of the pass.** Plugin sandbox escapes, permission bypass, CSP violations — one
week of internal work.

**Rationale.** The internal pass carries the first round. Whether an external audit is
commissioned is a later decision, and a critical finding in the internal pass makes it immediate.

## Creator Mode's consent notice

**Decision (2026-11-07).** The notice speaks in the product's friendly voice, not a legal
one, and asks for three granular privileges — code execution, file access, network access —
one row each, with a risk level beside it. The dialog carries no liability waiver; that
belongs in the terms, not in the sheet.

**Moved since (2026-11-08).** The owner ruling of that date replaced two parts of that sketch, and the
shipped sheet is the ruling's: one granted privilege is enough to enter Creator Mode, and a
grant is keyed to one session, never to the device. The sheet is
`app/src/components/dashboard/chat/CreatorConsentDialog.tsx`; the privileges are the guard's
closed set (`core/tools/creator_guard.py:39`) and the words are `chat.creatorConsent.*` in
the locale bundles. The risk badge gave way to a sentence stating the reach the privilege
grants. What survives from 2026-11-07 is the shape: three named privileges, asked one by
one, in the product's own voice, with no waiver inside the dialog.

## The forest is the only ground

**Decision (2026-10-19), recorded here 2026-11-24.** The product ships one visual language and one
ground: the forest. No light theme, no system follow, no theme toggle. Paper had been tried as the
default and rejected on 2026-10-16, then kept as a user choice until this decision removed it from the
product (`tests/test_forest_only.py:3-5`).

**Why the entry is late.** The ledger carried no line for this date: `rg -n '2026-10-19'
docs/decisions/owner-decisions.md` answered with nothing while five comments in the app cited
`docs/DESIGN.md` §3 for exactly this rule. `docs/DESIGN.md` now holds the rule and this entry is the
ledger's copy of the date. No rationale is stated here, because no file in this checkout records one; a
reason invented to fill a table is the claim this ledger exists to keep out.

**Where it stands in the tree.**

| What carries the decision | Where |
|---|---|
| The sweep's set of grounds, one entry | `app/tests/playwright/theme-parity.spec.ts:724` |
| The token audit's set of grounds, one entry | `app/src/styles/globals.boundaryContrast.test.ts:51` |
| Eight refusals at the source, each proved against its own example | `tests/test_forest_only.py:40-60`, probes at `:76`, scan coverage at `:96` |
| The committed counts: 163 rows, every one forest | `app/tests/playwright/theme-parity.baseline.json` |
| The settings section that says the forest is the only theme | `app/src/components/dashboard/settings/model/sections-appearance.tsx:10` |
| The stylesheet's token guardian, which refuses a second block | `app/src/styles/globals.tokens.test.ts:4-6` |
| The contrast floors, now taken on one ground | `docs/ACCESSIBILITY.md:45-49` |
| Palette, mark and share-card recomputations on that ground | `scripts/theme_contrast.py:4`, `scripts/brand_palette.py:16`, `scripts/mark_contract.py:52`, `scripts/generate_social_preview.py:12` |
