/**
 * F7 — a replay card shows its own run.
 *
 * `GET /api/trajectory` answers newest-first while the card looked its turn up
 * by the assistant message's position, which counts oldest-first: with two
 * runs in the session the first card showed the newest run's steps and summed
 * their durations. The chain id decides now; the position remains only as the
 * fallback for messages that predate it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      opts ? `${k} ${JSON.stringify(opts)}` : k,
  }),
}))

const getTrajectory = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ getTrajectory }))

import { ToolReplayKader } from './ToolReplayKader'
import { useChatStore } from '@/store/chatStore'

const step = (text: string, ms: number) => ({ n: 1, type: 'tool', text, ms, state: 'done' })

const turns = [
  { sid: 's', turn_id: 't-new', model: 'm', ts: 2, duration_ms: null, steps: [step('new-step', 200)] },
  { sid: 's', turn_id: 't-old', model: 'm', ts: 1, duration_ms: null, steps: [step('old-step', 100)] },
]

const messages = [
  { id: 'u1', role: 'user', content: 'first', timestamp: 1 },
  { id: 'a1', role: 'assistant', content: 'one', timestamp: 2, turnId: 't-old' },
  { id: 'u2', role: 'user', content: 'second', timestamp: 3 },
  { id: 'a2', role: 'assistant', content: 'two', timestamp: 4, turnId: 't-new' },
] as never

beforeEach(() => {
  getTrajectory.mockReset()
  getTrajectory.mockResolvedValue({ turns })
  useChatStore.setState({
    activeSessionId: 's',
    currentSession: { id: 's', messages },
  } as never)
})

const card = (id: string) =>
  render(<ToolReplayKader message={(messages as unknown as { id: string }[]).find((m) => m.id === id) as never} />)

describe('ToolReplayKader turn scoping', () => {
  it('shows the steps and the duration of the message’s own turn', async () => {
    card('a2')
    await waitFor(() => expect(screen.getByTestId('tool-replay-kader-1')).toBeTruthy())
    const header = screen.getByTestId('tool-replay-kader-1')
    expect(header.textContent).toContain('200')
    expect(header.textContent).not.toContain('300')
  })

  it('picks the older turn for the older message', async () => {
    card('a1')
    await waitFor(() => expect(screen.getByTestId('tool-replay-kader-0')).toBeTruthy())
    expect(screen.getByTestId('tool-replay-kader-0').textContent).toContain('100')
  })

  it('falls back to chronological position for a message without a chain id', async () => {
    const legacy = [
      { id: 'a1', role: 'assistant', content: 'one', timestamp: 2 },
      { id: 'a2', role: 'assistant', content: 'two', timestamp: 4 },
    ] as never
    useChatStore.setState({
      activeSessionId: 's',
      currentSession: { id: 's', messages: legacy },
    } as never)
    const { container } = render(
      <ToolReplayKader message={(legacy as unknown as { id: string }[])[0] as never} />,
    )
    await waitFor(() => expect(container.querySelector('[data-testid="tool-replay-kader-0"]')).toBeTruthy())
    expect(container.textContent).toContain('100')
  })
})
