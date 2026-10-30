/**
 * The one list the Discover area reads from. Seven endpoints answer for it, each
 * of which may fail on its own, so every row says where it came from and a card
 * only shows a number the endpoint actually sent.
 */
import type { McpCatalogEntry, McpHealthServer, McpSettings, SkillSummary } from '@/lib/api'
import type { MarketHome, MarketIndexBody, MarketInstalledRow, ToolUsageView } from '@/lib/api'

export type DiscoverKind = 'skill' | 'connector' | 'plugin'

/** `all` plus one tab per kind; the tab heads carry the counts of their kind. */
export type DiscoverTab = DiscoverKind | 'all'

export interface DiscoverItem {
  id: string
  kind: DiscoverKind
  name: string
  title: string
  summary: string
  /** Who shipped it: a source title, a publisher, or the word for "in the box". */
  origin: string
  categories: string[]
  /** Already on this machine, so the main verb on the card is enable rather than add. */
  installed: boolean
  enabled: boolean
  version?: string
  /** Tools a connector brings with it — the only count a connector can show. */
  toolCount?: number
  latencyMs?: number
  offline?: boolean
  /** The launch line a connector is attached with, when one is known. */
  spec?: string
  /** Calls measured in the audit log, when the item names a tool that was used. */
  calls?: number
  /** The listing page this entry was drawn from, for the detail surface. */
  docs?: string
  /** The launch line the publisher suggests, when the entry is not attached yet. */
  installHint?: string
  /** Credential names the publisher requires; a value is never part of an item. */
  requiredEnv?: { name: string; secret: boolean }[]
  /** Provenance the card can show: our selection, freshly published, or in the box. */
  badge?: 'pick' | 'recent' | 'bundled'
}

/** One curated registry tier row, served by /api/discover/bootstrap. */
export interface RegistryEntry {
  id: string
  name: string
  description: string
  category: string
  install_hint: string
  docs: string
  version: string
  published_at: string
  source: string
  curated_reason?: 'pick' | 'recent'
  /** Names a publisher declares as required; values live in the vault, never here. */
  required_env?: { name: string; secret: boolean }[]
}

export interface DiscoverSources {
  skills: SkillSummary[]
  mcp: McpSettings | null
  health: McpHealthServer[]
  catalog: McpCatalogEntry[]
  registry: RegistryEntry[]
  registryCount: number
  home: MarketHome | null
  index: MarketIndexBody | null
  installed: MarketInstalledRow[]
  usage: ToolUsageView | null
}

const desc = (value: string | Record<string, string> | undefined): string => {
  if (!value) return ''
  if (typeof value === 'string') return value
  const values = Object.values(value)
  return String(values[0] ?? '')
}

/** `npx:weather` and `uvx:maps@1` both name themselves after the colon. */
export const specName = (spec: string): string => {
  const tail = spec.includes(':') ? spec.slice(spec.lastIndexOf(':') + 1) : spec
  const head = tail.replace(/^@/, '').split('@')[0] ?? ''
  return head.split('/').pop() || spec
}

const byName = <T extends { name: string }>(rows: T[]): Map<string, T> =>
  new Map(rows.map((row) => [row.name, row]))

export const kindOf = (tab: DiscoverTab): DiscoverKind | null => (tab === 'all' ? null : tab)

