import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// Visibility wave: the helper chat is recognisable as a helper in the sidebar,
// not as an ordinary task — it hangs as a child on the parent task's branch
// (buildSessionTree), but carries its own marker.

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
  useTranslation: () => ({ t: (key: string) => key }),
}))

const setActiveSession = vi.fn()

vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  useChatStore: () => ({
    sessions: [
      {
        id: 'r1',
        title: 'Mutteraufgabe',
        messages: [{ role: 'user', content: 'a' }],
        createdAt: baseNow,
      },
      {
        id: 'helper-9e8d7c6b',
        title: 'Research HTTP timeouts',
        messages: [{ role: 'user', content: 'b' }],
        createdAt: baseNow + 1,
        parentId: 'r1',
      },
    ],
    activeSessionId: 'r1',
    setActiveSession,
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    renameSession: vi.fn(),
    togglePin: vi.fn(),
    toggleArchive: vi.fn(),
    markUnread: vi.fn(),
    branchSession: vi.fn(),
  }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }))

import Sidebar from './Sidebar'

describe('Sidebar — Helfer-Kind ist als Helfer gekennzeichnet', () => {
  it('zeigt die Helfer-Markierung an der Kind-Zeile, nicht an der Aufgabe', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    expect(screen.getByTestId('session-row-helper-9e8d7c6b')).toBeTruthy()
    expect(screen.getByTestId('session-helper-mark-helper-9e8d7c6b')).toBeTruthy()
    expect(screen.queryByTestId('session-helper-mark-r1')).toBeNull()
  })
})
