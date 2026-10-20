/**
 * The model picker's budget report. The ceiling stays 500 ms; the control
 * render of the same row count is measured in the same run so a failure can
 * say whether the host was loaded or the picker itself regressed. A control
 * that is slow never widens the ceiling — it only explains the reading.
 */
export const PICKER_BUDGET_MS = 500

export interface BudgetReport {
  renderedMs: number
  controlMs: number
  overheadMs: number
  ratio: number | null
  pass: boolean
}

export function budgetReport(renderedMs: number, controlMs: number): BudgetReport {
  return {
    renderedMs,
    controlMs,
    overheadMs: renderedMs - controlMs,
    ratio: controlMs > 0 ? renderedMs / controlMs : null,
    pass: renderedMs < PICKER_BUDGET_MS,
  }
}
