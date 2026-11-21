/**
 * The goal run on the status panel — its own file because
 * AgentStatusSections.test.tsx carries the six sections already and this is the
 * one that changed: the goal the loop works toward (core/goal_loop.py, `/goal`)
 * instead of a guess at the session's first line.
 *
 * jsdom cannot measure layout — pinned are text, data-* attributes and classes.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, renderHook, screen } from '@testing-library/react'

import { GoalSection, useStatusPanelData } from './AgentStatusSections'
import type { ChatMessage, GoalRunState } from '@/types'

// The two wording keys this surface reads; the run's numbers need none.
const DE: Record<string, string> = {
  'agentStatus.goalSection': 'Ziel',
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'de' },
    t: (key: string) => DE[key] ?? key,
  }),
}))

// duration.ts statically imports getSettings through deepSettings.
const api = vi.hoisted(() => ({
  getUsageSummary: vi.fn(),
  getSettings: vi.fn(async () => ({ workspace_dir: '/ws' })),
}))
vi.mock('@/lib/api', () => api)

let seq = 0
const msg = (over: Partial<ChatMessage> = {}): ChatMessage => ({
  id: `m${++seq}`,
  role: 'assistant',
  content: '',
  timestamp: Date.now(),
  ...over,
})

const run: GoalRunState = {
  goal: 'Fix the login bug',
  check: 'npm test',
  maxTurns: 4,
  turn: 2,
  ok: false,
}

describe('useStatusPanelData — the goal run', () => {
  it('shows the goal the loop works toward, not the session’s opening query', () => {
    const user = msg({ role: 'user', content: 'Why is the app slow?\n(and something else)' })
    const turn = msg({ goal: { ...run, goal: 'Make the failing test pass' } })
    const { result } = renderHook(() => useStatusPanelData([user, turn]))
    expect(result.current.goal).toBe('Make the failing test pass')
    expect(result.current.goalRun?.check).toBe('npm test')
  })

  it('keeps the opening query as the fallback where no run recorded a goal', () => {
    const user = msg({ role: 'user', content: '  Fix the login bug  \nwith detail' })
    const { result } = renderHook(() => useStatusPanelData([user, msg({ content: 'ok' })]))
    expect(result.current.goalRun).toBeNull()
    expect(result.current.goal).toBe('Fix the login bug')
  })

  it('takes the newest goal run when a session carries more than one', () => {
    const older = msg({ goal: { ...run, goal: 'first goal' } })
    const newer = msg({ goal: { ...run, goal: 'second goal' } })
    const { result } = renderHook(() => useStatusPanelData([older, newer]))
    expect(result.current.goal).toBe('second goal')
  })

  it('a goal start with blank text is no goal, and the query stands in', () => {
    const user = msg({ role: 'user', content: 'Real question' })
    const turn = msg({ goal: { ...run, goal: '   ' } })
    const { result } = renderHook(() => useStatusPanelData([user, turn]))
    expect(result.current.goal).toBe('Real question')
  })
})

describe('GoalSection — the run line', () => {
  it('shows the check command, the round and the round’s verdict', () => {
    render(<GoalSection goal="Fix the login bug" run={run} />)
    expect(screen.getByTestId('agent-status-goal-text').textContent?.trim()).toBe(
      'Fix the login bug',
    )
    const line = screen.getByTestId('agent-status-goal-check')
    expect(line.dataset.status).toBe('failed')
    expect(line.textContent).toContain('npm test')
    expect(line.querySelector('svg')?.classList.contains('lucide-circle-alert')).toBe(true)
    expect(screen.getByTestId('agent-status-goal-turn').textContent).toBe('2/4')
  })

  it('a round whose check has not answered yet reads as running', () => {
    render(<GoalSection goal="Fix the login bug" run={{ ...run, turn: 1, ok: null }} />)
    const line = screen.getByTestId('agent-status-goal-check')
    expect(line.dataset.status).toBe('running')
    expect(line.querySelector('svg')?.classList.contains('lucide-loader-circle')).toBe(true)
  })

  it('a passed round is a check mark', () => {
    render(<GoalSection goal="Fix the login bug" run={{ ...run, ok: true }} />)
    const line = screen.getByTestId('agent-status-goal-check')
    expect(line.dataset.status).toBe('passed')
    expect(line.querySelector('svg')?.classList.contains('lucide-check')).toBe(true)
  })

  it('without a run there is no check line and no round counter', () => {
    render(<GoalSection goal="Fix the login bug" />)
    expect(screen.queryByTestId('agent-status-goal-check')).toBeNull()
    expect(screen.queryByTestId('agent-status-goal-turn')).toBeNull()
  })
})
