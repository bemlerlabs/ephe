/**
 * Ephe — PWA chat UX plan, task A2: thinking-duration labels
 *
 * GIVEN  formatThinkingLabel / formatDurationShort from lib/thinking.ts
 * WHEN   fed different durations (a fake `t` that records keys/interpolation
 *        into a Map — tests the helper without any i18n init)
 * THEN   under 3s: thoughtBriefly, ≥ 3s: thoughtForSeconds + the correct
 *        duration ("4s", "1m 5s")
 */
import { describe, it, expect } from 'vitest'
import { formatDurationShort, formatThinkingLabel, THRESHOLD_MS } from './thinking'

type FakeT = (key: string, opts?: Record<string, unknown>) => string

function makeT(): { t: FakeT; calls: Array<{ key: string; opts?: Record<string, unknown> }> } {
  const calls: Array<{ key: string; opts?: Record<string, unknown> }> = []
  const t: FakeT = (key, opts) => {
    calls.push({ key, opts })
    return opts ? `${key}(${String(opts.duration ?? '')})` : key
  }
  return { t, calls }
}

describe('formatDurationShort', () => {
  it('unter 1 Minute: ganze Sekunden + "s"', () => {
    expect(formatDurationShort(4_000)).toBe('4s')
    expect(formatDurationShort(5_999)).toBe('6s') // rounds up
    expect(formatDurationShort(1_200)).toBe('1s')
  })

  it('ab 1 Minute: "Nm Ss"-Format', () => {
    expect(formatDurationShort(65_000)).toBe('1m 5s')
    expect(formatDurationShort(359_000)).toBe('5m 59s')
    expect(formatDurationShort(60_000)).toBe('1m 0s')
  })

  it('negativer Input: 0s (kein negatives Label)', () => {
    expect(formatDurationShort(-500)).toBe('0s')
  })
})

describe('formatThinkingLabel', () => {
  it(`unter ${THRESHOLD_MS}ms: "Kurz nachgedacht" (chat.thoughtBriefly)`, () => {
    const { t } = makeT()
    expect(formatThinkingLabel(1_000, t)).toBe('chat.thoughtBriefly')
    expect(formatThinkingLabel(0, t)).toBe('chat.thoughtBriefly')
  })

  it(`ab ${THRESHOLD_MS}ms: thoughtForSeconds mit Duration`, () => {
    const { t } = makeT()
    expect(formatThinkingLabel(4_000, t)).toBe('chat.thoughtForSeconds(4s)')
  })

  it('schwelle exakt: 3000ms zählt als "gedacht"', () => {
    const { t } = makeT()
    expect(formatThinkingLabel(THRESHOLD_MS, t)).toBe('chat.thoughtForSeconds(3s)')
  })

  it('minütige Dauer fließt in den Key ein', () => {
    const { t } = makeT()
    expect(formatThinkingLabel(130_000, t)).toBe('chat.thoughtForSeconds(2m 10s)')
  })
})
