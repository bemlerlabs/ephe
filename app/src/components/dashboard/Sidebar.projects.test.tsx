import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// W2-1 (2026-09-09): project anchors in the PROJECTS section — the active
// workspace project carries a green pin + aria-current; projects merely
// following along have neither. A click sets the workspace (updateSettings).

const updateSettings = vi.fn(async (_args: unknown) => ({ success: true }))

vi.mock('@/lib/api', () => ({
  listProjects: vi.fn(async () => ({
    workspace: '/tmp/alpha',
    generated_at: 'now',
    projects: [
      { name: 'Alpha', path: '/tmp/alpha', stacks: ['py'], score: 1, workspace: true },
      { name: 'Beta', path: '/tmp/beta', stacks: ['ts'], score: 0.5, workspace: false },
    ],
  })),
  listSchedules: vi.fn(async () => []),
  getTasks: vi.fn(async () => []),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/alpha' })),
  updateSettings: (args: unknown) => updateSettings(args),
  searchSessions: vi.fn(async () => []),
  exportChatMarkdown: vi.fn(async () => ''),
  downloadTextFile: vi.fn(),
}))

vi.mock('framer-motion', () => ({
  // The surfaces animate with `m` — LazyMotion's core component; the app root
  // mounts the feature set once (App.tsx). The stub has to answer for `m`.
  m: {
    aside: (props: Record<string, unknown>) => (
      <aside data-testid="chat-sidebar" {...(props as React.ComponentProps<'aside'>)} />
    ),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  useChatStore: () => ({
    sessions: [],
    activeSessionId: null,
    setActiveSession: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    renameSession: vi.fn(),
    togglePin: vi.fn(),
  }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => true, // Desktop
}))

import Sidebar from './Sidebar'

function renderSidebar() {
  return render(
    <Sidebar
      isOpen={false}
      onClose={vi.fn()}
      onOpenSettings={vi.fn()}
      collapsed={false}
      onToggleCollapsed={vi.fn()}
    />,
  )
}

describe('W2 — Projekt-Anker (aktives Workspace-Projekt)', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('ephe.sidebar.view', 'project')
    updateSettings.mockClear?.()
  })

  it('aktives Projekt: gruene Nadel + aria-current, Mitlaufende ohne', async () => {
    renderSidebar()
    const rows = await screen.findAllByTestId('sidebar-project')
    expect(rows).toHaveLength(2)
    const active = rows.find((r) => r.getAttribute('aria-current') === 'true')
    expect(active).toBeTruthy()
    expect(active!.querySelector('[data-testid="sidebar-project-dot"]')).toBeTruthy()
    const plain = rows.find((r) => r !== active)
    expect(plain!.querySelector('[data-testid="sidebar-project-dot"]')).toBeNull()
  })

  it('Klick auf ein Projekt setzt den Workspace via updateSettings', async () => {
    renderSidebar()
    const rows = await screen.findAllByTestId('sidebar-project')
    fireEvent.click(rows[1]!)
    expect(updateSettings).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(updateSettings.mock.calls[0]![0])).toContain('/tmp/beta')
  })
})
