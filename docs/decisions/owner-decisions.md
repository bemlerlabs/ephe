# Owner decisions, 2026-11-07

Status: decided by the owner. This record carries the decisions as they were taken; where the
tree has moved since, the move is named at the decision instead of being folded into its text.

| Field | Value |
|---|---|
| Date | 2026-11-07 |
| Scope | this record only; no product code |
| Decides | the plugin platform's feature flag, the red-team budget, the consent notice Creator Mode asks through |

## FLAG-01 — the plugin platform gets no feature flag

**Decision.** No feature flag for the plugin platform.

**Rationale.** The plugin system is core architecture ("everything is a plugin"), so a
global off-switch would break the product. The boundaries that matter are already held
elsewhere: the sandbox, the per-privilege gates, the CSP and the audit log. There is no
budget for an external red team until funding, so the first pass is internal (RT-01).

**Where it stands in the tree.** There is no platform flag to read: per-plugin enablement
is the authoritative switch (`PUT /api/plugins/{id}/enabled`, `server/routes/plugins.py:10`).
`POST /api/plugins/master` (`server/routes/plugins.py:407`) is the legacy pause control —
off pauses every plugin, on restores the per-plugin states — and it is not the platform
gate this decision refuses. The operator's brake on the switch surface is the read-only
setting `plugins.plugin_lifecycle_read_only` (`core/plugin_switch_policy.py:10`,
`core/settings_schema.py:216`); it blocks switch mutations, it disables no plugin, and it
never restores the retired `master_enabled` bypass.

## RT-01 — internal red team only

**Decision.** An internal red-team pass first. No external audit budget until funding; an
external audit only after funding or if the internal pass finds a critical issue.

**Scope of the pass.** Plugin sandbox escapes, permission bypass, CSP violations — one
week of internal work.

**Rationale.** Zero external budget for security review. The internal pass carries the
first round; the question is revisited when funding arrives.

## Creator Mode's consent notice

**Decision (2026-11-07).** The notice speaks in the product's friendly voice, not a legal
one, and asks for three granular privileges — code execution, file access, network access —
one row each, with a risk level beside it. The dialog carries no liability waiver; that
belongs in the terms, not in the sheet.

**Moved since (2026-11-08).** The A2 owner ruling replaced two parts of that sketch, and the
shipped sheet is the ruling's: one granted privilege is enough to enter Creator Mode, and a
grant is keyed to one session, never to the device. The sheet is
`app/src/components/dashboard/chat/CreatorConsentDialog.tsx`; the privileges are the guard's
closed set (`core/tools/creator_guard.py:39`) and the words are `chat.creatorConsent.*` in
the locale bundles. The risk badge gave way to a sentence stating the reach the privilege
grants. What survives from 2026-11-07 is the shape: three named privileges, asked one by
one, in the product's own voice, with no waiver inside the dialog.
