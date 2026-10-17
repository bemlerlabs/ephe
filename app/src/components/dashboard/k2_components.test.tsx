import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// K2 (2026-09-08): wiring up the orphaned routes — Z38 export menu entry in
// the sidebar, Z13 thumb pairs on the assistant bubble.

const apiMocks = vi.hoisted(() => ({
  exportChatMarkdown: vi.fn(async () => '## Chat Export\n**Nutzer:** hi'),
  downloadTextFile: vi.fn(),
  feedbackThumbsUp: vi.fn(async () => ({ saved: true })),
  feedbackThumbsDown: vi.fn(async () => ({ saved: true })),
  fileUrl: vi.fn((p: string) => `/api/file?path=${p}`),
  synthesizeSpeech: vi.fn(async () => ''),
  getTasks: vi.fn(async () => []),
  listProjects: vi.fn(async () => ({ workspace: '', projects: [], generated_at: '' })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  updateSettings: vi.fn(async () => ({})),
  getSettings: vi.fn(async () => ({ workspace_dir: null, approval_profile: 'strict' })),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
}))

vi.mock('@/lib/api', () => apiMocks)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}))

const storeMocks = vi.hoisted(() => ({
  sessions: [
    {
      id: 's1',
      title: 'Alpha',
      messages: [
        { role: 'user', content: 'Hallo' },
        { role: 'assistant', content: 'Hi' },
      ],
      createdAt: Date.now(),
    },
  ] as Array<Record<string, unknown>>,
  activeSessionId: 's1',
}))
vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  useChatStore: (sel?: (s: Record<string, unknown>) => unknown) => {
    const st: Record<string, unknown> = {
      sessions: storeMocks.sessions,
      activeSessionId: storeMocks.activeSessionId,
      setActiveSession: vi.fn(),
      createSession: vi.fn(),
      deleteSession: vi.fn(),
      renameSession: vi.fn(),
      togglePin: vi.fn(),
    }
    return sel ? sel(st) : st
  },
}))
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }))

import Sidebar from './Sidebar'
import MessageBubble from './MessageBubble'
import type { ChatMessage } from '@/types'

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('K2 Z38 — Export im Session-Menue', () => {
  it('Menue-Punkt "menu-export" ruft exportChatMarkdown mit den Session-Messages', async () => {
    render(
      <Sidebar
        isOpen
        onClose={() => {}}
        onOpenSettings={() => {}}
        collapsed={false}
        onToggleCollapsed={() => {}}
      />,
    )
    fireEvent.click(screen.getByTestId('session-menu-s1'))
    expect(await screen.findByTestId('menu-export')).toBeTruthy()
    fireEvent.click(screen.getByTestId('menu-export'))
    await vi.waitFor(() => {
      expect(apiMocks.exportChatMarkdown).toBeCalled()
      expect(apiMocks.downloadTextFile).toBeCalled()
    })
    const arg = (apiMocks.exportChatMarkdown.mock.calls[0] as unknown[])[0] as Array<
      Record<string, unknown>
    >
    expect(arg[0]?.role).toBe('user')
    expect((apiMocks.downloadTextFile.mock.calls[0] as unknown[])[0]).toBe('ephe-s1.md')
  })
})

describe('K2 Z13 — Thumbs an der Assistant-Bubble', () => {
  const msg: ChatMessage = { id: 'a1', role: 'assistant', content: 'Antwort', timestamp: 1 }

  it('up/down POSTen das Paar (prevUser, content) an die Routen', async () => {
    render(<MessageBubble message={msg} prevUserContent="Vorherige Frage" />)
    fireEvent.click(screen.getByTestId('msg-thumbs-up'))
    expect(apiMocks.feedbackThumbsUp).toHaveBeenCalledWith('Vorherige Frage', 'Antwort')
    fireEvent.click(screen.getByTestId('msg-thumbs-down'))
    expect(apiMocks.feedbackThumbsDown).toHaveBeenCalledWith('Vorherige Frage', 'Antwort')
  })

  it('Auswahl bleibt als akzentuierter Zustand sichtbar (up nach down)', () => {
    render(<MessageBubble message={msg} prevUserContent="" />)
    fireEvent.click(screen.getByTestId('msg-thumbs-up'))
    const up = screen.getByTestId('msg-thumbs-up')
    expect(String(up.className)).toMatch(/text-brand/)
  })
})
