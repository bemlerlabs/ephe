/**
 * P6 A2 — the central formatting core: ONE module for the four panel formats
 * (ms, duration, clock, tokens). The duplicates in tabsA.tsx / duration.ts /
 * MessageBubble.tsx delegate here (DRY).
 *
 * Wave #55 added the rule the module did not have: a grouping or a decimal
 * separator is a language decision, so every number formatter here takes the
 * surface language and delegates to dateLocale. The one call that stays pinned
 * says so on its own line, and the gate in dateLocale.test.ts reads that mark.
 */

import { formatNumber } from './dateLocale'

/** Ephe standard: <1s raw ms, <10s two decimals, from 10s one. */
export function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 10000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * Duration in h/m/s, at most 2 units („11m 19s“); the 0s suffix is dropped
 * („1m“ instead of „1m 0s“), below 1000ms raw milliseconds. Negative values
 * clamp to 0.
 */
export function fmtDurationUnits(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.floor(ms))}ms`
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  if (m > 0) return s > 0 ? `${m}m ${s}s` : `${m}m`
  return `${s}s`
}

/** I6-3: the same duration as a clock time — „04:07", from one hour up „1:04:07".
 * The second display form of the `chat.duration_format` control. */
export function fmtClockDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const pad = (n: number) => String(n).padStart(2, '0')
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

// locale-pin: intentional — an instrument clock (h23, fixed width for the
// column) is the same convention in both languages, unlike a grouped number.
const CLOCK_FMT = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  hourCycle: 'h23',
})

/** Fixed HH:MM:SS in local time (hour12:false, locale pinned → deterministic format). */
export function fmtClock(tsSeconds: number): string {
  return CLOCK_FMT.format(new Date(tsSeconds * 1000))
}

/** Token count, grouped the way the surface language groups: „12,345" (en) /
 *  „12.345" (de). Before wave #55 the locale was fixed to en-US, so the German
 *  interface read English grouping in every trajectory row. */
export function fmtTokens(n: number, language?: string): string {
  return formatNumber(n, language)
}

/** Compact form for space-tight rows — the ladder SkyCard used to carry as a
 *  private copy: „1.5M", „12.3k", plain below a thousand. Same thresholds, same
 *  one decimal, and the separator now follows the language („1,5M" in German). */
export function fmtTokensCompact(n: number, language?: string): string {
  if (n >= 1_000_000) return `${formatNumber(n / 1_000_000, language, 1)}M`
  if (n >= 1_000) return `${formatNumber(n / 1_000, language, 1)}k`
  return formatNumber(n, language)
}

/** N5: a signed delta — a positive sign written out explicitly,
 *  a negative one as a typographic minus (U+2212), zero with no sign. */
export function fmtSigned(n: number, language?: string): string {
  if (n > 0) return `+${fmtTokens(n, language)}`
  if (n < 0) return `−${fmtTokens(Math.abs(n), language)}`
  return '0'
}
