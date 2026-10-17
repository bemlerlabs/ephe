import { formatNumber } from './dateLocale'

/**
 * IndexedDB footprint of the session list (R44/P3): N sessions · MB.
 * Pure state derivation — no fetches, testable in jsdom.
 *
 * Both numbers follow the interface language. The status bar splits this string
 * on " · " to keep its digits unshrunken, so the separator has to stay exactly
 * one " · " and no formatted number may contain it.
 */
export function storageFootprint(
  sessions: unknown[] | undefined,
  language?: string,
): string | null {
  if (!sessions?.length) return null
  try {
    const bytes = new Blob([JSON.stringify(sessions)]).size
    const mb = Math.max(0.01, Math.round((bytes / (1024 * 1024)) * 100) / 100)
    return `${formatNumber(sessions.length, language)} · ${formatNumber(mb, language, 2)}`
  } catch {
    return null
  }
}
