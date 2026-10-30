// PAKET X1 — the finished turn keeps ONE line: diff counts, Undo and a Replay
// link that opens the trajectory tab of the right-side panel. The steps
// themselves no longer render inside the bubble.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MessageBubble from './MessageBubble'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

vi.mock('@/lib/api', () => ({
  synthesizeSpeech: vi.fn(() => Promise.resolve('/audio/tts_test.mp3')),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  getCapabilities: vi.fn(async () => ({ subagent: { tool_count: null } })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}<${JSON.stringify(opts)}>` : key,
    i18n: { language: 'de' },
  }),
}))

import type { ChatMessage } from '@/types'

const WITH_STEPS: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content: 'Antwort 1',
  timestamp: Date.now() - 20_000,
  durationMs: 3500,
  streaming: false,
  tool_calls: [
    {
      id: 't1',
      name: 'run_shell',
      args: { cmd: 'ls' },
      result: 'ok',
      status: 'done',
    } as unknown as NonNullable<ChatMessage['tool_calls']>[number],
  ],
}

describe('Replay link (PAKET X1)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders no inline replay frame — only one link into the trajectory tab', () => {
    render(<MessageBubble message={WITH_STEPS} />)
    expect(document.querySelector('[data-testid^="tool-replay-kader"]')).toBeNull()
    expect(document.querySelector('[data-testid^="replay-row-"]')).toBeNull()
    expect(screen.getByTestId('replay-link')).toBeTruthy()
  })

  it('the link asks the panel for the trajectory tab', () => {
    const seen: unknown[] = []
    const listener = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(PREVIEW_OPEN_EVENT, listener)
    try {
      render(<MessageBubble message={WITH_STEPS} />)
      fireEvent.click(screen.getByTestId('replay-link'))
    } finally {
      window.removeEventListener(PREVIEW_OPEN_EVENT, listener)
    }
    expect(seen).toEqual([{ tab: 'trajectory' }])
  })

  it('a turn without steps offers no replay link', () => {
    render(
      <MessageBubble
        message={{ id: 'a2', role: 'assistant', content: 'x', timestamp: 0 } as ChatMessage}
      />,
    )
    expect(screen.queryByTestId('replay-link')).toBeNull()
  })
})
