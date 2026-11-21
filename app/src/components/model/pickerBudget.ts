/**
 * The model picker's budget report. The ceiling stays 500 ms; the control
 * render of the same row count is measured in the same run so a failure can
 * say whether the host was loaded or the picker itself regressed.
 *
 * The lane that reads this is serial (`vitest.perf.config.ts`). In the parallel
 * suite the same control read 606 ms on a fully loaded runner while the picker
 * was unchanged, so there it measured the host and not the component.
 */
export const PICKER_BUDGET_MS = 500

/**
 * A plain 320-row DOM build is the load control. It reads about 2 ms on an idle
 * machine; a hundredfold reading means this host cannot support a wall-clock
 * verdict at all, and the lane must say that instead of blaming the picker.
 */
export const CONTROL_LOAD_MS = 100

export interface BudgetReport {
  renderedMs: number
  controlMs: number
  overheadMs: number
  ratio: number | null
  pass: boolean
  overloaded: boolean
}

export function median(samples: number[]): number {
  if (samples.length === 0) {
    throw new Error('median needs at least one sample')
  }
  const sorted = [...samples].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  const upper = sorted[middle]
  const lower = sorted.length % 2 === 1 ? upper : sorted[middle - 1]
  if (upper === undefined || lower === undefined) {
    throw new Error('median sample set became empty')
  }
  return (lower + upper) / 2
}

export function budgetReport(renderedMs: number, controlMs: number): BudgetReport {
  return {
    renderedMs,
    controlMs,
    overheadMs: renderedMs - controlMs,
    ratio: controlMs > 0 ? renderedMs / controlMs : null,
    pass: renderedMs < PICKER_BUDGET_MS,
    overloaded: controlMs > CONTROL_LOAD_MS,
  }
}
