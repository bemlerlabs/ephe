/**
 * S2 — the search, filter, sort and sectioning behind every model picker host.
 *
 * Pure functions over `ModelRow` so the three hosts (setup, engine settings, composer
 * chip) cannot drift into three behaviours, and so the whole rule set is testable
 * without a DOM. The one rule with teeth: an unknown never satisfies a filter. A row
 * whose tools field is null is not a tools model and not a non-tools model, so it stays
 * out of a filtered list and stays visibly unknown in an unfiltered one.
 */
import type { ModelMeta, ModelRow } from './modelPickerTypes'
import { vendorPrefix } from './modelPickerTypes'

export type PickerFilter = 'free' | 'tools' | 'vision' | 'longContext'
export type PickerSort = 'name' | 'freeFirst' | 'context' | 'price'

/** The threshold the "Long context" filter means, in tokens. */
export const LONG_CONTEXT_MIN = 100_000

export const FILTERS: PickerFilter[] = ['free', 'tools', 'vision', 'longContext']
export const SORTS: PickerSort[] = ['name', 'freeFirst', 'context', 'price']

function pick(meta: ModelMeta, filter: PickerFilter): boolean | null {
  if (filter === 'free') return meta.isFree
  if (filter === 'tools') return meta.supportsTools
  if (filter === 'vision') return meta.supportsVision
  return meta.contextWindow === null ? null : meta.contextWindow >= LONG_CONTEXT_MIN
}

/** Every filter has to hold. An unknown fails a filter; no filter passes everything. */
export function matchesFilters(row: ModelRow, filters: PickerFilter[]): boolean {
  return filters.every((filter) => pick(row.meta, filter) === true)
}

/** id, display name and group, trimmed and case-folded — what a query may find. */
export function rowSearchText(row: ModelRow): string {
  return `${row.id} ${row.displayName ?? ''} ${row.group}`.toLowerCase().trim()
}

export function matchesQuery(row: ModelRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return rowSearchText(row).includes(needle)
}

function compareName(a: ModelRow, b: ModelRow): number {
  return (a.displayName || a.id).localeCompare(b.displayName || b.id)
}

/** Known numbers sort before unknown ones, which never take a fake position at either end. */
function compareNumbers(known: (row: ModelRow) => number | null, ascending: boolean) {
  return (a: ModelRow, b: ModelRow): number => {
    const left = known(a)
    const right = known(b)
    if (left === null && right === null) return compareName(a, b)
    if (left === null) return 1
    if (right === null) return -1
    return ascending ? left - right : right - left
  }
}

function compareFreeFirst(a: ModelRow, b: ModelRow): number {
  const rank = (row: ModelRow): number =>
    row.meta.isFree === true ? 0 : row.meta.isFree === false ? 2 : 1
  const delta = rank(a) - rank(b)
  return delta !== 0 ? delta : compareName(a, b)
}

export function sortRows(rows: ModelRow[], sort: PickerSort): ModelRow[] {
  const out = [...rows]
  if (sort === 'context') out.sort(compareNumbers((row) => row.meta.contextWindow, false))
  else if (sort === 'price') out.sort(compareNumbers((row) => row.meta.priceInPerM, true))
  else if (sort === 'freeFirst') out.sort(compareFreeFirst)
  else out.sort(compareName)
  return out
}

export function searchRows(rows: ModelRow[], query: string, filters: PickerFilter[]): ModelRow[] {
  return rows.filter((row) => matchesQuery(row, query) && matchesFilters(row, filters))
}

export interface PickerSection {
  id: string
  /** Locale key the heading reads, so no provider name is invented here. */
  labelKey: string
  /** The group whose rows follow, when this is a provider section. */
  group?: string
  rows: ModelRow[]
}

/** Provider label of a row: the service's own namespace when it has one, else the engine. */
export function groupLabel(row: ModelRow): string {
  return vendorPrefix(row.id) ?? row.group
}

/** Favorites and recents are stored as model ids; a row shown above is not shown twice.
 *
 *  `groupOf` and `groupOrder` exist for a host whose headings are a taxonomy rather than
 *  a provider namespace (the composer keeps chat / other / not configured): the picker
 *  itself passes neither and groups by vendor prefix. */
export function sectionRows(
  rows: ModelRow[],
  favorites: string[],
  recents: string[],
  groupOf?: (row: ModelRow) => string,
  groupOrder?: string[],
): PickerSection[] {
  const taken = new Set<string>()
  const pick = (ids: string[]): ModelRow[] => {
    const out: ModelRow[] = []
    for (const id of ids) {
      for (const row of rows) {
        if (row.id !== id || taken.has(row.key)) continue
        taken.add(row.key)
        out.push(row)
      }
    }
    return out
  }

  const sections: PickerSection[] = []
  const favoriteRows = pick(favorites)
  if (favoriteRows.length)
    sections.push({ id: 'favorites', labelKey: 'modelPicker.favorites', rows: favoriteRows })
  const recentRows = pick(recents)
  if (recentRows.length)
    sections.push({ id: 'recent', labelKey: 'modelPicker.recent', rows: recentRows })

  const label = groupOf ?? groupLabel
  const grouped = new Map<string, ModelRow[]>()
  for (const row of rows) {
    if (taken.has(row.key)) continue
    const key = label(row)
    const bucket = grouped.get(key)
    if (bucket) bucket.push(row)
    else grouped.set(key, [row])
  }
  const rank = (key: string): number => {
    const at = groupOrder?.indexOf(key) ?? -1
    return at >= 0 ? at : (groupOrder?.length ?? 0) + 1
  }
  return sections.concat(
    [...grouped.entries()]
      .sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]))
      .map(([key, bucket]) => ({
        id: `group-${key.replace(/[^a-zA-Z0-9_-]/g, '-')}`,
        labelKey: key,
        group: key,
        rows: bucket,
      })),
  )
}

/** 131072 → "131k"; 8192 → "8.2k"; null → the em-dash the surface prints. */
export function formatContext(tokens: number | null): string | null {
  if (tokens === null || tokens <= 0) return null
  if (tokens < 1000) return String(tokens)
  const thousands = tokens / 1000
  return `${thousands >= 10 ? Math.round(thousands) : Math.round(thousands * 10) / 10}k`
}

/** Two decimals, trailing zeros trimmed: 0.5 → "0.50", 2 → "2", 0.075 → "0.08". */
function money(value: number): string {
  const rounded = Math.round(value * 100) / 100
  return rounded % 1 === 0 ? String(rounded) : rounded.toFixed(2).replace(/0$/, '')
}

/** The price pair, or null when either side is unknown — half a price is no price. */
export function formatPricePair(meta: ModelMeta): { in: string; out: string } | null {
  if (meta.priceInPerM === null || meta.priceOutPerM === null) return null
  return { in: money(meta.priceInPerM), out: money(meta.priceOutPerM) }
}
