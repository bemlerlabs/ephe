/**
 * D5 / D6: every number in the status row and the composer ring speaks the
 * interface language.
 *
 * Measured 2026-10-10 in a German interface: one row printed "72.63%" and
 * "~0.29 MB" with a dot next to "5.950 tok" and "2.242 frei" with a comma — the
 * row had been made locale-driven in eight places and these two had been left
 * behind, because `formatPercent` took no language at all and `storageFootprint`
 * interpolated a raw number that the status bar then splits back apart.
 *
 * The dot-decimal instances that cannot be photographed today (the live tok/s and
 * TTFT need a running turn, the expiry notice needs an expiring artifact) are
 * covered here at the formatter level instead.
 */
import { describe, it, expect } from 'vitest'
import { formatPercent } from './contextMeter'
import { formatRate } from './dateLocale'
import { storageFootprint } from './storageFootprint'
import { contextRingLabel } from '@/components/dashboard/ChatInput'

describe('formatPercent', () => {
  it('follows the interface language', () => {
    expect(formatPercent(72.63, 'en')).toBe('72.63%')
    expect(formatPercent(72.63, 'de')).toBe('72,63%')
  })

  it('invents no decimal places', () => {
    expect(formatPercent(43, 'de')).toBe('43%')
    expect(formatPercent(43, 'en')).toBe('43%')
  })

  it('stays an English number when no language is given', () => {
    expect(formatPercent(72.63)).toBe('72.63%')
  })
})

describe('formatRate', () => {
  it('always shows the one decimal, in the language of the surface', () => {
    expect(formatRate(3.75, 'en')).toBe('3.8')
    expect(formatRate(3.75, 'de')).toBe('3,8')
    expect(formatRate(0, 'de')).toBe('0,0')
    expect(formatRate(0.04, 'en')).toBe('0.0')
  })
})

describe('storageFootprint', () => {
  const sessions = [{ id: 'a' }, { id: 'b' }]

  it('keeps exactly one separator between the two numbers', () => {
    for (const lng of ['en', 'de']) {
      const parts = (storageFootprint(sessions, lng) ?? '').split(' · ')
      expect(parts.length).toBe(2)
      expect(parts[0]).toBe('2')
      expect(parts[1]!.length).toBeGreaterThan(0)
    }
  })

  it('prints the megabyte piece with the language separator', () => {
    expect(storageFootprint(sessions, 'de')!.split(' · ')[1]).toMatch(/^[0-9]+,[0-9]+$/)
    expect(storageFootprint(sessions, 'en')!.split(' · ')[1]).toMatch(/^[0-9]+\.[0-9]+$/)
  })

  it('says nothing without sessions', () => {
    expect(storageFootprint([], 'de')).toBeNull()
    expect(storageFootprint(undefined, 'de')).toBeNull()
  })
})

describe('contextRingLabel', () => {
  const stub = (_k: string, o?: Record<string, unknown>) => `Context used: ${String(o?.percent)}%`

  it('carries a localized percent below ten', () => {
    expect(contextRingLabel(stub, 3.75, 'de')).toBe('Context used: 3,8%')
    expect(contextRingLabel(stub, 3.75, 'en')).toBe('Context used: 3.8%')
  })

  it('rounds to a whole localized number from ten up', () => {
    expect(contextRingLabel(stub, 42.6, 'de')).toBe('Context used: 43%')
  })

  it('never leaves the ring at a bare zero', () => {
    expect(contextRingLabel(stub, null, 'de')).toBe('Context used: 0,0%')
  })
})
