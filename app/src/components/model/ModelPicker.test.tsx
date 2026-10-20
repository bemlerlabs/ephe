/**
 * S2 — the picker as a surface: what it shows, what it lets a keyboard do, and what it
 * refuses to invent.
 *
 * The three things worth holding are all about honesty rather than looks: an unknown
 * prints an em-dash in its own cell, a filter cannot pull an unknown row into its list,
 * and the selection is the user's — the picker never carries a preselected row.
 */
// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, within, cleanup } from '@testing-library/react'

import { ModelPicker } from './ModelPicker'
import { UNKNOWN_CELL, type ModelRow } from './modelPickerTypes'
import { FAVORITES_KEY, RECENTS_KEY } from './modelPickerStore'
import { budgetReport } from './pickerBudget'

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

function row(
  id: string,
  group: string,
  meta: Partial<ModelRow['meta']> = {},
  displayName: string | null = null,
  selectable = true,
): ModelRow {
  return {
    key: `${group}||${id}`,
    id,
    displayName,
    group,
    selectable,
    meta: {
      contextWindow: null,
      priceInPerM: null,
      priceOutPerM: null,
      isFree: null,
      supportsTools: null,
      supportsVision: null,
      ...meta,
    },
  }
}

const ROWS: ModelRow[] = [
  row(
    'openai/gpt-big',
    'openrouter',
    {
      contextWindow: 200000,
      supportsTools: true,
      supportsVision: false,
      isFree: false,
      priceInPerM: 2.5,
      priceOutPerM: 10,
    },
    'GPT Big',
  ),
  row('muse:free', 'ephe', { isFree: true, contextWindow: 8192, priceInPerM: 0, priceOutPerM: 0 }),
  row('quiet-model', 'ephe'),
]

function renderPicker(over: Partial<Parameters<typeof ModelPicker>[0]> = {}) {
  const onChange = vi.fn()
  render(
    <ModelPicker
      rows={ROWS}
      value=""
      onChange={onChange}
      testId="picker"
      label="Choose a model"
      {...over}
    />,
  )
  return { onChange }
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

const open = () => fireEvent.click(screen.getByTestId('picker'))

/** The row itself: the star button inside it shares the test-id prefix. */
function optionRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-model-id]'))
}

