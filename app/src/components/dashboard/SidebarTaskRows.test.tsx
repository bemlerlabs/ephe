import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TaskRowGroup } from './SidebarTaskRows'

/**
 * The reading direction, pinned where it is visible: the sidebar's task rows.
 * These assertions hold the four rules the slice introduces: one Rule between
 * rows, the trailing number on one right axis, the three reading steps in their
 * roles, and the accent on a running row only.
 */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'sidebar.newChat': 'New task',
        'sidebar.messages': 'messages',
        'sidebar.ready': 'Ready',
        'sidebar.freshCell': 'New one-way cell',
        'sidebar.expandBranch': 'Expand branch',
        'sidebar.collapseBranch': 'Collapse branch',
        'sidebar.helperChat': 'Helper',
        'sidebar.renameHint': 'Rename task',
        'sidebar.deleteAction': 'Delete task',
        'sidebar.deleteCancel': 'Cancel',
        'sidebar.filterUnread': 'Unread',
        'sidebar.sessionMenu.aria': 'Session menu',
        'sidebar.sessionMenu.pinnedAria': 'Pinned',
      }
      return map[key] ?? key
    },
    i18n: { language: 'en' },
  }),
}))

vi.mock('@/store/chatStore', () => ({
  useChatStore: () => ({}),
  DEFAULT_SESSION_TITLE: 'New task',
}))

const base = Date.now() - 60_000
const sessions = [
  {
    id: 's1',
    title: 'Research the criticism',
    createdAt: base,
    messages: [{ id: 'm1', role: 'user', content: 'a' }],
  },
  {
    id: 's2',
    title: 'Session-deep: delete check',
    createdAt: base - 1000,
    messages: [{ id: 'm2', role: 'user', content: 'b' }],
    parentId: 's1',
  },
  {
    id: 's3',
    title: 'Report the mutation catch',
    createdAt: base - 2000,
    messages: [
      { id: 'm3', role: 'user', content: 'c' },
      { id: 'm4', role: 'assistant', content: 'd' },
    ],
    unread: true,
  },
]

function renderGroup(over: Partial<React.ComponentProps<typeof TaskRowGroup>> = {}) {
  const props = {
    label: 'Today',
    sessions,
    collapsed: false,
    onToggleCollapse: () => {},
    rail: false,
    activeSessionId: null,
    runningSessionId: null,
    collapsedBranches: new Set<string>(),
    onSelect: () => {},
    onToggleBranch: () => {},
    rename: { id: null, draft: '', setDraft: () => {}, commit: () => {}, cancel: () => {} },
    deleteConfirmId: null,
    onDeleteConfirm: () => {},
    onDeleteCancel: () => {},
    onOpenMenu: () => {},
    menuReturnRef: { current: null },
    ...over,
  }
  return render(<TaskRowGroup {...props} />)
}

const classesIn = (el: Element): string[] =>
  [...el.querySelectorAll('*')].map((e) => e.getAttribute('class') ?? '')

