/**
 * The task register below 1024 px, where the frame's rail is not on screen.
 *
 * The rail takes the five rows that name a page from 1024 px up. A phone gets the tab bar
 * instead, and the tab bar carries five of the places — so the drawer has to keep the whole
 * register, or `/workspaces` and `/artifacts` would have no way in. This file is the proof
 * that the desktop trim did not become a deletion.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Sidebar from './Sidebar'
import { RAIL_DESTINATIONS, SIDEBAR_ACTION_ENTRY_IDS } from './sidebarActionGroups'

const storeMocks = vi.hoisted(() => ({
  sessions: [
    {
      id: 's1',
      title: 'Alpha',
      messages: [{ role: 'user', content: 'Hallo' }],
      createdAt: Date.now(),
    },
  ] as Array<Record<string, unknown>>,
  activeSessionId: 's1',
}))

const apiMocks = vi.hoisted(() => ({
  listProjects: vi.fn(async () => ({ projects: [] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  updateSettings: vi.fn(async () => ({})),
  getSettings: vi.fn(async () => ({ workspace_dir: null, approval_profile: 'strict' })),
  getTasks: vi.fn(async () => []),
  searchSessions: vi.fn(async () => []),
  exportChatMarkdown: vi.fn(async () => ''),
  downloadTextFile: vi.fn(),
}))

vi.mock('framer-motion', () => ({
  m: {
    aside: (props: Record<string, unknown>) => (
      <aside data-testid="chat-sidebar" {...(props as React.ComponentProps<'aside'>)} />
    ),
  },
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  useChatStore: () => ({
    sessions: storeMocks.sessions,
    activeSessionId: storeMocks.activeSessionId,
    setActiveSession: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    renameSession: vi.fn(),
    togglePin: vi.fn(),
  }),
}))

// The drawer case: no media match, so the sidebar is the only navigation there is.
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => false }))

vi.mock('@/lib/api', () => ({
  listProjects: apiMocks.listProjects,
  listSchedules: apiMocks.listSchedules,
  updateSettings: apiMocks.updateSettings,
  getSettings: apiMocks.getSettings,
  getTasks: apiMocks.getTasks,
  searchSessions: apiMocks.searchSessions,
  exportChatMarkdown: apiMocks.exportChatMarkdown,
  downloadTextFile: apiMocks.downloadTextFile,
}))

describe('the drawer keeps the whole register', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('carries every row the ONE list names, the rail’s five included', async () => {
    render(
      <Sidebar
        isOpen
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    await screen.findByTestId('sidebar-actions')

    for (const id of SIDEBAR_ACTION_ENTRY_IDS) {
      expect(screen.getByTestId(`sidebar-action-${id}`), id).toBeTruthy()
    }
    // The trim is a move, not a removal: the five would be missing on desktop.
    expect(RAIL_DESTINATIONS.length).toBeGreaterThan(0)
    expect(screen.getByTestId('sidebar-tier-tools-count').textContent).toBe('7')
    expect(screen.getByTestId('sidebar-tier-more-count').textContent).toBe('5')
  })
})
