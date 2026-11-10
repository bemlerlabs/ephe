'use client'

import { TAB_KEYS, type Tab } from './primitives'

/**
 * Shape-checked reads for the panel's persisted state (ephe.panel.*).
 *
 * #39: invalid JSON was survivable, JSON of the WRONG SHAPE was not — a stored
 * `{"a":1}` under `ephe.panel.tabs` reached the boot's `.map`, a `[null]` under
 * `ephe.panel.recent` reached `.tab`, and the pane came up with a TypeError.
 * The guard belongs at the read, not in a try/catch around the boot: `readStored`
 * takes the default and the shape check together, so every call site has to name
 * what a valid value looks like, and a hand-edited or version-skewed key can only
 * ever fall back to the documented default instead of reaching the render.
 */

export type Dock = 'left' | 'right'
export type RecentEntry = { tab: Tab; closedAt: number }

/** A boot with no usable stored inventory opens the first page. */
export const DEFAULT_TABS: Tab[] = ['preview']
export const DEFAULT_DOCK: Dock = 'right'
/** The pane's fit width — also the fallback for a stored width that is not sane. */
export const FIT_WIDTH = 420
/** Nothing but the drag writes this key, and the drag never goes below 360. */
export const MIN_WIDTH = 360
/** Sanity roof; the layout still clamps the rendered pane to 60vw / 95vw. */
const MAX_STORED_WIDTH = 10_000

/** The stored form of a recent entry before the page name is narrowed to a Tab. */
type StoredRecentEntry = { tab: string; closedAt: number }

function parseJson(raw: string): unknown {
  return JSON.parse(raw) as unknown
}

/**
 * The one read path: an absent key, invalid JSON and a value of the wrong form all
 * deliver the default. `decode` turns the raw string into the value that
 * `isShape` checks — dock and width are stored plain, the inventories as JSON.
 */
export function readStored<T>(
  key: string,
  fallback: T,
  isShape: (value: unknown) => value is T,
  decode: (raw: string) => unknown = parseJson,
): T {
  const raw = localStorage.getItem(key)
  if (!raw) return fallback
  let value: unknown
  try {
    value = decode(raw)
  } catch {
    return fallback
  }
  return isShape(value) ? value : fallback
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Stored inventories from older builds carry keys the inventory no longer has
 * ('browser' from before the B5 dedup, 'url' from the pane's first name). Both
 * mean the one url pane.
 */
export function aliasTab(value: string): Tab {
  return value === 'browser' || value === 'url' ? 'preview' : (value as Tab)
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === 'string')
}

function isActiveTabName(value: unknown): value is Tab {
  return typeof value === 'string'
}

export function isRecentList(value: unknown): value is StoredRecentEntry[] {
  return (
    Array.isArray(value) &&
    value.every(
      (entry) =>
        isRecord(entry) &&
        typeof entry.tab === 'string' &&
        typeof entry.closedAt === 'number' &&
        Number.isFinite(entry.closedAt),
    )
  )
}

export function isDock(value: unknown): value is Dock {
  return value === 'left' || value === 'right'
}

export function isWidth(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= MIN_WIDTH &&
    value <= MAX_STORED_WIDTH
  )
}

/**
 * The open pills. A list that keeps nothing at all after the alias/filter was not
 * written by this panel — the boot default keeps the pane usable. An empty list IS
 * a state this panel writes (every pill closed) and survives as empty.
 */
export function readTabs(): Tab[] {
  const stored = readStored<string[]>('ephe.panel.tabs', DEFAULT_TABS, isStringList)
  const kept = stored.map(aliasTab).filter((tab) => TAB_KEYS.includes(tab))
  return stored.length > 0 && kept.length === 0 ? [...DEFAULT_TABS] : kept
}

/** Recently closed pills; the entry's closedAt is what the menu renders as age. */
export function readRecent(): RecentEntry[] {
  return readStored<StoredRecentEntry[]>('ephe.panel.recent', [], isRecentList)
    .filter((entry) => TAB_KEYS.some((tab) => tab === entry.tab))
    .map((entry) => ({ ...entry, tab: aliasTab(entry.tab) }))
}

/**
 * The active page, stored JSON-encoded like tabs/recent. The build before #47
 * wrote the bare page name, so a parse failure carries the legacy form here, and a broken
 * value — the shape check still rejects objects/numbers/null.
 */
export function readActiveTab(): Tab | null {
  const decodeLegacy = (raw: string): unknown => {
    try {
      return parseJson(raw)
    } catch {
      return raw
    }
  }
  return readStored<Tab | null>('ephe.panel.activeTab', null, isActiveTabName, decodeLegacy)
}

/** Dock side, stored plain (not JSON-encoded). */
export function readDock(): Dock {
  return readStored<Dock>('ephe.panel.dock', DEFAULT_DOCK, isDock, (raw) => raw)
}

/** Pane width in px, stored as a decimal string. */
export function readWidth(): number {
  return readStored<number>('ephe.panel.width', FIT_WIDTH, isWidth, Number)
}
