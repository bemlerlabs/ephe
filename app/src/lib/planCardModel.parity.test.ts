import { describe, it, expect } from 'vitest'
import block from '../../fixtures/plan/rendered-block.txt?raw'
import { parsePlanCard } from './planCardModel'

/**
 * The emitter and this parser are two languages over one contract. The fixture is
 * core/ephe_plan.py's own output, written by `tests/test_plan_surface_contract.py`, which
 * refuses a fixture that no longer matches what render() produces. A shape change that only
 * reaches one side of the pair fails here.
 */
const rendered = block.trimEnd()

describe('plan block parity with core/ephe_plan.py', () => {
  it('reads the rendered block as four steps, one done', () => {
    const spec = parsePlanCard(rendered)
    expect(spec).not.toBeNull()
    expect(spec!.total).toBe(4)
    expect(spec!.done).toBe(1)
    expect(spec!.items.map((i) => i.status)).toEqual(['done', 'active', 'pending', 'pending'])
    expect(spec!.items[0]!.text).toBe('Read the three route files the request names')
  })
})
