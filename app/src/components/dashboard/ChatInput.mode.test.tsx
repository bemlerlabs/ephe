import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/lib/api', () => ({
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'm' },
    providers: [],
    local_models: [],
    local_model_options: [],
  })),
  transcribeAudio: vi.fn(async () => ''),
  listFs: vi.fn(async () => ({ entries: [] })),
  getSettings: vi.fn(async () => ({ workspace_dir: null, approval_profile: 'strict' })),
  setModelProvider: vi.fn(async () => ({ ok: true })),
  getSetupStatus: vi.fn(async () => ({
    configured: true,
    provider: 'local_ollama',
    model: null,
    url: null,
    reachable: true,
    available_models: [],
  })),
}))
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }))

import ChatInput from './ChatInput'
import { useChatStore } from '@/store/chatStore'

beforeEach(() => {
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
})

describe('Composer-Modus-Switch (P4)', () => {
  it('Analyst-Hinweis sichtbar, Operator-Klick blendet ihn aus + Chip + Session.mode', () => {
    useChatStore.getState().createSession('S')
    useChatStore.getState().setSessionMode(useChatStore.getState().activeSessionId!, 'analyst')
    render(
      <ChatInput
        onSend={() => {
          /* noop */
        }}
      />,
    )
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain('Analyst')
    expect(screen.queryByTestId('composer-ask-hint')).not.toBeNull()
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    fireEvent.click(screen.getByTestId('composer-mode-operator'))
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain('Operator')
    expect(screen.queryByTestId('composer-ask-hint')).toBeNull()
    const st = useChatStore.getState()
    expect(st.sessions.find((x) => x.id === st.activeSessionId)?.mode).toBe('operator')
  })

  it.each([
    ['analyst', 'Analyst'],
    ['architect', 'Architect'],
    ['operator', 'Operator'],
  ] as const)('Modus %s → Chip %s + Session.mode', (key, label) => {
    useChatStore.getState().createSession('S')
    render(
      <ChatInput
        onSend={() => {
          /* noop */
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    fireEvent.click(screen.getByTestId(`composer-mode-${key}`))
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain(label)
    const st = useChatStore.getState()
    expect(st.sessions.find((x) => x.id === st.activeSessionId)?.mode).toBe(key)
  })

  it('ohne aktive Session (null) aktualisiert der Klick zumindest den Chip', () => {
    render(
      <ChatInput
        onSend={() => {
          /* noop */
        }}
      />,
    )
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    fireEvent.click(screen.getByTestId('composer-mode-operator'))
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain('Operator')
  })
})
