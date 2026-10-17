// N5 — the Δ switch in the trajectory header: once active, the turn headers show
// the delta row 'ΔIN +1,204 · ΔOUT −31' (the first turn stays empty).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TrajectoryTab } from './tabsA'
import { turnStamp } from './trajectoryParts'
import { useChatStore } from '@/store/chatStore'

function deltaTurns() {
  return [
    {
      sid: 's1',
      model: 'm',
      ts: 1761806357,
      duration_ms: 1000,
      steps: [
        {
          n: 1,
          type: 'tool_call',
          title: 'a',
          ms: 500,
          state: 'ok',
          usage: { in: 100, out: 50, model: 'm' },
        },
      ],
    },
    {
      sid: 's1',
      model: 'm',
      ts: 1761806358,
      duration_ms: 1000,
      steps: [
        {
          n: 1,
          type: 'tool_call',
          title: 'b',
          ms: 500,
          state: 'ok',
          usage: { in: 1304, out: 19, model: 'm' },
        },
      ],
    },
  ]
}

vi.mock('@/lib/api', () => ({
  getTrajectory: vi.fn(async () => ({ turns: deltaTurns() })),
  getSubagent: vi.fn(async () => null),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  listArtifacts: vi.fn(async () => ({ artifacts: [], total: 0 })),
}))

// The language belongs to the test: the delta row is a number, and a number that
// follows whoever runs the suite is not measured, it is inherited.
const sprache = vi.hoisted(() => ({ current: 'en' }))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: sprache.current } }),
}))

describe('Δ-Ansicht (N5)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    // jsdom reports height 0 — the virtualizer needs a measured scroll height
    ;(['offsetHeight', 'clientHeight'] as const).forEach((prop) => {
      Object.defineProperty(HTMLElement.prototype, prop, {
        configurable: true,
        get() {
          return this.classList.contains('overflow-y-auto') ? 600 : 0
        },
      })
    })
  })

  it('Umschalter zeigt Deltas nur am zweiten Turn', async () => {
    render(
      <MemoryRouter>
        <TrajectoryTab />
      </MemoryRouter>,
    )
    await screen.findByTestId('trajectory-summary')
    expect(screen.queryByTestId('trajectory-delta-1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('trajectory-btn-delta'))
    const line = await screen.findByTestId('trajectory-delta-1')
    expect(line.textContent).toBe('ΔIN +1,204 · ΔOUT −31')
    expect(screen.queryByTestId('trajectory-delta-0')).not.toBeInTheDocument()
    // switching it off takes the row away again
    fireEvent.click(screen.getByTestId('trajectory-btn-delta'))
    expect(screen.queryByTestId('trajectory-delta-1')).not.toBeInTheDocument()
  })

  it('counter-check: the same row groups with the point in the German interface', async () => {
    sprache.current = 'de'
    render(
      <MemoryRouter>
        <TrajectoryTab />
      </MemoryRouter>,
    )
    await screen.findByTestId('trajectory-summary')
    fireEvent.click(screen.getByTestId('trajectory-btn-delta'))
    const line = await screen.findByTestId('trajectory-delta-1')
    expect(line.textContent).toBe('ΔIN +1.204 · ΔOUT −31')
    sprache.current = 'en'
  })
})

// The turn tooltip is the other number-shaped string in this area: one instant,
// two readings. Measured against Intl before written.
describe('turnStamp — the same instant per language', () => {
  it('english writes the month name and AM, german the dotted date', () => {
    // The rendered stamp follows the runner's timezone, so this asserts the format only.
    const expected = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'medium' }).format(
      new Date(1761806357 * 1000),
    )
    expect(turnStamp(1761806357, 'en')).toBe(expected)
    const expectedDe = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'medium' }).format(
      new Date(1761806357 * 1000),
    )
    expect(turnStamp(1761806357, 'de')).toBe(expectedDe)
    expect(turnStamp(null, 'de')).toBeUndefined()
  })
})
