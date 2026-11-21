// N5 (C3) — Δ view: diffTurns as a frontend derivation (backend unchanged)
// + fmtSigned in the format core (positive sign explicit, minus U+2212).
import { describe, expect, it } from 'vitest'
import { diffTurns } from './trajectory'
import { fmtSigned } from '../format'
import type { TrajTurn } from './trajectory'

function turn(inTok: number, outTok: number): TrajTurn {
  return {
    sid: 's1',
    model: 'm',
    ts: 1761806357,
    duration_ms: 1000,
    steps: [
      {
        n: 1,
        type: 'tool_call',
        title: 't',
        ms: 500,
        state: 'ok',
        usage: { in: inTok, out: outTok, model: 'm' },
      },
    ],
  }
}

describe('fmtSigned', () => {
  it('positive with +, negative with a typographic minus, thousands point', () => {
    expect(fmtSigned(1204, 'en')).toBe('+1,204')
    expect(fmtSigned(-31)).toBe('−31')
    expect(fmtSigned(0)).toBe('0')
  })
})

describe('diffTurns (N5)', () => {
  it('returns the deltas between consecutive turns', () => {
    const out = diffTurns([turn(100, 50), turn(1304, 19)])
    expect(out[0]).toEqual({ index: 0, din: null, dout: null })
    expect(out[1]).toEqual({ index: 1, din: 1204, dout: -31 })
  })

  it('empty input, single turns and missing usage give null deltas', () => {
    expect(diffTurns([])).toEqual([])
    const one = diffTurns([turn(100, 50)])
    expect(one[0]?.din).toBeNull()
    const noUsage: TrajTurn = { sid: 's', model: 'm', ts: null, duration_ms: null, steps: [] }
    expect(diffTurns([noUsage, noUsage]).map((d) => d.din)).toEqual([null, null])
  })
})
