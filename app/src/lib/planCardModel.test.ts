import { describe, it, expect } from 'vitest'
import {
  PLAN_EXECUTION_MODE,
  parsePlanCard,
  planAcceptTurn,
  renderPlanBlock,
} from './planCardModel'

describe('parsePlanCard — the one plan shape', () => {
  it('parses the block core/ephe_plan.py renders', () => {
    const text = [
      '## Plan · 1/3',
      '- [x] Read the manifest',
      '- [>] Run the test suite',
      '- [ ] Summarize results',
    ].join('\n')
    const spec = parsePlanCard(text)
    expect(spec).not.toBeNull()
    expect(spec!.done).toBe(1)
    expect(spec!.total).toBe(3)
    expect(spec!.items.map((i) => i.status)).toEqual(['done', 'active', 'pending'])
  })

  it('accepts the heading without a count, which is what a model writes', () => {
    const spec = parsePlanCard('## Plan\n- [ ] One\n- [ ] Two')
    expect(spec!.total).toBe(2)
    expect(spec!.done).toBe(0)
  })

  it('keeps the card alive on a half-written step line', () => {
    const spec = parsePlanCard('## Plan\n- [ ] Read the three route fil')
    expect(spec).not.toBeNull()
    expect(spec!.items[0]!.text).toBe('Read the three route fil')
  })

  it('takes the counts from the marks when the heading digits disagree', () => {
    const spec = parsePlanCard('## Plan · 9/9\n- [x] A\n- [ ] B')
    expect(spec!.done).toBe(1)
    expect(spec!.total).toBe(2)
  })

  it('strips the ledger id so a row is not numbered twice', () => {
    const spec = parsePlanCard('## Plan · 1/2\n- [x] 1. Read routes\n- [>] 2. Add the case')
    expect(spec!.items.map((i) => i.text)).toEqual(['Read routes', 'Add the case'])
  })

  it('carries the two terminal marks', () => {
    const spec = parsePlanCard('## Plan\n- [!] Explode\n- [-] Skipped\n- [ ] Next')
    expect(spec!.items.map((i) => i.status)).toEqual(['failed', 'cancelled', 'pending'])
  })

  it('reads the legacy bold header the old emitter wrote', () => {
    const spec = parsePlanCard('**Plan · 1/3**\n[x] a\n[>] b\n[ ] c')
    expect(spec!.total).toBe(3)
  })

  it('returns null for prose and for a single stray box without a heading', () => {
    expect(parsePlanCard('Plain prose with no list.')).to.eq(null)
    expect(parsePlanCard('')).to.eq(null)
    expect(parsePlanCard('- [ ] only one line')).to.eq(null)
  })
})

describe('the accept contract — what the gate hands to the engine', () => {
  it('names a mode that can write, because plan mode cannot by contract', () => {
    // server/routes/chat.py::_mode_context keeps `plan` on _READ_ONLY_TOOL_NAMES, so the
    // mode a plan's execution needs is the write family's — never the mode it came from.
    expect(PLAN_EXECUTION_MODE).toBe('edit-auto')
    expect(PLAN_EXECUTION_MODE).not.toBe('plan')
  })

  it('carries the accepted steps, so the turn does not have to guess them', () => {
    const titles = ['Read the route', 'Add the case', 'Run the suite']
    const turn = planAcceptTurn('Plan accepted.', titles)
    expect(turn).toBe(`Plan accepted.\n\n${renderPlanBlock(titles)}`)
    // Round-trip: what the gate sends parses back into the card the user confirmed.
    const back = parsePlanCard(turn)
    expect(back!.items.map((i) => i.text)).toEqual(titles)
  })
})

describe('parsePlanCard survives a re-printed and flattened plan (F5)', () => {
  it('counts a step once when the answer printed its plan twice', () => {
    const text = [
      '## Plan',
      '- [x] Inspect the workspace',
      '- [x] Verify the file exists',
      '- [>] Write the note',
      '- [ ] Report back',
      '',
      'Halfway through. Here is the plan again:',
      '- [x] Inspect the workspace',
      '- [x] Verify the file exists',
      '- [x] Write the note',
      '- [ ] Report back',
    ].join('\n')
    const spec = parsePlanCard(text)!
    expect(spec.total).toBe(4)
    expect(spec.done).toBe(3)
    expect(spec.items.map((i) => i.status)).toEqual(['done', 'done', 'done', 'pending'])
  })

  it('splits a checklist the writer flattened onto one line', () => {
    const text = '## Plan\n- [x] first step - [x] second step - [ ] third step'
    const spec = parsePlanCard(text)!
    expect(spec.items.map((i) => i.text)).toEqual(['first step', 'second step', 'third step'])
    expect(spec.total).toBe(3)
  })
})
