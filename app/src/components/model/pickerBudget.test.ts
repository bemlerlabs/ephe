import { describe, expect, it } from 'vitest'

import { PICKER_BUDGET_MS, budgetReport } from './pickerBudget'

describe('model picker budget report', () => {
  it('keeps the 500 ms ceiling and names the overhead over the control', () => {
    const report = budgetReport(120, 30)
    expect(report.pass).toBe(true)
    expect(report.overheadMs).toBe(90)
    expect(report.ratio).toBe(4)
  })

  it('a loaded host explains a slow reading but does not move the ceiling', () => {
    const report = budgetReport(640, 300)
    expect(report.pass).toBe(false)
    expect(PICKER_BUDGET_MS).toBe(500)
    expect(report.ratio).toBeCloseTo(2.13, 2)
  })

  it('a missing control leaves the ratio unknown rather than dividing by zero', () => {
    expect(budgetReport(100, 0).ratio).toBeNull()
  })
})
