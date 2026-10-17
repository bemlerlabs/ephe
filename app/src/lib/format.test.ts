/**
 * P6 A2 — central format core: ONE module for ms/duration/clock/tokens.
 * The asserts come exactly from the plan (Task A2, Ephe-standard scope).
 */
import { describe, it, expect } from 'vitest'
import {
  fmtMs,
  fmtDurationUnits,
  fmtClock,
  fmtTokens,
  fmtTokensCompact,
  fmtSigned,
} from '@/lib/format'

describe('fmtMs (Ephe-Norm)', () => {
  it('unter 1000ms: rohe Millisekunden', () => {
    expect(fmtMs(850)).toBe('850ms')
    expect(fmtMs(0)).toBe('0ms')
  })

  it('unter 10s: zwei Dezimalstellen in Sekunden', () => {
    expect(fmtMs(5000)).toBe('5.00s')
    expect(fmtMs(1000)).toBe('1.00s')
  })

  it('ab 10s: eine Dezimalstelle in Sekunden', () => {
    expect(fmtMs(17000)).toBe('17.0s')
    expect(fmtMs(60000)).toBe('60.0s')
  })
})

describe('fmtDurationUnits (max 2 Units, 0s-Suffix entfällt)', () => {
  it('unter 1000ms: rohe Millisekunden', () => {
    expect(fmtDurationUnits(850)).toBe('850ms')
    expect(fmtDurationUnits(0)).toBe('0ms')
  })

  it('Minuten + Sekunden, 0s-Suffix entfällt', () => {
    expect(fmtDurationUnits(679000)).toBe('11m 19s')
    expect(fmtDurationUnits(60000)).toBe('1m')
    expect(fmtDurationUnits(84000)).toBe('1m 24s')
    expect(fmtDurationUnits(29400)).toBe('29s')
  })

  it('Stunden: max 2 Units (h/m), Sekunden fallen weg', () => {
    expect(fmtDurationUnits(3600000)).toBe('1h')
    expect(fmtDurationUnits(4200000)).toBe('1h 10m')
    expect(fmtDurationUnits(3661000)).toBe('1h 1m')
  })

  it('negative Werte werden auf 0 geklemmt', () => {
    expect(fmtDurationUnits(-5)).toBe('0ms')
  })
})

describe('fmtClock (Intl, en-US fix, hour12:false, Lokalzeit)', () => {
  // Expectation derived with identical options from the test host's local
  // time — the contract (locale, digits, hour12) stays pinned.
  const EXPECT_FMT = new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    hourCycle: 'h23',
  })
  it('deterministischer HH:MM:SS aus fixem Epoch', () => {
    expect(fmtClock(1700000000)).toBe(EXPECT_FMT.format(new Date(1700000000 * 1000)))
    expect(fmtClock(1700002800)).toBe(EXPECT_FMT.format(new Date(1700002800 * 1000)))
    expect(fmtClock(1700000000)).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })
})

/**
 * Wave #55: a grouping and a decimal separator are a language decision. Both
 * readings are pinned below as literals per language — never rebuilt from the
 * formatter the test checks, which would follow whoever runs it. fmtClock above
 * stays pinned on purpose: an h23 instrument clock is the same convention in
 * both languages, and it carries the marker the locale gate reads.
 */
describe('fmtTokens / fmtSigned / fmtTokensCompact — the language groups', () => {
  it('english groups with the comma', () => {
    expect(fmtTokens(12345, 'en')).toBe('12,345')
    expect(fmtTokens(1234567, 'en')).toBe('1,234,567')
    expect(fmtTokens(0, 'en')).toBe('0')
    expect(fmtSigned(1204, 'en')).toBe('+1,204')
    expect(fmtSigned(-1204, 'en')).toBe('−1,204')
    expect(fmtSigned(0, 'en')).toBe('0')
  })

  it('german groups with the point', () => {
    expect(fmtTokens(12345, 'de')).toBe('12.345')
    expect(fmtTokens(1234567, 'de')).toBe('1.234.567')
    expect(fmtTokens(0, 'de')).toBe('0')
    expect(fmtSigned(1204, 'de')).toBe('+1.204')
    expect(fmtSigned(-1204, 'de')).toBe('−1.204')
  })

  it('the compact ladder keeps its thresholds and takes its separator from the language', () => {
    expect(fmtTokensCompact(1_523_456, 'en')).toBe('1.5M')
    expect(fmtTokensCompact(12_345, 'en')).toBe('12.3k')
    expect(fmtTokensCompact(999, 'en')).toBe('999')
    expect(fmtTokensCompact(1_523_456, 'de')).toBe('1,5M')
    expect(fmtTokensCompact(12_345, 'de')).toBe('12,3k')
    expect(fmtTokensCompact(999, 'de')).toBe('999')
  })

  it('with no language stored the surface is English, and so is the number', () => {
    expect(fmtTokens(12345)).toBe('12,345')
    expect(fmtTokensCompact(12_345)).toBe('12.3k')
  })
})
