import { describe, expect, it } from 'vitest'
import { de, enUS } from 'date-fns/locale'
import { formatDistanceToNowStrict } from 'date-fns'
import {
  dateLocaleFor,
  formatBytes,
  formatDate,
  formatDateTime,
  formatNumber,
  intlLocale,
} from './dateLocale'

// Raw import of every surface source (no fs, runs in jsdom) — same pattern
// as the i18n key lint.
const quellen = import.meta.glob<string>('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('dateLocaleFor', () => {
  it('folgt der aktiven Sprache', () => {
    expect(dateLocaleFor('de')).toBe(de)
    expect(dateLocaleFor('de-DE')).toBe(de)
    expect(dateLocaleFor('DE')).toBe(de)
    expect(dateLocaleFor('en')).toBe(enUS)
    expect(dateLocaleFor('en-GB')).toBe(enUS)
  })

  // src/i18n.ts: fallbackLng 'en', no navigator lookup — without a stored
  // choice the interface stands in English. A 'de' fallback here was the defect.
  it('fällt auf enUS zurück, nicht auf Deutsch', () => {
    expect(dateLocaleFor(undefined)).toBe(enUS)
    expect(dateLocaleFor('')).toBe(enUS)
  })

  it('liefert die Distanz in der Sprachrichtung des Interfaces', () => {
    const twoHours = Date.now() - 2 * 60 * 60 * 1000
    expect(formatDistanceToNowStrict(twoHours, { locale: de, roundingMethod: 'floor' })).toBe(
      '2 Stunden',
    )
    expect(
      formatDistanceToNowStrict(twoHours, { locale: dateLocaleFor('en'), roundingMethod: 'floor' }),
    ).toBe('2 hours')
  })
})

// Finding from the review walk 2026-10-07, with a screenshot: the workbench was German and
// its stamps English — „Geboren Oct 6, 2026, 8:13 PM" above „06.10., 20:13"
// in the row next to it. Four surfaces had their own Intl call and
// asked the machine instead of the language (`undefined` as locale).
describe('intlLocale', () => {
  it('folgt der Flächensprache und fällt wie das Interface auf Englisch', () => {
    expect(intlLocale('de')).toBe('de-DE')
    expect(intlLocale('de-DE')).toBe('de-DE')
    expect(intlLocale('EN')).toBe('en-US')
    expect(intlLocale(undefined)).toBe('en-US')
  })
})

describe('Stempel und Größen in der Sprache der Fläche', () => {
  const iso = '2026-10-06T18:13:02+00:00'

  it('datiert deutsch ohne AM/PM, englisch mit Monatsnamen', () => {
    const deutsch = formatDateTime(iso, 'de')
    expect(deutsch).toMatch(/^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$/)
    expect(deutsch).not.toMatch(/AM|PM/)
    expect(formatDateTime(iso, 'en')).toContain('Oct 6, 2026')
    expect(formatDate(iso, 'de')).toMatch(/^\d{2}\.\d{2}\.\d{4}$/)
  })

  it('zifferngruppieren nach Sprache', () => {
    expect(formatNumber(12483, 'de')).toBe('12.483')
    expect(formatNumber(12483, 'en')).toBe('12,483')
  })

  // Measured, not guessed: Intl with `unit: 'byte'` + `notation: 'compact'`
  // returns on German „166.000 B" and „2,4 Mio. B". Unreadable, hence our own
  // ladder — with the thin space that German notation requires.
  it('größenordnungen mit leerem Zwischenraum vor dem Kürzel', () => {
    expect(formatBytes(6144, 'de')).toBe('6,1 KB')
    expect(formatBytes(6144, 'en')).toBe('6.1 KB')
    expect(formatBytes(166000, 'de')).toBe('166 KB')
    expect(formatBytes(2400000, 'de')).toBe('2,4 MB')
    expect(formatBytes(999, 'de')).toBe('999 B')
  })

  it('sagt nichts Unbestimmtes über eine unlesbare Zeit', () => {
    expect(formatDateTime(null, 'de')).toBe('')
    expect(formatDateTime('morgens', 'de')).toBe('')
  })
})

