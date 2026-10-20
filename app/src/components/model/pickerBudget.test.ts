import { describe, expect, it } from 'vitest'

import { CONTROL_LOAD_MS, PICKER_BUDGET_MS, budgetReport, median } from './pickerBudget'

describe('model picker budget report', () => {
  it('keeps the 500 ms ceiling and names the overhead over the control', () => {
    const report = budgetReport(120, 30)
    expect(report.pass).toBe(true)
    expect(report.overloaded).toBe(false)
    expect(report.overheadMs).toBe(90)
    expect(report.ratio).toBe(4)
  })

  it('a loaded host explains a slow reading but does not move the ceiling', () => {
    const report = budgetReport(640, 300)
    expect(report.pass).toBe(false)
    expect(report.overloaded).toBe(true)
    expect(PICKER_BUDGET_MS).toBe(500)
    expect(report.ratio).toBeCloseTo(2.13, 2)
  })

  it('marks an overloaded host even when the picker reading is under the ceiling', () => {
    const report = budgetReport(120, CONTROL_LOAD_MS + 1)
    expect(report.pass).toBe(true)
    expect(report.overloaded).toBe(true)
  })

  it('a missing control leaves the ratio unknown rather than dividing by zero', () => {
    expect(budgetReport(100, 0).ratio).toBeNull()
  })
})

describe('median', () => {
  it('returns the middle of an odd sample set', () => {
    expect(median([700, 100, 400, 300, 200])).toBe(300)
  })

  it('averages the two middles of an even sample set', () => {
    expect(median([4, 1, 3, 2])).toBe(2.5)
  })

  it('refuses an empty sample set instead of returning a number nobody measured', () => {
    expect(() => median([])).toThrow(/at least one sample/)
  })
})