describe('sidebar task rows — the direction, measured', () => {
  it('separates rows with one Rule between them and no card at all', () => {
    const { container } = renderGroup()
    const rows = container.querySelector('[data-testid="task-rows"]')!
    // Rule paints the line; it is the only separator in the block.
    const lines = [...rows.querySelectorAll('.bg-hairline')]
    expect(lines).toHaveLength(sessions.length - 1)
    // No radius, no shadow, no card background on any row.
    const cls = [...classesIn(rows), rows.getAttribute('class') ?? ''].join(' ')
    expect(cls).not.toMatch(/\brounded-|shadow-|bg-surface-raised|bg-brand\/10|border-brand/)
  })

  it('trades the zero counters for the ready line on a fresh session', () => {
    renderGroup({
      sessions: [{ id: 'fresh', title: 'New task', createdAt: base, messages: [] }],
    })
    const age = screen.getByTestId('session-age-fresh')
    expect(age.textContent).toBe('New one-way cell')
    // The label is row meta, so it takes the data step and may shrink: at the base step
    // it reached over the ⋯ button beside it, measured on the desktop build 2026-11-01.
    expect(age.className).toContain('min-w-0')
    expect(age.firstElementChild!.className).toContain('text-scale-data')
    expect(document.body.textContent).not.toContain('0 messages')
    expect(document.body.textContent).toContain('Ready')
  })

  it('sets the title at the UI step and the meta line at the data step', () => {
    renderGroup()
    const titles = screen.getAllByTestId('session-title-text')
    for (const title of titles) expect(title.className).toContain('text-scale-ui')
    const age = screen.getByTestId('session-age-s1')
    expect(age.textContent).toBeTruthy()
    expect(age.innerHTML).toContain('text-scale-data')
  })

  it('ends every trailing number on the one right axis (Num col 1)', () => {
    renderGroup()
    for (const id of ['s1', 's2', 's3']) {
      const cell = screen.getByTestId(`session-age-${id}`).firstElementChild!
      expect(cell.className).toContain('w-[var(--num-col-1)]')
      expect(cell.className).toContain('text-right')
    }
    // The group label's own count sits on the same edge as the rows' ages.
    const label = screen.getByText('Today').closest('button')!
    expect(label.className).toContain('pr-8')
    expect(label.querySelector('[class*="--num-col-1"]')).toBeTruthy()
    // The row's text column stops on that same edge, so the ⋯ box never sits on it.
    const rowButton = screen.getByTestId('session-row-s1').querySelector('button[title]')!
    expect(rowButton.className).toContain('pr-8')
  })

  it('keeps the tree glyphs on the same step as the title they indent', () => {
    const { container } = renderGroup()
    const connector = screen.getByTestId('session-connector-s2')
    expect(connector.className).toContain('text-scale-ui')
    const rail = container.querySelector('[data-testid="session-row-s2"] span[aria-hidden="true"]')!
    expect(rail.className).toContain('text-scale-ui')
  })

  it('carries the accent on the running row only, never on a selected one', () => {
    const { container, unmount } = renderGroup({
      activeSessionId: 's1',
      runningSessionId: 's3',
    })
    const accented = [...container.querySelectorAll('.text-brand-deep')]
    expect(accented).toHaveLength(1)
    // The one accent in the list sits on the running row's own count.
    expect(screen.getByTestId('session-row-s3').contains(accented[0]!)).toBe(true)
    expect(accented[0]!.textContent).toContain('2 messages')
    const nowRules = [...container.querySelectorAll('.bg-brand')]
    expect(nowRules).toHaveLength(1)
    expect(screen.getByTestId('session-row-s3').contains(nowRules[0]!)).toBe(true)
    // The selected row marks itself in hairline-strong, an ink line, no accent.
    const selRule = screen.getByTestId('session-row-s1').querySelector('.bg-hairline-strong')
    expect(selRule).toBeTruthy()
    unmount()
  })

  it('shows no accent at all when nothing runs', () => {
    const { container } = renderGroup({ activeSessionId: 's1' })
    expect(container.querySelectorAll('.text-brand-deep')).toHaveLength(0)
    expect(container.querySelectorAll('.bg-brand')).toHaveLength(0)
  })

  it('reads the unread state in type, without a painted dot', () => {
    renderGroup()
    const mark = screen.getByTestId('session-unread-dot-s3')
    expect(mark.className).toContain('sr-only')
    expect(mark.className).not.toContain('rounded-full')
    expect(screen.getByText('Report the mutation catch').className).toContain('text-ink')
  })

  it('keeps the label at the data step in caps, with its count in the number column', () => {
    renderGroup()
    const label = screen.getByText('Today').closest('button')!
    expect(label.className).toContain('text-scale-data')
    expect(label.className).toContain('font-mono')
    expect(label.className).toContain('uppercase')
  })
})
