/**
 * W10 group 8 — the phone shell at 390 px: the touch floor and the two shell
 * exits that had no path.
 *
 * GIVEN the sidebar rendered at phone width
 * WHEN a named control is inspected, "New task" is picked, or "Report issue" is chosen
 * THEN every named control carries the 24 px floor class, the pick closes the
 *      drawer, and the link leaves through the shell bridge.
 *
 * The "24 px floor" above is the desktop glyph floor (`lg:min-h-6`). Below lg the
 * phone floor is 44 px (`max-lg:min-h-11`), the number WD-29 set for the composer and
 * the rest of the app follows; the view toggles carried `max-lg:min-h-6` — the
 * desktop value behind a phone prefix — until the 390 px measurement at
 * `tests/playwright/mobile-viewport.spec.ts` caught them at 24 px.
 *
 * jsdom has no layout, so this file pins the class contract. The real box in
 * px is measured by e2e/walkthrough/persona-07-handy.spec.ts at 390 x 844.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

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
const { openExternally } = vi.hoisted(() => ({ openExternally: vi.fn(async () => {}) }))
vi.mock('@/lib/nativeBrowser', () => ({ openExternally }))

import Sidebar from './Sidebar'
import { useChatStore } from '@/store/chatStore'

const ISSUES = 'https://github.com/bemlerlabs/ephe/issues'

function renderSidebar(): ReturnType<typeof vi.fn> {
  const onClose = vi.fn()
  render(
    <Sidebar
      isOpen
      onClose={onClose}
      collapsed={false}
      onToggleCollapsed={() => {}}
      onOpenSettings={vi.fn()}
    />,
  )
  return onClose
}

/** A viewport wider than lg, so the column is permanent instead of a drawer. */
function stubDesktopViewport(): void {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('min-width: 1024px'),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

beforeEach(() => {
  localStorage.clear()
  openExternally.mockClear()
  useChatStore.setState({
    sessions: [{ id: 's1', title: 'Alpha', createdAt: 0, messages: [] }],
    activeSessionId: 's1',
    currentSession: { id: 's1', title: 'Alpha', createdAt: 0, messages: [] },
    checkpoints: {},
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('Sidebar touch floor at 390 px (W10 g8)', () => {
  it('the session trigger is visible at rest and carries the 24 px floor', async () => {
    renderSidebar()
    const trigger = await screen.findByTestId('session-menu-s1')
    // The finding: 22x22 px and opacity-0 until hover. Both are the same edit.
    expect(trigger.className).not.toContain('opacity-0')
    expect(trigger.className).toContain('min-w-6')
    expect(trigger.className).toContain('min-h-6')
  })

  it('the Group and Project toggles carry the phone floor class', async () => {
    renderSidebar()
    const group = await screen.findByTestId('sidebar-view-group-active')
    // 44 px below lg, the floor the composer set in WD-29 and the rest of the app
    // follows; `max-lg:min-h-6` was the same 24 px as the desktop case and bought
    // the phone nothing.
    expect(group.className).toContain('max-lg:min-h-11')

    const project = screen.getByText('sidebar.viewProject').closest('button')
    expect(project).not.toBeNull()
    expect(project!.className).toContain('max-lg:min-h-11')
  })

  it('the filter popover carries the phone floor on all eight controls', async () => {
    renderSidebar()
    fireEvent.click(await screen.findByTestId('sidebar-filter-toggle'))
    // The popover holds the same eight controls the desktop test names, so it carries
    // the same phone floor; `lg:min-h-6` alone left five of them at 22-24 px at 390.
    for (const id of [
      'sidebar-filter-order-updated',
      'sidebar-filter-order-created',
      'sidebar-filter-pinned',
      'sidebar-filter-unread',
      'sidebar-filter-archived',
      'sidebar-filter-collapse-all',
      'sidebar-filter-reset',
      'sidebar-filter-mark-read',
    ]) {
      expect(screen.getByTestId(id).className, id).toContain('max-lg:min-h-11')
    }
  })

  it('picking New task closes the phone drawer', () => {
    const onClose = renderSidebar()
    fireEvent.click(screen.getByTestId('new-session'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('the desktop column stays when New task is picked', () => {
    stubDesktopViewport()
    const onClose = renderSidebar()
    fireEvent.click(screen.getByTestId('new-session'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('Report issue leaves through the shell bridge, not a raw window.open', async () => {
    const raw = vi.spyOn(window, 'open').mockImplementation(() => null)
    renderSidebar()
    fireEvent.click(await screen.findByTestId('session-menu-s1'))
    fireEvent.click(screen.getByTestId('menu-report-issue'))
    expect(openExternally).toHaveBeenCalledWith(ISSUES)
    expect(raw).not.toHaveBeenCalled()
  })
})

/* The same floor at the other end of the shell. The 2026-10-12 wave guarded the
   phone with `max-lg:min-h-6`; at 1440 px the same controls stayed below 24 px,
   which is where the desktop pointer lives. Measured at 1440 px before this
   edit: Group/Project 22 px, the filter rows 18-22 px, the search clear button
   12x12, the delete-confirm pair 18 px, the fold toggle 16x16 (`lg:` = 1024 px).
   Measured at 390 px after it: Group/Project 24 px, the search field 26 px at an
   11 px font — the phone half needed the 44 px floor too, and `max-lg:min-h-11`
   is where it lives now. */

const FLOOR_H = ['min-h-6', 'lg:min-h-6']
const FLOOR_W = ['min-w-6', 'lg:min-w-6']

function ownTokens(el: Element | null): string[] {
  if (!el) return []
  return String((el as HTMLElement).className ?? '')
    .split(/\s+/)
    .filter(Boolean)
}

/** Exact token match: `max-lg:min-h-6` must not answer for the desktop floor. */
function expectToken(el: Element | null, tokens: string[]): void {
  expect(el, 'the control is rendered').not.toBeNull()
  const own = ownTokens(el)
  expect(
    tokens.some((want) => own.includes(want)),
    `[${own.join(' ')}] carries none of ${tokens.join(' | ')}`,
  ).toBe(true)
}

/** Desktop-effective h-<size> of every glyph under `root`; a row may not mix two.
 *  An `lg:` token wins over the bare one, since this file reads the desktop case. */
function glyphHeights(root: Element | null): string[] {
  const size = (el: SVGElement): string => {
    const cls = ` ${el.getAttribute('class') ?? ''} `
    const at = /(?:^|\s)lg:h-([\d.]+)(?=\s|$)/.exec(cls) ?? /(?:^|\s)h-([\d.]+)(?=\s|$)/.exec(cls)
    return at?.[1] ?? '?'
  }
  return [...(root?.querySelectorAll('svg') ?? [])].map(size)
}

function expectOneGlyph(root: Element | null, size: string, what: string): void {
  const sizes = glyphHeights(root)
  const distinct = [...new Set(sizes)]
  expect(sizes.length, `${what} carries a glyph`).toBeGreaterThan(0)
  expect(distinct, `${what} mixes ${distinct.join('/')}`).toHaveLength(1)
  expect(distinct[0], `${what} glyph size`).toBe(size)
}

describe('Sidebar desktop floor at 1440 px (W13)', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessions: [
        {
          id: 'r1',
          title: 'Alpha',
          createdAt: 1,
          messages: [{ id: 'm1', role: 'user', content: 'a', timestamp: 1 }],
        },
        {
          id: 'c1',
          title: 'Zweig',
          createdAt: 2,
          parentId: 'r1',
          messages: [{ id: 'm2', role: 'user', content: 'b', timestamp: 2 }],
        },
      ],
      activeSessionId: 'r1',
      currentSession: null,
      checkpoints: {},
    })
  })

  it('every control keeps 24x24 at desktop width', async () => {
    stubDesktopViewport()
    renderSidebar()

    const group = await screen.findByTestId('sidebar-view-group-active')
    expectToken(group, FLOOR_H)
    expectToken(screen.getByText('sidebar.viewProject').closest('button'), FLOOR_H)

    const filterToggle = screen.getByTestId('sidebar-filter-toggle')
    expectToken(filterToggle, FLOOR_H)
    expectToken(filterToggle, FLOOR_W)

    fireEvent.click(filterToggle)
    for (const id of [
      'sidebar-filter-order-updated',
      'sidebar-filter-order-created',
      'sidebar-filter-pinned',
      'sidebar-filter-unread',
      'sidebar-filter-archived',
      'sidebar-filter-collapse-all',
      'sidebar-filter-reset',
      'sidebar-filter-mark-read',
    ]) {
      expectToken(screen.getByTestId(id), FLOOR_H)
    }

    const menuTrigger = screen.getByTestId('session-menu-r1')
    expectToken(menuTrigger, FLOOR_H)
    expectToken(menuTrigger, FLOOR_W)

    const fold = screen.getByTestId('session-fold-r1')
    expectToken(fold, FLOOR_H)
    expectToken(fold, FLOOR_W)

    fireEvent.click(menuTrigger)
    fireEvent.click(screen.getByTestId('menu-delete'))
    expectToken(screen.getByText('sidebar.deleteAction').closest('button'), FLOOR_H)
    expectToken(screen.getByText('sidebar.deleteCancel').closest('button'), FLOOR_H)

    // last: typing a query narrows the list, so the tree rows above have to be
    // read before it
    const input = screen.getByPlaceholderText('sidebar.searchPlaceholder')
    fireEvent.change(input, { target: { value: 'al' } })
    const clear = input.parentElement?.querySelector('button') ?? null
    expectToken(clear, FLOOR_H)
    expectToken(clear, FLOOR_W)
  })

  it('a row keeps one glyph size at desktop width', async () => {
    stubDesktopViewport()
    renderSidebar()

    expectOneGlyph(await screen.findByTestId('session-row-r1'), '3', 'the session row')
    expectOneGlyph(screen.getByTestId('sidebar-view-toggle').parentElement, '3', 'the view row')

    const input = screen.getByPlaceholderText('sidebar.searchPlaceholder')
    fireEvent.change(input, { target: { value: 'al' } })
    expectOneGlyph(input.parentElement, '3.5', 'the search row')
  })
})
