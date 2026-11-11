/**
 * The phone drawer as a dialog. Before this, the closed drawer stayed in the tab
 * order behind the viewport edge and an open one never took focus, so a keyboard
 * user walked through controls that were not on screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useState } from 'react'
import Sidebar from './Sidebar'

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
    sessions: [],
    activeSessionId: null,
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
  listProjects: vi.fn(async () => ({ projects: [] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  updateSettings: vi.fn(async () => ({})),
  getSettings: vi.fn(async () => ({ workspace_dir: null, approval_profile: 'strict' })),
  getTasks: vi.fn(async () => []),
  searchSessions: vi.fn(async () => []),
  exportChatMarkdown: vi.fn(async () => ''),
  downloadTextFile: vi.fn(),
}))

function DrawerHost({ onClose = vi.fn() }: { onClose?: () => void }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <button type="button" data-testid="header-menu-toggle" onClick={() => setOpen(true)}>
        menu
      </button>
      <Sidebar
        isOpen={open}
        onClose={() => {
          setOpen(false)
          onClose()
        }}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />
    </>
  )
}

describe('the mobile drawer is a dialog only while open', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('closed: inert and hidden, without dialog semantics', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    const aside = screen.getByTestId('chat-sidebar')
    expect(aside.hasAttribute('inert')).toBe(true)
    expect(aside.getAttribute('aria-hidden')).toBe('true')
    expect(aside.getAttribute('role')).toBeNull()
    expect(aside.getAttribute('aria-modal')).toBeNull()
  })

  it('open: dialog + modal, and focus moves to the close button', async () => {
    render(<DrawerHost />)
    const aside = screen.getByTestId('chat-sidebar')
    expect(aside.getAttribute('role')).toBe('dialog')
    expect(aside.getAttribute('aria-modal')).toBe('true')
    expect(aside.hasAttribute('inert')).toBe(false)
    expect(aside.getAttribute('aria-hidden')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId('sidebar-close')))
  })

  it('Tab is trapped inside the drawer', async () => {
    render(<DrawerHost />)
    const aside = screen.getByTestId('chat-sidebar')
    const close = screen.getByTestId('sidebar-close')
    await waitFor(() => expect(document.activeElement).toBe(close))
    // Shift+Tab on the first stop wraps to the last one instead of leaving the dialog.
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    expect(aside.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).not.toBe(close)
  })

  it('Escape closes the drawer and returns focus to the header trigger', async () => {
    const onClose = vi.fn()
    render(<DrawerHost onClose={onClose} />)
    const close = screen.getByTestId('sidebar-close')
    await waitFor(() => expect(document.activeElement).toBe(close))
    fireEvent.keyDown(close, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    const aside = screen.getByTestId('chat-sidebar')
    await waitFor(() => expect(aside.hasAttribute('inert')).toBe(true))
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByTestId('header-menu-toggle')),
    )
  })
})
