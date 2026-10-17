/**
 * M2: the session context menu. The expectation is not restated here — it is read
 * from the ONE list (SESSION_MENU_GROUPS, sessionMenuEntries.ts) that Sidebar.tsx
 * renders from, so a stale pin cannot outlive a menu change in either direction.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SESSION_MENU_ENTRY_IDS, SESSION_MENU_GROUPS } from './sessionMenuEntries'
import Sidebar from './Sidebar'

vi.mock('@/lib/api', () => ({
  listProjects: vi.fn(async () => ({ projects: [] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  getTasks: vi.fn(async () => []),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'autonomous' })),
  updateSettings: vi.fn(async () => ({})),
  searchSessions: vi.fn(async () => ({ hits: [] })),
  exportChatMarkdown: vi.fn(async () => ''),
  downloadTextFile: vi.fn(),
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
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

import { useChatStore } from '@/store/chatStore'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

beforeEach(() => {
  localStorage.clear()
  useChatStore.setState({
    sessions: [{ id: 's1', title: 'Alpha', createdAt: 0, messages: [] }],
    activeSessionId: 's1',
    currentSession: { id: 's1', title: 'Alpha', createdAt: 0, messages: [] },
    checkpoints: {},
  })
})

async function openMenu() {
  render(
    <Sidebar
      isOpen
      onClose={() => {}}
      collapsed={false}
      onToggleCollapsed={() => {}}
      onOpenSettings={vi.fn()}
    />,
  )
  const more = await screen.findByTestId('session-menu-s1')
  fireEvent.click(more)
  return screen.findByTestId('session-context-menu')
}

describe('Session-Kontext-Menue (M2, 1:1-Gruppen)', () => {
  it('renders every entry of the ONE list, in order, with a rule between the groups', async () => {
    const menu = await openMenu()
    // Read the rows back from the DOM and compare them with the list the component
    // renders from — an extra row, a missing row or a reorder all fail here.
    const rendered = Array.from(menu.querySelectorAll<HTMLElement>('[data-testid^="menu-"]'))
      .filter((el) => !(el.getAttribute('data-testid') ?? '').startsWith('menu-sep-'))
      .map((el) => (el.getAttribute('data-testid') ?? '').replace(/^menu-/, ''))
    expect(rendered).toEqual([...SESSION_MENU_ENTRY_IDS])
    // one rule between the groups (one fewer than the groups)
    expect(menu.querySelectorAll('[data-testid^="menu-sep-"]').length).toBe(
      SESSION_MENU_GROUPS.length - 1,
    )
  })

  it('archive: the session leaves the list, the pin set stays logic-free', async () => {
    const menu = await openMenu()
    fireEvent.click(menu.querySelector('[data-testid="menu-archive"]')!)
    expect(useChatStore.getState().sessions.find((s) => s.id === 's1')?.archived).toBe(true)
  })

  it('mark as unread sets the unread field', async () => {
    const menu = await openMenu()
    fireEvent.click(menu.querySelector('[data-testid="menu-unread"]')!)
    expect(useChatStore.getState().sessions.find((s) => s.id === 's1')?.unread).toBe(true)
  })

  it('Trajektorie oeffnet den Replay-Tab im Pane', async () => {
    const spy = vi.fn()
    window.addEventListener(PREVIEW_OPEN_EVENT, spy)
    const menu = await openMenu()
    fireEvent.click(menu.querySelector('[data-testid="menu-trajectory"]')!)
    window.removeEventListener(PREVIEW_OPEN_EVENT, spy)
    expect(spy).toHaveBeenCalled()
    const detail = (spy.mock.calls[0]![0] as CustomEvent<{ tab?: string }>).detail
    expect(detail?.tab).toBe('trajectory')
  })
})

describe('Session menu: the keyboard path (W3-57)', () => {
  async function openViaTrigger() {
    render(
      <Sidebar
        isOpen
        onClose={() => {}}
        collapsed={false}
        onToggleCollapsed={() => {}}
        onOpenSettings={vi.fn()}
      />,
    )
    const trigger = await screen.findByTestId('session-menu-s1')
    fireEvent.click(trigger)
    const menu = await screen.findByTestId('session-context-menu')
    const items = await screen.findAllByRole('menuitem')
    return { trigger, menu, items }
  }

  it('focus moves into the menu on open; entries are roving targets (tabindex=-1)', async () => {
    const { menu, items } = await openViaTrigger()
    expect(menu.getAttribute('role')).toBe('menu')
    expect(items.length).toBe(SESSION_MENU_ENTRY_IDS.length)
    for (const item of items) expect(item.getAttribute('tabindex')).toBe('-1')
    await waitFor(() => expect(document.activeElement).toBe(items[0]))
  })

  it('arrows and Home/End walk through the entries', async () => {
    const { menu, items } = await openViaTrigger()
    await waitFor(() => expect(document.activeElement).toBe(items[0]))

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])
    fireEvent.keyDown(menu, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(items[0])
    fireEvent.keyDown(menu, { key: 'End' })
    expect(document.activeElement).toBe(items[items.length - 1])
    fireEvent.keyDown(menu, { key: 'Home' })
    expect(document.activeElement).toBe(items[0])
  })

  it('Escape closes the menu and returns focus to the trigger', async () => {
    const { trigger, menu } = await openViaTrigger()
    fireEvent.keyDown(menu, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('session-context-menu')).toBeNull())
    expect(document.activeElement).toBe(trigger)
  })

  it('Tab closes the menu instead of trapping focus inside it', async () => {
    const { menu } = await openViaTrigger()
    fireEvent.keyDown(menu, { key: 'Tab' })
    await waitFor(() => expect(screen.queryByTestId('session-context-menu')).toBeNull())
  })
})
