/**
 * The agentic workbench chrome: the command/state bar and the run rail.
 *
 * The bar states what the run is doing from signals the session already carries —
 * there is no state of its own to invent — and the rail marks the plan the newest
 * turn already wrote. Both are held here against that contract, and against the
 * classes the sheet binds the state motion to.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AgenticBar, { runStateOf } from './AgenticBar'
import RunRail from './RunRail'
import type { PlanCardSpec } from '@/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const PLAN: PlanCardSpec = {
  items: [
    { status: 'done', text: 'Read the repo' },
    { status: 'active', text: 'Run the tests' },
    { status: 'pending', text: 'Write the report' },
  ],
  done: 1,
  total: 3,
}

describe('runStateOf — the state, read off the session', () => {
  const base = { typing: false }

  it('a streaming turn is working', () => {
    expect(runStateOf({ ...base, typing: true })).toBe('working')
  })

  it('a dead engine or an open ask outranks streaming', () => {
    expect(runStateOf({ typing: true, engineOnline: false })).toBe('waiting')
    expect(runStateOf({ typing: true, askWaiting: true })).toBe('waiting')
  })

  it('a finished plan is done, a fresh session is ready', () => {
    const done: PlanCardSpec = { items: PLAN.items, done: 3, total: 3 }
    expect(runStateOf({ ...base, plan: done })).toBe('done')
    expect(runStateOf({ ...base, plan: PLAN })).toBe('ready')
    expect(runStateOf(base)).toBe('ready')
  })
})

describe('AgenticBar — one chrome line states the run', () => {
  const render_bar = (props: Partial<Parameters<typeof AgenticBar>[0]> = {}) => {
    const onOpenPalette = vi.fn()
    render(
      <AgenticBar
        state="working"
        plan={PLAN}
        goal="Ship the wave"
        onOpenPalette={onOpenPalette}
        {...props}
      />,
    )
    return onOpenPalette
  }

  it('carries the state on the bar and on its one mark', () => {
    render_bar()
    const bar = screen.getByTestId('agentic-bar')
    expect(bar.getAttribute('data-state')).toBe('working')
    // The bar wears both chrome classes; the sheet addresses the mark through its state.
    expect(bar.className).toContain('workbench-bar')
    expect(bar.className).toContain('ephe-run')
    expect(bar.querySelector('.ephe-run-mark')).toBeTruthy()
  })

  it('states the plan ratio and grows the accent rule to it', () => {
    render_bar()
    expect(screen.getByTestId('workbench-plan').textContent).toBe('workbench.steps')
    const rule = screen.getByTestId('workbench-progress')
    expect(rule.className).toContain('ephe-run-progress')
    expect(rule.getAttribute('style')).toContain('scaleX(0.3333333333333333)')
  })

  it('keeps the command affordance wired to the palette', () => {
    const onOpenPalette = render_bar()
    fireEvent.click(screen.getByTestId('workbench-command'))
    expect(onOpenPalette).toHaveBeenCalledTimes(1)
  })

  it('shows no ratio and no rule without a plan', () => {
    render_bar({ plan: null })
    expect(screen.queryByTestId('workbench-plan')).toBeNull()
    expect(screen.queryByTestId('workbench-progress')).toBeNull()
  })
})

describe('RunRail — the run down the edge of the work column', () => {
  it('renders nothing without a plan', () => {
    const { container } = render(<RunRail plan={null} />)
    expect(container.querySelector('[data-testid="run-rail"]')).toBeNull()
  })

  it('marks every step with the status the plan gave it', () => {
    render(<RunRail plan={PLAN} />)
    const rail = screen.getByTestId('run-rail')
    expect(rail.className).toContain('hidden')
    expect(rail.className).toContain('lg:flex')
    expect(rail.getAttribute('aria-label')).toBe('workbench.runProgress')
    expect(
      [...rail.querySelectorAll('.ephe-rail-mark')].map((m) => m.getAttribute('data-step')),
    ).toEqual(['done', 'active', 'pending'])
  })
})