export function buildItems(sources: DiscoverSources): DiscoverItem[] {
  const items: DiscoverItem[] = []
  const usedCalls = new Map((sources.usage?.tools ?? []).map((one) => [one.tool, one.calls]))
  const installedPlugins = byName(sources.installed)

  for (const skill of sources.skills) {
    items.push({
      id: `skill:${skill.name}`,
      kind: 'skill',
      name: skill.name,
      title: skill.name,
      summary: skill.description ?? '',
      origin: skill.is_builtin ? 'bundled' : 'local',
      categories: skill.trigger ? [skill.trigger] : [],
      installed: true,
      enabled: !skill.disabled,
      version: skill.version,
      calls: usedCalls.get(skill.name),
    })
  }

  const configured = new Set((sources.mcp?.servers ?? []).map(specName))
  const catalog = byName(sources.catalog)
  for (const probe of sources.health) {
    const known = catalog.get(specName(probe.spec))
    items.push({
      id: `connector:${specName(probe.spec)}`,
      kind: 'connector',
      name: specName(probe.spec),
      title: known?.name ?? specName(probe.spec),
      summary: known ? desc(known.description) : probe.transport,
      origin: known?.category ? 'catalog' : 'yours',
      categories: known?.category ? [known.category] : [],
      installed: configured.has(specName(probe.spec)),
      enabled: probe.status === 'ok',
      toolCount: probe.tool_count,
      latencyMs: probe.latency_ms ?? undefined,
      offline: probe.status !== 'ok',
      spec: probe.spec,
    })
  }

  for (const entry of sources.catalog) {
    if (sources.health.some((probe) => specName(probe.spec) === entry.name)) continue
    items.push({
      id: `connector:${entry.name}`,
      kind: 'connector',
      name: entry.name,
      title: entry.name,
      summary: desc(entry.description_en) || desc(entry.description),
      origin: 'catalog',
      categories: entry.category ? [entry.category] : [],
      installed: configured.has(entry.name),
      enabled: false,
      spec: entry.spec ?? entry.install_hint,
      badge: 'bundled',
    })
  }

  for (const entry of sources.registry) {
    if (configured.has(entry.name)) continue
    if (sources.catalog.some((known) => known.name === entry.name)) continue
    items.push({
      id: `connector:registry:${entry.id}`,
      kind: 'connector',
      name: entry.name,
      title: entry.name,
      summary: entry.description,
      origin: 'registry',
      categories: [entry.category],
      installed: false,
      enabled: false,
      version: entry.version,
      docs: entry.docs,
      installHint: entry.install_hint,
      badge: entry.curated_reason === 'recent' ? 'recent' : 'pick',
      requiredEnv: entry.required_env ?? [],
    })
  }

  for (const plugin of sources.index?.plugins ?? []) {
    const owned = installedPlugins.get(plugin.name)
    items.push({
      id: `plugin:${plugin.name}`,
      kind: 'plugin',
      name: plugin.name,
      title: plugin.displayName || plugin.name,
      summary: desc(plugin.description),
      origin: plugin.publisher?.name || 'unknown',
      categories: plugin.categories ?? [],
      installed: Boolean(owned),
      enabled: owned ? owned.enabled : false,
      version: plugin.versions?.[0]?.version,
    })
  }

  return items
}

export interface DiscoverQuery {
  tab: DiscoverTab
  query: string
  category: string | null
  origin: string | null
}

/** Search covers the words a person would type, so it reads title, name and summary. */
export function filterItems(
  items: DiscoverItem[],
  q: DiscoverQuery,
  intentIds: string[] = [],
): DiscoverItem[] {
  const needle = q.query.trim().toLowerCase()
  const kind = kindOf(q.tab)
  const intent = new Set(intentIds)
  return items.filter((item) => {
    if (kind && item.kind !== kind) return false
    if (q.category && !item.categories.includes(q.category)) return false
    if (q.origin && item.origin !== q.origin) return false
    if (!needle) return true
    if (intent.has(item.id)) return true
    return (
      item.title.toLowerCase().includes(needle) ||
      item.name.toLowerCase().includes(needle) ||
      item.summary.toLowerCase().includes(needle)
    )
  })
}

/** The intent ranking wins over page order; an unranked item keeps its place behind. */
export function rankByIntent(items: DiscoverItem[], intentIds: string[]): DiscoverItem[] {
  if (!intentIds.length) return items
  const order = new Map(intentIds.map((id, index) => [id, index]))
  return [...items].sort(
    (a, b) =>
      (order.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.id) ?? Number.MAX_SAFE_INTEGER),
  )
}

export function countByTab(items: DiscoverItem[]): Record<DiscoverTab, number> {
  const counts: Record<DiscoverTab, number> = {
    all: items.length,
    skill: 0,
    connector: 0,
    plugin: 0,
  }
  for (const item of items) counts[item.kind] += 1
  return counts
}

/** The chips only ever offer a value the loaded items carry. */
export function facetValues(
  items: DiscoverItem[],
  pick: (item: DiscoverItem) => string[],
): string[] {
  const set = new Set<string>()
  for (const item of items) for (const one of pick(item)) if (one) set.add(one)
  return [...set].sort()
}

/** The first card is the one the page presents large: installed and most used wins. */
export function heroOf(items: DiscoverItem[]): DiscoverItem | null {
  if (!items.length) return null
  const used = [...items].sort(
    (a, b) =>
      Number(b.installed) - Number(a.installed) ||
      Number(b.enabled) - Number(a.enabled) ||
      (b.calls ?? 0) - (a.calls ?? 0),
  )
  return used[0] ?? null
}

/** Three cards of our own top items — the calm opening the page makes its claim with. */
export function bentoOf(items: DiscoverItem[]): DiscoverItem[] {
  return items
    .filter((item) => item.origin === 'bundled')
    .sort(
      (a, b) =>
        (b.calls ?? 0) - (a.calls ?? 0) ||
        Number(b.enabled) - Number(a.enabled) ||
        a.title.localeCompare(b.title),
    )
    .slice(0, 3)
}
