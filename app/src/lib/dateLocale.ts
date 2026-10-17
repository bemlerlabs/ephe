import { de } from 'date-fns/locale/de'
import { enUS } from 'date-fns/locale/en-US'

/* Both locales by path: `date-fns/locale` re-exports 200+, and vite.config.ts puts
 * these two modules in the `dates` chunk instead of the entry chunk. */

/** date-fns follows the active language. The fallback value is enUS, not de:
 *  src/i18n.ts has fallbackLng 'en' and no navigator lookup — with no stored
 *  choice the interface stands in English, while the sidebar dated strictly in
 *  German ("2 Stunden" inside the English UI). */
export function dateLocaleFor(language?: string) {
  return (language ?? 'en').toLowerCase().startsWith('de') ? de : enUS
}

/** The same decision for `Intl`: the user's machine is not asked along.
 *  Measured at the workbench — a German interface showed there
 *  „Nov 5, 2026, 7:13 PM" and „6KB", because the formatters received
 *  `undefined` as their locale and thereby followed the browser default. */
export function intlLocale(language?: string): string {
  return (language ?? 'en').toLowerCase().startsWith('de') ? 'de-DE' : 'en-US'
}

/* The four formats that sit side by side on one page must speak the same
 * language. Before, every surface had its own Intl call — and four of them
 * asked the machine (`undefined`), so the German interface put
 * „Nov 5, 2026, 7:13 PM" next to „06.10., 20:13". */

/** Date with the time down to the minute. '' when the stamp is unreadable. */
export function formatDateTime(iso: string | null | undefined, language?: string): string {
  return stamp(iso, language, { dateStyle: 'medium', timeStyle: 'short' })
}

/** The date only. */
export function formatDate(iso: string | null | undefined, language?: string): string {
  return stamp(iso, language, { dateStyle: 'medium' })
}

function stamp(
  iso: string | null | undefined,
  language: string | undefined,
  opts: Intl.DateTimeFormatOptions,
): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  try {
    return new Intl.DateTimeFormat(intlLocale(language), opts).format(date)
  } catch {
    return iso
  }
}

/** Bytes with a blank space before the unit — „6,1 KB" (de) / „6.1 KB" (en).
 *
 * Deliberately not `Intl … style:'unit', unit:'byte', notation:'compact'`: that
 * yields „166.000 B" and „2,4 Mio. B" in German (measured, V8/ICU), which is
 * exactly the number nobody can read. The ladder lives here, the number follows
 * the language. */
export function formatBytes(bytes: number, language?: string): string {
  if (!Number.isFinite(bytes)) return '—'
  const stufen: [number, string][] = [
    [1e12, 'TB'],
    [1e9, 'GB'],
    [1e6, 'MB'],
    [1e3, 'KB'],
  ]
  for (const [grenze, einheit] of stufen) {
    if (Math.abs(bytes) >= grenze) {
      return `${formatNumber(bytes / grenze, language, 1)} ${einheit}`
    }
  }
  return `${formatNumber(bytes, language, 0)} B`
}

/** A number in the language of the surface, without invented decimal places. */
export function formatNumber(value: number, language?: string, digits = 0): string {
  try {
    return new Intl.NumberFormat(intlLocale(language), { maximumFractionDigits: digits }).format(
      value,
    )
  } catch {
    return String(value)
  }
}

/**
 * One decimal, always shown, in the language of the surface.
 *
 * `formatNumber` above deliberately never invents a decimal, and that is right for
 * counts. A rate readout is the opposite case: "0 tok/s" reads as "no answer" where
 * the value is a tenth, and the context ring below 10 % exists precisely to show a
 * fraction that has not rounded up yet.
 */
export function formatRate(value: number, language?: string): string {
  try {
    return new Intl.NumberFormat(intlLocale(language), {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value)
  } catch {
    return value.toFixed(1)
  }
}
