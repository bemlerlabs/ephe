// N3′ — keyboard navigation of the trajectory timeline: ArrowUp/Down move the
// active step, Home/End jump to start/end, Enter/Space opens the step details,
// Esc deselects. scrollIntoView keeps the active row visible.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TrajectoryTab } from './tabsA'
import { useChatStore } from '@/store/chatStore'

function fixtureTurns() {
  const step = (n: number, usage?: { in: number; out: number }) => ({
    n,
    type: usage ? 'tool_call' : 'message',
    title: `cmd ${n}`,
    ms: 520 + n,
    state: 'ok',
    ...(usage ? { usage: { ...usage, model: 'qwen3.8-flash-next' } } : {}),
  })
  const turn = (offset: number, usage: { in: number; out: number }) => ({
    sid: 's1',
    model: 'qwen3.8-flash-next',
    ts: 1761806357,
    duration_ms: 3520,
    steps: Array.from({ length: 7 }, (_, i) =>
      step(usage && i === 0 ? offset + i + 1 : offset + i + 1, i === 0 ? usage : undefined),
    ),
  })
  return [turn(0, { in: 144794, out: 115 }), turn(7, { in: 8021000, out: 119797 })]
}

vi.mock('@/lib/api', () => ({
  getTrajectory: vi.fn(async () => ({ turns: fixtureTurns() })),
  getSubagent: vi.fn(async () => null),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  listArtifacts: vi.fn(async () => ({ artifacts: [], total: 0 })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const patchHeight = (prop: 'offsetHeight' | 'clientHeight') => {
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    get() {
      return this.classList.contains('overflow-y-auto') ? 600 : 0
    },
  })
}

describe('TrajectoryTab Tastatur-Navigation (N3′)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    patchHeight('offsetHeight')
    patchHeight('clientHeight')
    Element.prototype.scrollIntoView = vi.fn()
  })

  const list = () => document.querySelector('[data-testid="trajectory-list"]') as HTMLElement

  it('ArrowDown waehlt Steps sequentiell (turnuebergreifend), Home/End springen', async () => {
    render(
      <MemoryRouter>
        <TrajectoryTab />
      </MemoryRouter>,
    )
    await screen.findByTestId('trajectory-summary')
    const el = list()
    fireEvent.keyDown(el, { key: 'ArrowDown' })
    expect(document.querySelector('[data-active-step]')?.getAttribute('data-trajectory-step')).toBe(
      '0-1',
    )
    fireEvent.keyDown(el, { key: 'ArrowDown' })
    expect(document.querySelector('[data-active-step]')?.getAttribute('data-trajectory-step')).toBe(
      '0-2',
    )
    fireEvent.keyDown(el, { key: 'End' })
    expect(document.querySelector('[data-active-step]')?.getAttribute('data-trajectory-step')).toBe(
      '1-14',
    )
    fireEvent.keyDown(el, { key: 'ArrowDown' }) // at the end: stays put
    expect(document.querySelector('[data-active-step]')?.getAttribute('data-trajectory-step')).toBe(
      '1-14',
    )
    fireEvent.keyDown(el, { key: 'Home' })
    expect(document.querySelector('[data-active-step]')?.getAttribute('data-trajectory-step')).toBe(
      '0-1',
    )
    fireEvent.keyDown(el, { key: 'ArrowUp' }) // at the start: stays put
    expect(document.querySelector('[data-active-step]')?.getAttribute('data-trajectory-step')).toBe(
      '0-1',
    )
  })

  it('aktive Zeile bleibt per scrollIntoView sichtbar', async () => {
    render(
      <MemoryRouter>
        <TrajectoryTab />
      </MemoryRouter>,
    )
    await screen.findByTestId('trajectory-summary')
    fireEvent.keyDown(list(), { key: 'ArrowDown' })
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled())
  })

  it('Enter oeffnet die Sektionen des aktiven Steps; Esc entwaehlt', async () => {
    render(
      <MemoryRouter>
        <TrajectoryTab />
      </MemoryRouter>,
    )
    await screen.findByTestId('trajectory-summary')
    const el = list()
    fireEvent.keyDown(el, { key: 'ArrowDown' }) // 0-1 aktiv
    expect(screen.queryByTestId('trajectory-section-0-1-in')).not.toBeInTheDocument()
    fireEvent.keyDown(el, { key: 'Enter' })
    expect(screen.getByTestId('trajectory-section-0-1-in')).toBeInTheDocument()
    fireEvent.keyDown(el, { key: 'Escape' })
    expect(document.querySelector('[data-active-step]')).toBeNull()
    // opened details survive Esc (only the selection is dropped)
    expect(screen.getByTestId('trajectory-section-0-1-in')).toBeInTheDocument()
  })
})
