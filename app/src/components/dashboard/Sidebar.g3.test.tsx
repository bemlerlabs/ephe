import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Sidebar from './Sidebar'
import {
  OPEN_TIERS_KEY,
  SIDEBAR_ACTION_TIERS,
  SIDEBAR_ACTION_ENTRY_IDS,
} from './sidebarActionGroups'

/**
 * Round-G3 (2026-09-07, reference parity): the left rail's action rows — "New task" (⌘N),
 * "Search" (⌘K), "Automations", "Skills", … — plus the Group/Project toggle and the tasks
 * section. Rewritten for register #71, where the owner called the flat list overloaded.
 *
 * The old assertions asked `getByTestId('sidebar-action-…')` of every row in turn, which is as
 * true of a row in a closed, hidden tier (jsdom keeps it in the document) — the file read the
 * same flat or grouped. It now pins which tier holds which row (the literal table), that a tier
 * holds exactly the rows the ONE list names, that closing hides without unmounting, and that
 * the open/closed state survives a reload.
 */

const storeMocks = vi.hoisted(() => ({
  togglePin: vi.fn(),
  createSession: vi.fn(),
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
  listProjects: vi.fn(async () => ({ projects: [{ name: 'ephe', path: '/tmp/ephe' }] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  updateSettings: vi.fn(async () => ({})),
  getSettings: vi.fn(async () => ({ workspace_dir: null, approval_profile: 'strict' })),
  getTasks: vi.fn(async () => [
    { id: 't1', title: 'Regression testen', status: 'pending', project: null },
    { id: 't2', title: 'Changelog schreiben', status: 'done', project: null },
  ]),
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
    sessions: storeMocks.sessions,
    activeSessionId: storeMocks.activeSessionId,
    setActiveSession: vi.fn(),
    createSession: storeMocks.createSession,
    deleteSession: vi.fn(),
    renameSession: vi.fn(),
    togglePin: storeMocks.togglePin,
  }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }))

vi.mock('@/lib/api', () => ({
  listProjects: apiMocks.listProjects,
  listSchedules: apiMocks.listSchedules,
  updateSettings: apiMocks.updateSettings,
  getTasks: apiMocks.getTasks,
  getSettings: apiMocks.getSettings,
  searchSessions: apiMocks.searchSessions,
  exportChatMarkdown: apiMocks.exportChatMarkdown,
  downloadTextFile: apiMocks.downloadTextFile,
}))

/**
 * The tiers as the owner named them, written out. Deliberately a literal: the
 * ONE list in sidebarActionGroups.ts can only tell us that nothing was dropped,
 * never that a row sits in the right tier — that part has to be read here.
 */
const TIERS: Record<string, string[]> = {
  // "New Task + aktuelle Tasks/Steps" — headless, always open.
  primary: ['sidebar-action-search', 'sidebar-action-tasks'],
  // "Tools & Capabilities" — collapsible.
  tools: [
    'sidebar-action-skills',
    'sidebar-action-tools',
    'sidebar-action-helpers',
    'sidebar-action-agents',
    'sidebar-action-marketplace',
    'sidebar-action-files',
    'sidebar-action-workspaces',
  ],
  // "More surfaces" — collapsible, four named rows instead of one catch-all.
  more: [
    'sidebar-action-knowledge',
    'sidebar-action-library',
    'sidebar-action-artifacts',
    'sidebar-action-automations',
    'sidebar-action-connectors',
  ],
}

const ALL_ROWS: string[] = []
for (const rows of Object.values(TIERS)) ALL_ROWS.push(...rows)

function rowTestIdsOf(tier: string): string[] {
  const container = screen.getByTestId(`sidebar-tier-${tier}`)
  return [...container.querySelectorAll<HTMLElement>('[data-testid^="sidebar-action-"]')].map(
    (el) => el.getAttribute('data-testid') ?? '',
  )
}

function mount(onOpenSettings = vi.fn()) {
  return render(
    <Sidebar
      isOpen={false}
      onClose={vi.fn()}
      onOpenSettings={onOpenSettings}
      collapsed={false}
      onToggleCollapsed={vi.fn()}
    />,
  )
}

describe('Sidebar Aktionszeilen + Ansichtsumschalter (Runden-G3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  describe('#71: the three tiers', () => {
    it('every row stands in its tier — primary first, then tools, then the rest', async () => {
      mount()
      await screen.findByTestId('sidebar-actions')

      for (const [tier, rows] of Object.entries(TIERS)) {
        expect(rowTestIdsOf(tier), `tier ${tier}`).toEqual(rows)
      }

      // The tiers stand in the owner's order, top to bottom, and there is no
      // fourth, unlabelled place a row could hide in.
      const tiersInDom = [...screen.getByTestId('sidebar-actions').children].map((el) =>
        el.getAttribute('data-tier'),
      )
      expect(tiersInDom).toEqual(Object.keys(TIERS))
      for (const [tier, rows] of Object.entries(TIERS)) {
        for (const row of rows) {
          expect(screen.getByTestId(row).getAttribute('data-tier'), row).toBe(tier)
        }
      }
    })

    it('no row was lost on the way into a tier: thirteen before, thirteen after', async () => {
      mount()
      await screen.findByTestId('sidebar-actions')

      // Completeness read off the ONE list: one rendered row per entry id, in
      // display order — a dropped row fails here even if the table above is
      // edited to match, because the table's union is compared to the list.
      expect(SIDEBAR_ACTION_ENTRY_IDS).toHaveLength(ALL_ROWS.length)
      expect(SIDEBAR_ACTION_TIERS.flatMap((t) => t.entries)).toHaveLength(ALL_ROWS.length)

      const ids = ALL_ROWS.map((t) => screen.getByTestId(t).getAttribute('data-testid'))
      expect(new Set(ids).size).toBe(ALL_ROWS.length)
    })

    it('the primary tier carries no head and cannot be closed', async () => {
      mount()
      await screen.findByTestId('sidebar-tier-primary')

      expect(screen.queryByTestId('sidebar-tier-primary-toggle')).toBeNull()
      for (const row of TIERS.primary!) {
        expect(screen.getByTestId(row)).toBeVisible()
      }
      // It is the tier the pill sits directly above.
      const pill = screen.getByTestId('new-session')
      expect(pill.textContent).toContain('⌘N')
      expect(pill.compareDocumentPosition(screen.getByTestId('sidebar-action-search'))).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      )
      expect(screen.queryByTestId('sidebar-action-new')).toBeNull()
    })

    it('a fresh sidebar opens closed — what is primary is what you see', async () => {
      mount()
      await screen.findByTestId('sidebar-tier-tools')

      for (const tier of ['tools', 'more']) {
        expect(
          screen.getByTestId(`sidebar-tier-${tier}-toggle`).getAttribute('aria-expanded'),
        ).toBe('false')
        expect(screen.getByTestId(`sidebar-tier-${tier}-rows`)).toHaveAttribute('hidden')
      }
      // The heads keep the member count, so a closed tier still says what is in it.
      expect(screen.getByTestId('sidebar-tier-tools-count').textContent).toBe('7')
      expect(screen.getByTestId('sidebar-tier-more-count').textContent).toBe('5')
    })

    it('closing a tier hides its rows without unmounting them', async () => {
      mount()
      const toggle = await screen.findByTestId('sidebar-tier-tools-toggle')
      const rows = screen.getByTestId('sidebar-tier-tools-rows')
      const firstRow = screen.getByTestId(TIERS.tools![0]!)

      fireEvent.click(toggle)
      expect(toggle.getAttribute('aria-expanded')).toBe('true')
      expect(rows).not.toHaveAttribute('hidden')
      expect(firstRow).toBeVisible()

      fireEvent.click(toggle)
      expect(toggle.getAttribute('aria-expanded')).toBe('false')
      expect(rows).toHaveAttribute('hidden')
      // Still in the document — a closed tier is only hidden, so the rows keep
      // their state and the testids stay findable.
      expect(firstRow).toBeInTheDocument()
      expect(firstRow).not.toBeVisible()
      for (const row of TIERS.tools!) {
        expect(screen.getByTestId(row)).not.toBeVisible()
      }
      // …and the other tier is untouched by it.
      expect(screen.getByTestId(TIERS.more![0]!)).not.toBeVisible()
      expect(screen.getByTestId('sidebar-tier-more-toggle').getAttribute('aria-expanded')).toBe(
        'false',
      )
    })

    it('remembers what was opened — the state survives a reload', async () => {
      const first = mount()
      fireEvent.click(await screen.findByTestId('sidebar-tier-tools-toggle'))
      expect(JSON.parse(localStorage.getItem(OPEN_TIERS_KEY)!)).toEqual({
        tools: true,
        more: false,
      })
      first.unmount()

      // The reload: same storage, new sidebar.
      mount()
      expect(screen.getByTestId('sidebar-tier-tools-toggle').getAttribute('aria-expanded')).toBe(
        'true',
      )
      expect(screen.getByTestId(TIERS.tools![0]!)).toBeVisible()
      expect(screen.getByTestId(TIERS.more![0]!)).not.toBeVisible()
    })

    it('a torn value falls back to first run instead of breaking the sidebar', async () => {
      localStorage.setItem(OPEN_TIERS_KEY, '{not json')
      mount()
      expect(await screen.findByTestId('sidebar-tier-tools-toggle')).toBeTruthy()
      expect(screen.getByTestId('sidebar-tier-tools-rows')).toHaveAttribute('hidden')
    })

    it('the nav island scrolls instead of eating the task list', async () => {
      mount()
      const island = await screen.findByTestId('sidebar-actions')
      // Measured 2026-10-14 on the 288x800 column: with both tiers open the
      // island wants 503px; uncapped the aside clipped the rows past the fold
      // and the task list below collapsed to 8px. Capped, it scrolls.
      expect(island.className).toContain('max-h-[45vh]')
      expect(island.className).toContain('overflow-y-auto')
    })

    it('the head is a phone-sized target and says what it is', async () => {
      mount()
      const toggle = await screen.findByTestId('sidebar-tier-tools-toggle')
      // W10 g8's phone floor, the same class the other drawer controls carry.
      expect(toggle.className).toContain('max-lg:min-h-11')
      expect(toggle.getAttribute('title')).toBe('sidebar.groupTools')
      // The name a screen reader reads is the visible head text; the count is decoration.
      expect(toggle.textContent).toContain('sidebar.groupTools')
      expect(toggle.getAttribute('aria-controls')).toBe(
        screen.getByTestId('sidebar-tier-tools-rows').id,
      )
    })
  })

  describe('what the rows do', () => {
    it('Search keeps ⌘K; the New-task pill creates a session and stays the only way in', async () => {
      mount()
      await screen.findByTestId('sidebar-actions')
      expect(screen.getByTestId('sidebar-action-search').textContent).toContain('⌘K')
      expect(screen.queryByTestId('sidebar-action-kanban')).toBeNull()

      fireEvent.click(screen.getByTestId('new-session'))
      expect(storeMocks.createSession).toHaveBeenCalledTimes(1)

      const seen: KeyboardEvent[] = []
      const catcher = (e: KeyboardEvent) => seen.push(e)
      window.addEventListener('keydown', catcher)
      try {
        fireEvent.click(screen.getByTestId('sidebar-action-search'))
      } finally {
        window.removeEventListener('keydown', catcher)
      }
      const toggle = seen.find((e) => (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')
      expect(toggle).toBeTruthy()
    })

    it('a row in a closed tier is only reachable once the tier is open', async () => {
      const onOpenSettings = vi.fn()
      mount(onOpenSettings)
      // "Automations" lives in the third tier — closed on first run.
      expect(screen.getByTestId('sidebar-action-automations')).not.toBeVisible()
      fireEvent.click(await screen.findByTestId('sidebar-tier-more-toggle'))
      expect(screen.getByTestId('sidebar-action-automations')).toBeVisible()

      fireEvent.click(screen.getByTestId('sidebar-action-automations'))
      expect(onOpenSettings).toHaveBeenCalledWith('cron')
    })

    it('Capabilities lands on the capability group of the settings panel', async () => {
      const onOpenSettings = vi.fn()
      mount(onOpenSettings)
      // Plugins, MCP servers and skills are three sections of the settings panel; the
      // skills section is the installed list that carries a provenance mark per row. The
      // row used to call the handler with no argument, which opens the panel's default
      // tab — the engine's own section.
      fireEvent.click(await screen.findByTestId('sidebar-tier-tools-toggle'))
      fireEvent.click(screen.getByTestId('sidebar-action-skills'))
      expect(onOpenSettings).toHaveBeenCalledWith('skills')
    })

    it('Tasks opens the steps page in the settings; Library the library rail', async () => {
      const onOpenSettings = vi.fn()
      mount(onOpenSettings)
      // The steps ledger's one surface is its page in the settings: the panel tab that drew a
      // second step list beside the plan card is gone, so this row lands where the automations
      // row lands — on the page.
      fireEvent.click(await screen.findByTestId('sidebar-action-tasks'))
      expect(onOpenSettings).toHaveBeenCalledWith('tasks')

      fireEvent.click(screen.getByTestId('sidebar-tier-more-toggle'))
      const libSeen: string[] = []
      const libCatcher = (e: Event) => libSeen.push(e.type)
      window.addEventListener('ephe:library-open', libCatcher)
      try {
        fireEvent.click(screen.getByTestId('sidebar-action-library'))
      } finally {
        window.removeEventListener('ephe:library-open', libCatcher)
      }
      expect(libSeen).toContain('ephe:library-open')
    })
  })

  it('Group/Project-Umschalter: Project-Ansicht zeigt die Projects-Sektion dauerhaft', async () => {
    const { container } = mount()
    const toggleGroup = await screen.findByTestId('sidebar-view-toggle')
    const projectBtnInit = toggleGroup.querySelector<HTMLButtonElement>(
      'button[aria-pressed="false"]',
    )!
    fireEvent.click(projectBtnInit)
    const active = await screen.findByTestId('sidebar-view-project-active')
    expect(active).toBeTruthy()
    // Project view: the projects section stays visible once loading has finished
    expect(await screen.findByTestId('sidebar-projects')).toBeTruthy()
    // and toggling back to Group works (the button that is now false is Group)
    const groupBtn = container.querySelector<HTMLButtonElement>(
      '[data-testid="sidebar-view-toggle"] button[aria-pressed="false"]',
    )!
    fireEvent.click(groupBtn)
    expect(await screen.findByTestId('sidebar-view-group-active')).toBeTruthy()
  })

  it('Tasks-Sektion listet offene Aufgaben und klickt auf die Schritte-Seite der Settings', async () => {
    const onOpenSettings = vi.fn()
    mount(onOpenSettings)
    const row = await screen.findByTestId('sidebar-task-row-t1')
    expect(row.textContent).toContain('Regression testen')
    // done tasks do not belong in the open section
    expect(screen.queryByTestId('sidebar-task-row-t2')).toBeNull()
    fireEvent.click(row)
    expect(onOpenSettings).toHaveBeenCalledWith('tasks')
  })
})