// The rule that keeps the finding closed: a surface decides its own formats and
// asks neither the operating system nor a language fixed in code. Two machine
// shapes (undefined as the locale; the toLocaleX family with no argument at all)
// and one pinned shape (a literal tag handed to Intl or toLocaleX) are findings
// after wave #55 — this is how a German Mac came to print German grouping into an
// English interface, and how an English interface printed it into a German one.
//
// A pin is allowed once it is declared: the English marker `locale-pin:
// intentional` on the call's own line, or in the comment block directly above it,
// exempts the line. Without that valve the rule eats its own instruments — the
// h23 instrument clock is the same convention in both languages. The machine
// shapes have no exemption: the operator's locale is never a product decision.
describe('Gate: keine Locale-Auskunft beim Rechner', () => {
  const MASKIN = [
    /new Intl\.(?:DateTime|Number|RelativeTime|PluralRules)Format\(\s*undefined\b/,
    /\.toLocale(?:String|TimeString|DateString)\(\s*\)/,
  ]
  const GEPINNT = [
    /new Intl\.(?:DateTime|Number|RelativeTime|PluralRules)Format\(\s*['"](?:en-US|de-DE)['"]/,
    /\.toLocale(?:String|TimeString|DateString)\(\s*['"](?:en-US|de-DE)['"]/,
  ]
  const AUSNAHME = /locale-pin:\s*intentional/
  const TEST_FILE = /\/[^/]+\.(test|spec)\.[tm]sx?$/
  const istKommentar = (zeile: string) => /^\s*(\/\/|\*|\/\*)/.test(zeile)

  function funde(roh: string): string[] {
    const zeilen = roh.split('\n')
    const out: string[] = []
    zeilen.forEach((zeile, i) => {
      const text = zeile.trim()
      if (!text) return
      if (MASKIN.some((muster) => muster.test(zeile))) {
        out.push(`machine: ${text.slice(0, 72)}`)
        return
      }
      if (!GEPINNT.some((muster) => muster.test(zeile))) return
      for (let k = i; k >= 0; k--) {
        const vorher = zeilen[k] ?? ''
        if (AUSNAHME.test(vorher)) return
        if (k < i && !istKommentar(vorher)) break
      }
      out.push(`pinned: ${text.slice(0, 72)}`)
    })
    return out
  }

  const offender = Object.entries(quellen)
    .filter(([pfad]) => !TEST_FILE.test(pfad))
    .flatMap(([pfad, roh]) => funde(roh).map((fund) => `${pfad}  ${fund}`))

  it('ruft in keiner Flächen-Quelle Intl ohne Sprache auf', () => {
    expect(offender).toEqual([])
  })

  it('counter-check: both machine shapes fall when planted', () => {
    const planted = [
      'const a = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })',
      'const b = total.toLocaleString()',
      'const c = stamp.toLocaleTimeString()',
    ]
    for (const line of planted) {
      expect(
        MASKIN.some((pattern) => pattern.test(line)),
        line,
      ).toBe(true)
    }
    // a call that names its language stays clean — the rule is the machine, not Intl
    expect(MASKIN.some((pattern) => pattern.test('total.toLocaleString(intlLocale(lang))'))).toBe(
      false,
    )
  })

  it('counter-check: a pin falls until the marker declares it', () => {
    const pinnedCall = "const nf = (n: number) => n.toLocaleString('en-US')"
    const pinnedIntl = "const f = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 })"
    expect(funde(pinnedCall)).toEqual([`pinned: ${pinnedCall}`])
    expect(funde(pinnedIntl)).toHaveLength(1)
    // the very same call, declared in the comment block above it: exempt
    const declared = [
      '// locale-pin: intentional — a 24h instrument clock is one convention',
      pinnedCall,
    ].join('\n')
    expect(funde(declared)).toEqual([])
    // a language-named call is never a pin
    expect(GEPINNT.some((p) => p.test('n.toLocaleString(intlLocale(lang))'))).toBe(false)
  })
})
