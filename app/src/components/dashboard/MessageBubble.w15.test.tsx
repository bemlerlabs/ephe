/**
 * W15 · P1 — turn-level branch action in the message hover bar
 *
 * GIVEN  an assistant message inside a session with several messages
 * WHEN   the branch button (data-testid="message-branch") gets clicked
 * THEN   branchSession(message.id) runs: a fresh session with parentId,
 *        the prefix up to the target message, the branch made active
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'
import { useChatStore } from '@/store/chatStore'

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => (
    <div data-testid="markdown">{String(children)}</div>
  ),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: React.ReactNode }) => <pre>{children}</pre>,
}))
vi.mock('@/lib/utils', () => ({ formatTime: () => '12:00' }))
vi.mock('@/lib/api', () => ({
  synthesizeSpeech: vi.fn(() => Promise.resolve('/audio/tts_test.mp3')),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: (() => ({ t: (key: string) => key, i18n: { language: 'de' } })) as never,
}))

import type { ChatMessage } from '@/types'

function seed(): ChatMessage[] {
  const msgs: ChatMessage[] = [
    { id: 'u1', role: 'user', content: 'eins', timestamp: 0 },
    { id: 'a1', role: 'assistant', content: 'zwei', timestamp: 0 },
    { id: 'u2', role: 'user', content: 'drei', timestamp: 0 },
  ]
  useChatStore.setState({
    sessions: [{ id: 'sess-1', title: 'Basis', messages: msgs, createdAt: 0 } as never],
    activeSessionId: 'sess-1',
    currentSession: { id: 'sess-1', title: 'Basis', messages: msgs, createdAt: 0 } as never,
    isTyping: false,
    pendingToolCall: null,
    checkpoints: {},
  })
  return msgs
}

describe('MessageBubble · W15 Branch-Aktion', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
  })

  it('rendert den Branch-Button in der Action-Zeile', () => {
    const msgs = seed()
    render(<MessageBubble message={msgs[1]!} />)
    expect(screen.getByTestId('message-branch')).toBeTruthy()
  })

  it('Klick zweigt: neue Session mit parentId + Praefix bis zur Ziel-Message', () => {
    const msgs = seed()
    render(<MessageBubble message={msgs[1]!} />)
    fireEvent.click(screen.getByTestId('message-branch'))

    const st = useChatStore.getState()
    const fork = st.sessions.find((s) => s.parentId === 'sess-1')
    expect(fork).toBeTruthy()
    expect(fork!.messages.length).toBe(2) // the prefix up to and including 'a1'
    expect(fork!.messages[1]!.id).toBe('a1')
    expect(st.activeSessionId).toBe(fork!.id)
    // the original session stays untouched
    const orig = st.sessions.find((s) => s.id === 'sess-1')
    expect(orig!.messages.length).toBe(3)
  })
})
