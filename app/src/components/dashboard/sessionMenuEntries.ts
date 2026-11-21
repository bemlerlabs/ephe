/**
 * The session context menu's entry ids in display order, in groups that a rule
 * divides — the ONE list, the pattern of NAV_KEYS in settings/types.ts. Sidebar.tsx
 * renders the rows from it and Sidebar.menu.test.tsx reads its expectation from it,
 * so the menu and its test cannot drift apart in either direction.
 *
 * The reference cut carries the two management rows, the path and navigation rows,
 * the trajectory and the issue report. Ephe adds three of its own beyond that cut:
 * the branch fork (Z37, two rows above the export), the markdown export (Z38) and
 * the delete with the inline confirm, which stands alone behind the last rule.
 *
 * Import-free on purpose: a hook importing it must not close an import cycle.
 */

export const SESSION_MENU_GROUPS = [
  ['pin', 'rename', 'archive', 'unread'],
  ['show-path', 'copy-path', 'copy-task-path', 'copy-log-path', 'copy-id', 'goto-config'],
  ['trajectory', 'branch'],
  ['report-issue', 'export'],
  ['delete'],
] as const

export type SessionMenuEntryId = (typeof SESSION_MENU_GROUPS)[number][number]

/** The flat ids in display order — the same rows the rule is drawn between. */
export const SESSION_MENU_ENTRY_IDS: readonly SessionMenuEntryId[] = SESSION_MENU_GROUPS.flat()
