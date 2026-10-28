/**
 * The sidebar's destination rows in display order, in the three tiers the
 * owner asked for (register #71): "New Task + current tasks/steps" first,
 * "Tools & Capabilities" second, "Knowledge, Library, Automations, Connectors"
 * third. The two lower tiers are disclosures — closed on first run and
 * remembered per person (see OPEN_TIERS_KEY), so the top of the sidebar says
 * what is primary instead of listing thirteen equal-looking rows.
 *
 * The ONE list, the pattern of SESSION_MENU_GROUPS: Sidebar.tsx renders the rows
 * from it and Sidebar.g3.test.tsx reads its expectation from it, so the tiers
 * and their test cannot drift apart in either direction. Membership is still
 * pinned literally in the test — the list guards completeness, not the choice.
 *
 * Every row that stood flat here keeps its `data-testid`, its icon and its
 * target; the grouping adds one level above the list it already was. Nothing was
 * dropped: 2 + 7 + 5 = the fourteen rows the sidebar carries.
 *
 * Import-free on purpose: a hook importing it must not close an import cycle.
 */

/**
 * The row ids, spelled once. Declared before the tiers so the union the tiers
 * are typed against is not derived from them (that would be a cycle).
 */
export type SidebarActionEntryId =
  | 'search'
  | 'tasks'
  | 'skills'
  | 'tools'
  | 'helpers'
  | 'agents'
  | 'marketplace'
  | 'files'
  | 'workspaces'
  | 'knowledge'
  | 'library'
  | 'artifacts'
  | 'automations'
  | 'connectors'

/** `ephe.sidebar.tiers` — the JSON map tier-id → open, written on every toggle. */
export const OPEN_TIERS_KEY = 'ephe.sidebar.tiers'

export interface SidebarActionTier {
  /** Stable id: the persistence key fragment and the `data-tier` marker. */
  readonly id: string
  /** i18n key of the head, or null for the headless primary tier. */
  readonly labelKey: string | null
  /** The primary tier is always open — it is the answer to "what is primary". */
  readonly collapsible: boolean
  /** Entry ids in display order. */
  readonly entries: readonly SidebarActionEntryId[]
}

export const SIDEBAR_ACTION_TIERS: readonly SidebarActionTier[] = [
  {
    // Headless on purpose: the New-task pill sits right above it and the two
    // rows below carry the two verbs a person reaches for first — find (⌘K)
    // and the task list. A "primary" label over two rows would be chrome.
    id: 'primary',
    labelKey: null,
    collapsible: false,
    entries: ['search', 'tasks'],
  },
  {
    // What the agent can do, and where it works: the capabilities first, then
    // the runs, the helpers and the swarm those helpers form, the store that
    // adds more, then the two folder surfaces.
    id: 'tools',
    labelKey: 'sidebar.groupTools',
    collapsible: true,
    entries: ['skills', 'tools', 'helpers', 'agents', 'marketplace', 'files', 'workspaces'],
  },
  {
    // Four named surfaces instead of one catch-all head: memory, the workbench,
    // the schedules and the connector shelf each say what they are.
    id: 'more',
    labelKey: 'sidebar.groupMore',
    collapsible: true,
    entries: ['knowledge', 'library', 'artifacts', 'automations', 'connectors'],
  },
]

/** Tier id of the disclosures (everything with a head). */
export type SidebarCollapsibleTierId = Exclude<
  (typeof SIDEBAR_ACTION_TIERS)[number]['id'],
  'primary'
>

export const COLLAPSIBLE_TIER_IDS: readonly SidebarCollapsibleTierId[] =
  SIDEBAR_ACTION_TIERS.filter((tier) => tier.collapsible).map(
    (tier) => tier.id as SidebarCollapsibleTierId,
  )

/** The flat entry ids in display order — the same rows, read as one list. */
export const SIDEBAR_ACTION_ENTRY_IDS: readonly SidebarActionEntryId[] =
  SIDEBAR_ACTION_TIERS.flatMap((tier) => tier.entries)

/** The tier an entry lives in — the answer the test asserts per row. */
export function tierOfEntry(id: SidebarActionEntryId): string {
  const tier = SIDEBAR_ACTION_TIERS.find((t) => t.entries.includes(id))
  return tier?.id ?? 'unknown'
}

/** First run: both disclosures closed, the primary rows are what you see. */
export function readOpenTiers(raw: string | null): Record<SidebarCollapsibleTierId, boolean> {
  const state = { tools: false, more: false } as Record<SidebarCollapsibleTierId, boolean>
  if (!raw) return state
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    for (const id of COLLAPSIBLE_TIER_IDS) {
      if (typeof parsed[id] === 'boolean') state[id] = parsed[id]
    }
  } catch {
    // A corrupt value is not worth a broken sidebar — first run wins.
  }
  return state
}
