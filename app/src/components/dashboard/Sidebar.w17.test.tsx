import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// W17 P1-2: revision tree — the parentId links as indented rows
// with a connector glyph in the sidebar list.
const baseNow = Date.now()

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
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'a11y.sidebar': 'Chat sessions',
        'a11y.close': 'Close',
        'sidebar.collapse': 'Collapse sidebar',
        'sidebar.expand': 'Expand sidebar',
        'sidebar.newChat': 'New session',
        'sidebar.searchPlaceholder': 'Search…',
        'sidebar.settings': 'Settings',
        'sidebar.today': 'Today',
      }
      return map[key] ?? key
    },
  }),
}))

vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  useChatStore: () => ({
    sessions: [
      { id: 'r1', title: 'Wurzel', messages: [{ role: 'user', content: 'a' }], createdAt: baseNow },
      {
        id: 'c1',
        title: 'Zweig',
        messages: [{ role: 'user', content: 'b' }],
        createdAt: baseNow + 1,
        parentId: 'r1',
      },
    ],
    activeSessionId: 'r1',
    setActiveSession: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    renameSession: vi.fn(),
    togglePin: vi.fn(),
    toggleArchive: vi.fn(),
    markUnread: vi.fn(),
    branchSession: vi.fn(),
  }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => true, // Desktop
}))

import Sidebar from './Sidebar'

describe('Sidebar Revisionsbaum (W17 P1-2)', () => {
  it('renderet Kind-Sitzungen eingezogen mit Verbindungsglyphe', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    // Root without indent (paddingLeft 0), child with indent + the '└' glyph.
    const rootRow = screen.getByTestId('session-row-r1')
    const childRow = screen.getByTestId('session-row-c1')
    expect(rootRow.getAttribute('style') ?? '').toContain('padding-left')
    expect(childRow.getAttribute('style') ?? '').toContain('padding-left')
    const childPad = Number(
      (childRow.getAttribute('style') ?? '').match(/padding-left:\s*(\d+)/)?.[1] ?? -1,
    )
    const rootPad = Number(
      (rootRow.getAttribute('style') ?? '').match(/padding-left:\s*(\d+)/)?.[1] ?? -1,
    )
    expect(childPad).toBeGreaterThan(rootPad)
    const connector = screen.getByTestId('session-connector-c1')
    expect(connector.textContent).toBe('└')
  })

  it('zeigt wurzeln ohne Eltern-Knoten ohne Glyphe', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('session-connector-r1')).toBeNull()
  })

  it('P1-9: Elternzeile hat Fold-Toggle + Zweig-Badge; Fold klappt den Ast zu', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    // r1 is the parent of c1 → toggle + badge, child c1 visible.
    const fold = screen.getByTestId('session-fold-r1')
    expect(screen.getByTestId('session-branch-count-r1').textContent).toBe('1')
    expect(screen.getByTestId('session-row-c1')).toBeTruthy()
    expect(fold.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(fold)
    expect(fold.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByTestId('session-row-c1')).toBeNull()
    fireEvent.click(screen.getByTestId('session-fold-r1'))
    expect(screen.getByTestId('session-row-c1')).toBeTruthy()
  })
})
