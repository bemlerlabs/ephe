import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'

const { state, approveSandbox } = vi.hoisted(() => ({
  state: { currentSession: null as unknown },
  approveSandbox: vi.fn(async () => ({ status: 'ok' })),
}))
vi.mock('@/store/chatStore', () => ({
  useChatStore: Object.assign(
    (selector: (s: unknown) => unknown) => selector(state),
    { getState: () => ({ approveSandbox: vi.fn(), markAskAnswered: vi.fn(), compactSession: vi.fn() }) },
  ),
}))
vi.mock('@/lib/api/endpoints', () => ({
  approveSandbox,
  answerAsk: vi.fn(async () => ({ status: 'ok' })),
}))

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => true }
})

import HeaderCompanion from './HeaderCompanion'
import WorkspaceCompanion from './WorkspaceCompanion'

function seed(entries: Record<string, string | number | boolean>) {
  seedDeepSettings([
    {
      fields: Object.entries(entries).map(([key, value]) => ({ key, value, default: value })),
    },
  ] as unknown as DeepSection[])
}

/** A session with one waiting shell check the co-pilot would classify as safe. */
function waitingSession(): unknown {
  return {
    id: 's1',
    title: 't',
    createdAt: 1,
    updatedAt: 1,
    messages: [
      {
        id: 'm1',
        role: 'assistant',
        content: '',
        timestamp: 1,
        tool_calls: [
          {
            id: 't1',
            name: 'run_shell',
            args: { command: 'pytest' },
            status: 'waiting',
            description: 'tok-1',
          },
        ],
      },
    ],
  }
}

beforeEach(() => {
  approveSandbox.mockClear()
  state.currentSession = null
})

afterEach(() => seedDeepSettings(null))

describe('HeaderCompanion', () => {
  it('reserves the slot and renders the actor at the perch', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    render(<HeaderCompanion runState="ready" hasMessages />)
    expect(screen.getByTestId('header-companion-slot')).toBeTruthy()
    const companion = screen.getByTestId('header-companion')
    expect(companion.dataset.state).toBe('ready')
    expect(companion.dataset.mood).toBe('rest')
    expect(companion.querySelector('.companion-actor')).toBeTruthy()
  })

  it('keeps the slot before the first message without a second actor', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    render(<HeaderCompanion runState="ready" hasMessages={false} />)
    expect(screen.getByTestId('header-companion-slot')).toBeTruthy()
    expect(screen.queryByTestId('header-companion')).toBeNull()
  })

  it('renders nothing when the behavior is not the header perch', () => {
    render(<HeaderCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('header-companion-slot')).toBeNull()
  })

  it('maps the one run state to the actor mood', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    const { rerender } = render(<HeaderCompanion runState="working" hasMessages />)
    expect(screen.getByTestId('header-companion').dataset.mood).toBe('moving')
    rerender(<HeaderCompanion runState="waiting" hasMessages />)
    expect(screen.getByTestId('header-companion').dataset.mood).toBe('still')
    rerender(<HeaderCompanion runState="done" hasMessages />)
    expect(screen.getByTestId('header-companion').dataset.mood).toBe('settle')
  })

  it('carries the co-pilot into the perch popover', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    state.currentSession = waitingSession()
    render(<HeaderCompanion runState="ready" hasMessages />)
    fireEvent.click(screen.getByTestId('companion-trigger'))
    expect(screen.getByTestId('companion-mode-row')).toBeTruthy()
    expect(screen.getByTestId('companion-copilot-row')).toBeTruthy()
    // The act button is the cancel one only while a countdown is actually running.
    expect(screen.getByTestId('companion-popover-copilot-act')).toBeTruthy()
  })

  it('the perch the behavior chose runs the loop once, whatever else is mounted', async () => {
    vi.useFakeTimers()
    try {
      seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
      state.currentSession = waitingSession()
      render(
        <>
          <HeaderCompanion runState="ready" hasMessages />
          <WorkspaceCompanion runState="ready" hasMessages />
        </>,
      )
      await vi.advanceTimersByTimeAsync(2500)
      expect(approveSandbox).toHaveBeenCalledTimes(1)
      expect(approveSandbox).toHaveBeenCalledWith('tok-1', true, false)
    } finally {
      vi.useRealTimers()
    }
  })
})
