import { describe, it, expect } from 'vitest'
import { sessionCostUsd, formatUsd, cacheSharePercent } from './cost'

describe('sessionCostUsd (Wave 3, cost monitor)', () => {
  const pricing = { in_per_m: 0.05, out_per_m: 0.4 }

  it('bills in/out times USD per 1M tokens', () => {
    // 1M in + 0.5M out → 0.05 + 0.20 = 0.25
    expect(sessionCostUsd({ in: 1_000_000, out: 500_000, cached: 0 }, pricing)).toBeCloseTo(0.25)
  })

  it('microscopic sessions give small but real values', () => {
    // 1000 in + 500 out → 0.00005 + 0.0002 = 0.00025
    expect(sessionCostUsd({ in: 1000, out: 500, cached: 0 }, pricing)).toBeCloseTo(0.00025)
  })

  it('null without prices or usage, never a guessed number', () => {
    expect(sessionCostUsd({ in: 100, out: 100, cached: 0 }, null)).toBeNull()
    expect(sessionCostUsd({ in: 0, out: 0, cached: 0 }, pricing)).toBeNull()
    expect(sessionCostUsd(null, pricing)).toBeNull()
  })
})

describe('formatUsd', () => {
  it('micro amounts with 4 digits, otherwise 2', () => {
    expect(formatUsd(0.00025)).toBe('$0.0003')
    expect(formatUsd(1.234)).toBe('$1.23')
    expect(formatUsd(0)).toBe('$0.00')
  })
})

describe('cacheSharePercent (Wave 3, prompt cache chip)', () => {
  it('prefers the last turn', () => {
    const totals = { in: 10_000, out: 0, cached: 1_000 }
    expect(cacheSharePercent(totals, { in: 1_000, cached: 500 })).toBe(50)
  })

  it('falls back to the session sum', () => {
    expect(cacheSharePercent({ in: 10_000, out: 0, cached: 2_500 }, null)).toBe(25)
  })

  it('null without measured cache fields', () => {
    expect(cacheSharePercent({ in: 100, out: 0, cached: 0 }, { in: 100, cached: 0 })).toBeNull()
    expect(cacheSharePercent(null, null)).toBeNull()
  })
})
