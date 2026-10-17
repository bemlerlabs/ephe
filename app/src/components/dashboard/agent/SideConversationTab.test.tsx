// N1 — the side-conversation tab: a compact reading form of the active session
// with a role chip, a clock time and the full text per message; an empty state
// when there is no session.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SideConversationTab } from './tabsA'
import { useChatStore } from '@/store/chatStore'
import type { ChatMessage } from '@/types'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      typeof opts?.defaultValue === 'string' ? opts.defaultValue : key,
  }),
}))

const MSGS: ChatMessage[] = [
  { id: 'u1', role: 'user', content: 'frage', timestamp: 1761806357000 },
  { id: 'a1', role: 'assistant', content: 'antwort', timestamp: 1761806360000 },
] as ChatMessage[]

describe('SideConversationTab (N1)', () => {
  beforeEach(() => {
    useChatStore.setState({
      activeSessionId: null,
      currentSession: null,
    })
  })

  it('ohne aktive Session: Leerzustand', () => {
    render(<SideConversationTab />)
    expect(screen.getByTestId('side-conversation-empty')).toBeTruthy()
  })

  it('aktive Session: eine Zeile je Nachricht mit Rolle und Inhalt', () => {
    useChatStore.setState({
      activeSessionId: 's1',
      currentSession: {
        id: 's1',
        title: 'T',
        messages: MSGS,
        created_at: 1,
        updated_at: 2,
      } as never,
    })
    render(<SideConversationTab />)
    expect(screen.getByTestId('side-conversation')).toBeTruthy()
    const l0 = screen.getByTestId('side-msg-0')
    const l1 = screen.getByTestId('side-msg-1')
    expect(l0.textContent).toContain('user')
    expect(l0.textContent).toContain('frage')
    expect(l1.textContent).toContain('assistant')
    expect(l1.textContent).toContain('antwort')
  })
})
