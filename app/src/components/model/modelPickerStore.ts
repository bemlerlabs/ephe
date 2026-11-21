/**
 * S2 — favorites and recents, on the device.
 *
 * Two localStorage lists keyed by the model tag. Nothing is sent anywhere and no server
 * store exists: a picker preference is this device's, the same way the composer history
 * is (AGENTS.md: local-first, no account). A malformed or non-array payload reads as
 * empty rather than throwing at open.
 */
export const FAVORITES_KEY = 'ephe.modelPicker.favorites'
export const RECENTS_KEY = 'ephe.modelPicker.recents'
/** The list a returning user should recognise, not a log. */
export const RECENTS_MAX = 8

function store(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

/** The ids of one list in stored order. A broken entry is dropped; the rest of the list stands. */
export function readIds(key: string): string[] {
  const raw = store()?.getItem(key)
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
  } catch {
    return []
  }
}

function writeIds(key: string, ids: string[]): void {
  try {
    store()?.setItem(key, JSON.stringify(ids))
  } catch {
    // A full or blocked store is a preference that did not persist; the list still works.
  }
}

export function isFavorite(id: string, favorites: string[]): boolean {
  return favorites.includes(id)
}

/** Add or remove one id, returning the new list so the caller owns the state. */
export function toggleFavorite(id: string, favorites: string[]): string[] {
  const next = favorites.includes(id)
    ? favorites.filter((entry) => entry !== id)
    : [...favorites, id]
  writeIds(FAVORITES_KEY, next)
  return next
}

/** Most recent first, capped, and never duplicated. */
export function rememberRecent(id: string, recents: string[]): string[] {
  const next = [id, ...recents.filter((entry) => entry !== id)].slice(0, RECENTS_MAX)
  writeIds(RECENTS_KEY, next)
  return next
}

export function readFavorites(): string[] {
  return readIds(FAVORITES_KEY)
}

export function readRecents(): string[] {
  return readIds(RECENTS_KEY)
}
