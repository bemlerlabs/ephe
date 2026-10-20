/**
 * The picker's wall-clock ceiling, measured alone.
 *
 * `vite.config.ts` excludes the parallel suite from this path; `vitest.perf.config.ts`
 * selects it and runs one worker with no file or test parallelism. On 2026-10-20 the
 * same open+filter read 553.7 ms in Frontend Build and 811.2 ms in Verify while the
 * component was unchanged; the control below read hundreds of milliseconds in those
 * runs. A number read under that load is no verdict about the picker, so the lane warms
 * up, takes a median, and reports host overload as overload before the ceiling.
 */
// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'

import { ModelPicker } from './ModelPicker'
import type { ModelRow } from './modelPickerTypes'
import { CONTROL_LOAD_MS, PICKER_BUDGET_MS, budgetReport, median } from './pickerBudget'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const ROWS: ModelRow[] = Array.from({ length: 320 }, (_, index) => ({
  key: `${index % 2 ? 'openrouter' : 'ephe'}||vendor/model-${index}`,
  id: `vendor/model-${index}`,
  displayName: null,
  group: index % 2 ? 'openrouter' : 'ephe',
  selectable: true,
  meta: {
    contextWindow: index % 3 === 0 ? 128000 + index : null,
    priceInPerM: null,
    priceOutPerM: null,
    isFree: null,
    supportsTools: index % 4 === 0,
    supportsVision: null,
  },
}))

/** One open+filter cycle on a fresh picker, in milliseconds. */
function sample(): number {
  render(
    <ModelPicker rows={ROWS} value="" onChange={vi.fn()} testId="picker" label="Choose a model" />,
  )
  const startedAt = performance.now()
  fireEvent.click(screen.getByTestId('picker'))
  expect(document.querySelectorAll('[data-model-id]')).toHaveLength(320)
  fireEvent.change(screen.getByTestId('picker-search'), { target: { value: 'model-7' } })
  const elapsed = performance.now() - startedAt
  cleanup()
  return elapsed
}

/** The load control: the same row count as plain DOM, no React. */
function controlSample(): number {
  const startedAt = performance.now()
  const list = document.createElement('ul')
  for (let index = 0; index < ROWS.length; index += 1) {
    const item = document.createElement('li')
    item.textContent = `vendor/model-${index}`
    list.appendChild(item)
  }
  document.body.appendChild(list)
  const elapsed = performance.now() - startedAt
  list.remove()
  return elapsed
}

afterEach(cleanup)

beforeEach(() => {
  window.localStorage.clear()
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  })
})

describe('ModelPicker perf lane', () => {
  it('opens and filters 320 models inside the 500 ms ceiling', () => {
    // Warm-up: the first render pays the JSX transform and jsdom's first layout pass.
    sample()
    sample()

    const control = median([controlSample(), controlSample(), controlSample()])
    const samples = [sample(), sample(), sample(), sample(), sample()]
    const rendered = median(samples)
    const report = budgetReport(rendered, control)
    console.log(
      `model picker perf: control ${control.toFixed(1)} ms, median ${rendered.toFixed(1)} ms, ` +
        `samples [${samples.map((value) => value.toFixed(1)).join(', ')}] ms, ` +
        `ceiling ${PICKER_BUDGET_MS} ms`,
    )

    if (report.overloaded) {
      throw new Error(
        `perf lane host overloaded: the plain 320-row control read ${control.toFixed(1)} ms ` +
          `(limit ${CONTROL_LOAD_MS} ms), so no wall-clock verdict is possible; re-run on an ` +
          `idle runner. Picker samples: [${samples.map((value) => value.toFixed(1)).join(', ')}] ms`,
      )
    }

    expect(report.controlMs).toBeGreaterThan(0)
    expect(
      report.pass,
      `picker median ${rendered.toFixed(1)} ms against a ${control.toFixed(1)} ms control`,
    ).toBe(true)
  })
})
