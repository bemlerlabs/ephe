import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const storeMocks = vi.hoisted(() => ({
  togglePin: vi.fn(),
  // Mutable so that the DD-25 filter (hide empty sessions) can be set
  // deliberately per test; beforeEach restores the baseline state.
  sessions: [
    {
      id: 's1',
      title: 'Alpha',
      messages: [{ role: 'user', content: 'Hallo' }],
      createdAt: Date.now(),
    },
    {
      id: 's2',
      title: 'Beta',
      messages: [{ role: 'user', content: 'Hallo' }],
      createdAt: Date.now(),
      pinned: true,
    },
  ] as Array<Record<string, unknown>>,
  activeSessionId: 's1',
}))

// framer-motion mock — pass motion.aside through as a plain aside
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
        'sidebar.today': 'Heute',
      }
      return map[key] ?? key
    },
  }),
}))

vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  useChatStore: () => ({
    sessions: storeMocks.sessions,
    activeSessionId: storeMocks.activeSessionId,
    setActiveSession: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    renameSession: vi.fn(),
    togglePin: storeMocks.togglePin,
  }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => true, // Desktop
}))

import Sidebar from './Sidebar'

describe('Sidebar-Desktop-Collapse', () => {
  it('collapsed: Rail w-14, Titel + Search ausgeblendet, Toggle-Label wechselt', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={true}
        onToggleCollapsed={vi.fn()}
      />,
    )
    const aside = screen.getByTestId('chat-sidebar')
    expect(aside.className).toContain('w-14')
    expect(screen.queryByRole('button', { name: 'Collapse sidebar' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeTruthy()
    expect(screen.queryByPlaceholderText('Search…')).toBeNull()
    // Sessions stay clickable (icon rail)
    expect(screen.getByTitle('Alpha')).toBeTruthy()
  })

  it('collapsed: Expand-Button klickbar und feuert onToggleCollapsed (Regression: war im w-14-Rail geklippt)', () => {
    const onToggle = vi.fn()
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={true}
        onToggleCollapsed={onToggle}
      />,
    )
    const expand = screen.getByTestId('sidebar-expand-toggle')
    expect(expand).toBeTruthy()
    fireEvent.click(expand)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('expanded: w-72 + Sessionstitel + Search sichtbar', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    expect(screen.getByTestId('chat-sidebar').className).toContain('w-72')
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeTruthy()
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.getByPlaceholderText('Search…')).toBeTruthy()
  })

  it('expanded: Logo-Block entfernt — kein hero-frost-h2, kein nav.appName/sidebar.edition-Doppel (R38)', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    // The big display logo block (hero-frost h2 + edition line) was removed;
    // the name now stands only in the chat hero. The i18n mock falls back to the key,
    // so 'nav.appName'/'sidebar.edition' would show up as a raw key if the block
    // still existed.
    expect(screen.queryByText('nav.appName')).toBeNull()
    expect(screen.queryByText('sidebar.edition')).toBeNull()
    expect(document.querySelector('.hero-frost')).toBeNull()
    // The new-session structure remains as the first interactive block.
    expect(screen.getByTestId('new-session')).toBeTruthy()
  })

  it('Group-Collapse: Header-Klick einklappen, zweiter Klick ausklappen', () => {
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    expect(screen.getByText('Alpha')).toBeTruthy()
    const groupHeader = screen.getByRole('button', { name: /Heute.*2/ })
    fireEvent.click(groupHeader)
    expect(screen.queryByText('Alpha')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Heute.*2/ }))
    expect(screen.getByText('Alpha')).toBeTruthy()
  })

  it('onToggleCollapsed feuert beim Klick', () => {
    const onToggle = vi.fn()
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={vi.fn()}
        collapsed={false}
        onToggleCollapsed={onToggle}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('Settings-Karte unter den Sessions ist der Settings-Zugang (Owner-Entscheid: ein Knopf)', () => {
    const onOpen = vi.fn()
    render(
      <Sidebar
        isOpen={false}
        onClose={vi.fn()}
        onOpenSettings={onOpen}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
      />,
    )
    const btn = screen.getByTestId('sidebar-settings-btn')
    expect(btn).toBeTruthy()
    fireEvent.click(btn)
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})

// R26: Session context menu — right-click or the ⋯ hover button opens the
// same menu (Pin / Rename / Copy session ID / Delete), like leading AI clients.
describe('R26 Session context menu', () => {
  function mount() {
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

  it('right-click on a session row opens the context menu', () => {
    mount()
    fireEvent.contextMenu(screen.getByText('Alpha'))
    expect(screen.getByTestId('session-context-menu')).toBeTruthy()
    expect(screen.getByTestId('menu-pin')).toBeTruthy()
    expect(screen.getByTestId('menu-rename')).toBeTruthy()
    expect(screen.getByTestId('menu-copy-id')).toBeTruthy()
    expect(screen.getByTestId('menu-delete')).toBeTruthy()
  })

  it('menu-pin calls togglePin with the session id and closes the menu', () => {
    const { container } = mount()
    fireEvent.contextMenu(screen.getByText('Alpha'))
    fireEvent.click(screen.getByTestId('menu-pin'))
    expect(storeMocks.togglePin).toHaveBeenCalledWith('s1')
    expect(screen.queryByTestId('session-context-menu')).toBeNull()
    void container
  })

  it('menu-copy-id writes the session id to the clipboard', async () => {
    const writeText = vi.fn(async () => {})
    Object.assign(navigator, { clipboard: { writeText } })
    mount()
    fireEvent.contextMenu(screen.getByText('Alpha'))
    fireEvent.click(screen.getByTestId('menu-copy-id'))
    await Promise.resolve()
    expect(writeText).toHaveBeenCalledWith('s1')
  })

  it('menu-delete shows the inline delete confirm on the row', () => {
    mount()
    fireEvent.contextMenu(screen.getByText('Alpha'))
    fireEvent.click(screen.getByTestId('menu-delete'))
    expect(screen.queryByTestId('session-context-menu')).toBeNull()
    expect(screen.getByText('sidebar.deleteAction')).toBeTruthy()
  })

  it('⋯ button opens the same menu (touch/mobile path)', () => {
    mount()
    fireEvent.click(screen.getByTestId('session-menu-s1'))
    expect(screen.getByTestId('session-context-menu')).toBeTruthy()
  })

  it('pinned session shows the pin indicator and sorts first', () => {
    mount()
    // Beta has pinned: true in the mock — its pin indicator must exist
    const pins = screen.getAllByLabelText('sidebar.sessionMenu.pinnedAria')
    expect(pins.length).toBe(1)
    const titles = screen.getAllByTestId('session-title-text').map((el) => el.textContent)
    expect(titles.indexOf('Beta')).toBeLessThan(titles.indexOf('Alpha'))
  })
})

// DD-25: brand-new sessions without any message used to clutter the list.
// Only the active session stays visible while empty; every other empty
// session is hidden until it has content.
describe('DD-25 empty-session filter', () => {
  const baseSessions = () =>
    [
      {
        id: 's1',
        title: 'Alpha',
        messages: [{ role: 'user', content: 'Hallo' }],
        createdAt: Date.now(),
      },
      {
        id: 's2',
        title: 'Beta',
        messages: [{ role: 'user', content: 'Hallo' }],
        createdAt: Date.now(),
        pinned: true,
      },
    ] as Array<Record<string, unknown>>

  beforeEach(() => {
    storeMocks.sessions = baseSessions()
    storeMocks.activeSessionId = 's1'
  })

  function mount() {
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

  it('hides an empty session that is not active', () => {
    storeMocks.sessions.push({ id: 's3', title: 'Gamma', messages: [], createdAt: Date.now() })
    mount()
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.queryByText('Gamma')).toBeNull()
  })

  it('keeps an empty session visible while it is the active one', () => {
    storeMocks.sessions.push({ id: 's3', title: 'Gamma', messages: [], createdAt: Date.now() })
    storeMocks.activeSessionId = 's3'
    mount()
    expect(screen.getByText('Gamma')).toBeTruthy()
  })

  it('DEFAULT-Sitzungstitel erscheint uebersetzt statt als EN-Rohwert (I6 P3-4)', () => {
    storeMocks.sessions[0]!.title = 'New Session'
    mount()
    const titles = screen.getAllByTestId('session-title-text')
    expect(titles.length).toBeGreaterThan(0)
    // Do not assume the sorting (pinned on top) — the list carries no single
    // raw EN value any more, the default line shows up translated.
    expect(titles.some((el) => el.textContent === 'New Session')).toBe(false)
    expect(titles.some((el) => el.textContent === 'New session')).toBe(true)
  })
})