describe('ModelPicker', () => {
  it('opens on the trigger and keeps the chosen value out of the list until asked', () => {
    renderPicker()
    expect(screen.queryByTestId('picker-list')).toBeNull()
    open()
    expect(screen.getByTestId('picker-list')).toBeTruthy()
    expect(optionRows()).toHaveLength(3)
  })

  it('shows the display name, the group, the window and the price of a row', () => {
    renderPicker()
    open()
    const gpt = screen.getByTestId('picker-row-openai/gpt-big')
    expect(gpt.textContent).toContain('GPT Big')
    expect(gpt.textContent).toContain('200k')
    expect(gpt.textContent).toContain('modelPicker.perMillion')
    // A stated "no" is printed as a crossed chip, never as a missing chip.
    expect(within(gpt).getByTestId('model-chip-vision').textContent).toContain('¬')
    expect(within(gpt).getByTestId('model-chip-tools').dataset.state).toBe('yes')
  })

  it('leaves the unknown cells empty rather than filling them with a guess', () => {
    renderPicker()
    open()
    const quiet = screen.getByTestId('picker-row-quiet-model')
    expect(quiet.textContent).toContain('quiet-model')
    expect(quiet.querySelectorAll('[data-testid^="model-chip-"]')).toHaveLength(0)
    expect((quiet.textContent ?? '').split(UNKNOWN_CELL).length - 1).toBe(2)
  })

  it('searches, filters and clears again', () => {
    renderPicker()
    open()
    fireEvent.change(screen.getByTestId('picker-search'), { target: { value: 'gpt' } })
    expect(optionRows().map((node) => node.getAttribute('data-testid'))).toEqual([
      'picker-row-openai/gpt-big',
    ])
    fireEvent.click(screen.getByTestId('picker-filter-free'))
    expect(screen.getByTestId('picker-empty')).toBeTruthy()
    fireEvent.click(screen.getByTestId('picker-clear'))
    expect(optionRows()).toHaveLength(3)
  })

  it('keeps an unknown row out of a capability filter', () => {
    renderPicker()
    open()
    fireEvent.click(screen.getByTestId('picker-filter-tools'))
    expect(optionRows().map((node) => node.getAttribute('data-testid'))).toEqual([
      'picker-row-openai/gpt-big',
    ])
  })

  it('sorts free first without losing the unknown between the two answers', () => {
    renderPicker()
    open()
    fireEvent.change(screen.getByTestId('picker-sort'), { target: { value: 'freeFirst' } })
    expect(optionRows().map((node) => node.getAttribute('data-model-id'))).toEqual([
      'muse:free',
      'quiet-model',
      'openai/gpt-big',
    ])
  })

  it('stars a model, persists it, and puts it in the favorites section next time', () => {
    renderPicker()
    open()
    fireEvent.click(screen.getByTestId('picker-row-muse:free-favorite'))
    expect(window.localStorage.getItem(FAVORITES_KEY)).toContain('muse:free')
    fireEvent.keyDown(screen.getByTestId('picker-search'), { key: 'Escape' })
    open()
    expect(screen.getByTestId('picker-section-favorites')).toBeTruthy()
    expect(
      within(screen.getByTestId('picker-section-favorites')).getByTestId('picker-row-muse:free'),
    ).toBeTruthy()
    // its own group no longer repeats it
    expect(
      within(screen.getByTestId('picker-section-group-ephe')).queryByTestId('picker-row-muse:free'),
    ).toBeNull()
  })

  it('picks with the keyboard, reports the choice and remembers it', () => {
    const { onChange } = renderPicker()
    open()
    // The cursor starts on the first row and one step lands on the second: the
    // list order is the keyboard order (ephe before openai, name inside a group).
    fireEvent.keyDown(screen.getByTestId('picker-search'), { key: 'ArrowDown' })
    fireEvent.keyDown(screen.getByTestId('picker-search'), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('quiet-model')
    expect(window.localStorage.getItem(RECENTS_KEY)).toContain('quiet-model')
    expect(screen.queryByTestId('picker-list')).toBeNull()
  })

  it('jumps to the last row with End and selects it with Enter', () => {
    const { onChange } = renderPicker()
    open()
    fireEvent.keyDown(screen.getByTestId('picker-search'), { key: 'End' })
    fireEvent.keyDown(screen.getByTestId('picker-search'), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('openai/gpt-big')
  })

  it('returns the focus to the trigger on Escape', () => {
    renderPicker()
    open()
    const input = screen.getByTestId('picker-search')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByTestId('picker-list')).toBeNull()
    expect(document.activeElement).toBe(screen.getByTestId('picker'))
  })

  it('never lets a row whose endpoint is unconfigured be chosen', () => {
    const { onChange } = renderPicker({
      rows: [...ROWS, row('ghost/model', 'scan', {}, null, false)],
    })
    open()
    const ghost = screen.getByTestId('picker-row-ghost/model')
    expect(ghost.textContent).toContain('ghost/model')
    fireEvent.click(within(ghost).getByTitle(/ghost\/model/))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('says the engine is still being read', () => {
    renderPicker({ loading: true })
    open()
    expect(screen.getByTestId('picker-loading').textContent).toContain('modelPicker.loading')
  })

  it('shows the probe failure on the plate that carries the list', () => {
    renderPicker({ error: 'boom' })
    open()
    expect(screen.getByTestId('picker-error').textContent).toContain('boom')
    expect(optionRows()).toHaveLength(0)
  })

  it('becomes a sheet with its own close control on a phone', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query.includes('767px'),
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }),
    })
    renderPicker()
    open()
    expect(screen.getByTestId('picker-close')).toBeTruthy()
    fireEvent.click(screen.getByTestId('picker-close'))
    expect(screen.queryByTestId('picker-search')).toBeNull()
  })

  it('says what a stated no means for the run', () => {
    // S3: the row already crosses the Tools chip; the sentence is what the surface
    // shows where the model is displayed, so a reader is not left to interpret a ¬.
    renderPicker({ rows: [row('plain-model', 'ephe', { supportsTools: false })] })
    open()
    const line = screen.getByTestId('model-answer-only')
    expect(line.textContent).toBe('modelPicker.answerOnly')
    expect(
      within(screen.getByTestId('picker-row-plain-model')).getByTestId('model-chip-tools').dataset
        .state,
    ).toBe('no')
  })

  it('keeps the sentence off a row the engine said nothing about', () => {
    renderPicker({ rows: [row('unknown-model', 'ephe')] })
    open()
    expect(screen.queryByTestId('model-answer-only')).toBeNull()
  })

  it('opens and filters 320 models inside the budget', () => {
    const many: ModelRow[] = Array.from({ length: 320 }, (_, index) =>
      row(`vendor/model-${index}`, index % 2 ? 'openrouter' : 'ephe', {
        contextWindow: index % 3 === 0 ? 128000 + index : null,
        supportsTools: index % 4 === 0,
      }),
    )
    renderPicker({ rows: many })
    // The calibration control: the same row count built as plain DOM in this
    // run. It explains a slow reading; it never moves the 500 ms ceiling.
    const controlAt = performance.now()
    const controlList = document.createElement('ul')
    for (let index = 0; index < many.length; index += 1) {
      const item = document.createElement('li')
      item.textContent = `vendor/model-${index}`
      controlList.appendChild(item)
    }
    document.body.appendChild(controlList)
    const control = performance.now() - controlAt
    controlList.remove()

    const openedAt = performance.now()
    open()
    expect(optionRows().length).toBeGreaterThan(200)
    const rendered = performance.now() - openedAt
    fireEvent.change(screen.getByTestId('picker-search'), { target: { value: 'model-7' } })
    const total = performance.now() - openedAt
    const report = budgetReport(total, control)
    console.log(
      `model picker budget: control ${control.toFixed(1)} ms, open ${rendered.toFixed(1)} ms, ` +
        `open+filter ${total.toFixed(1)} ms, overhead ${report.overheadMs.toFixed(1)} ms`,
    )
    expect(report.controlMs).toBeGreaterThan(0)
    expect(rendered).toBeLessThan(500)
    expect(
      report.pass,
      `picker ${total.toFixed(1)} ms against a ${control.toFixed(1)} ms control`,
    ).toBe(true)
  })
})
