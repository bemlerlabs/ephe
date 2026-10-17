import { describe, it, expect } from 'vitest'
import { sessionCostUsd, formatUsd, cacheSharePercent } from './cost'

describe('sessionCostUsd (Welle 3, Cost-Monitor)', () => {
  const pricing = { in_per_m: 0.05, out_per_m: 0.4 }

  it('rechntet in/out × USD je 1M Token', () => {
    // 1M in + 0.5M out → 0.05 + 0.20 = 0.25
    expect(sessionCostUsd({ in: 1_000_000, out: 500_000, cached: 0 }, pricing)).toBeCloseTo(0.25)
  })

  it('mikroskopische Sitzungen ergeben kleine aber echte Werte', () => {
    // 1000 in + 500 out → 0.00005 + 0.0002 = 0.00025
    expect(sessionCostUsd({ in: 1000, out: 500, cached: 0 }, pricing)).toBeCloseTo(0.00025)
  })

  it('null ohne Preise oder ohne Nutzung — nie eine Zahl raten', () => {
    expect(sessionCostUsd({ in: 100, out: 100, cached: 0 }, null)).toBeNull()
    expect(sessionCostUsd({ in: 0, out: 0, cached: 0 }, pricing)).toBeNull()
    expect(sessionCostUsd(null, pricing)).toBeNull()
  })
})

describe('formatUsd', () => {
  it('Mikrobeträge mit 4 Stellen, sonst 2', () => {
    expect(formatUsd(0.00025)).toBe('$0.0003')
    expect(formatUsd(1.234)).toBe('$1.23')
    expect(formatUsd(0)).toBe('$0.00')
  })
})

describe('cacheSharePercent (Welle 3, Prompt-Cache-Chip)', () => {
  it('bevorzugt den letzten Turn', () => {
    const totals = { in: 10_000, out: 0, cached: 1_000 }
    expect(cacheSharePercent(totals, { in: 1_000, cached: 500 })).toBe(50)
  })

  it('fällt auf die Sitzungssumme zurück', () => {
    expect(cacheSharePercent({ in: 10_000, out: 0, cached: 2_500 }, null)).toBe(25)
  })

  it('null ohne gemessene Cache-Felder', () => {
    expect(cacheSharePercent({ in: 100, out: 0, cached: 0 }, { in: 100, cached: 0 })).toBeNull()
    expect(cacheSharePercent(null, null)).toBeNull()
  })
})
