/**
 * Wave #55: the evidence rows are read as numbers, so their grouping belongs to
 * the interface language. The helpers used to keep a `catch` that asked the
 * machine when the tag looked invalid — which is how a German Mac produced
 * „1.2" inside an English surface. `intlLocale` hands Intl a tag it always
 * accepts, so there is nothing left to catch and nobody left to ask.
 *
 * Literals per language, measured against Intl before written.
 */
import { describe, it, expect } from 'vitest'
import { auditNumber, auditDuration } from './auditFormat'

describe('auditFormat — the surface language decides the number', () => {
  it('german groups with the point, separates the decimal with a comma', () => {
    expect(auditNumber(12345.6, 'de')).toBe('12.345,6')
    expect(auditDuration(1234, 'de')).toBe('1,2 s')
    expect(auditDuration(942, 'de')).toBe('942 ms')
  })

  it('english groups with the comma, separates the decimal with a point', () => {
    expect(auditNumber(12345.6, 'en')).toBe('12,345.6')
    expect(auditDuration(1234, 'en')).toBe('1.2 s')
    expect(auditDuration(942, 'en')).toBe('942 ms')
  })

  it('an unreadable tag reads English, the way the interface falls back', () => {
    expect(auditNumber(12345.6, '')).toBe('12,345.6')
  })

  it('one column, one separator: ms and s share the path', () => {
    expect(`${auditDuration(1234, 'de')} / ${auditDuration(942, 'de')}`).toBe('1,2 s / 942 ms')
    expect(`${auditDuration(1234, 'en')} / ${auditDuration(942, 'en')}`).toBe('1.2 s / 942 ms')
  })
})
