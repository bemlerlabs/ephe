import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT, PANEL_STATE_EVENT } from '@/lib/panelEvents'

// Round-G parity (2026-09-07): the side pane carries real multi-tabs like
// the reference — opened pills with a close button, a +-menu with search,
// "Opened tabs" and "Recently closed tabs" (restoration), and an
// empty state with opening cards when all tabs are closed.

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
  runShell: vi.fn(async () => ({ output: '' })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  listFs: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'proj', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
}))

// P1-5: the terminal tab defaults to Live (xterm.js) — it needs canvas/WebSocket,
// irrelevant for the tab inventory here; mocked as a stub.
vi.mock('./agent/LiveTerminal', () => ({ default: () => <div data-testid="live-terminal" /> }))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

function openPane() {
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
}
function openTabViaEvent(tab: string) {
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
}
function setPersistedTabs(tabs: string[]) {
  localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs))
}

// The replay tab links to the workbench (R4 A3 backwards) — as in the real
// window, the pane therefore needs a router.
const renderPanel = () =>
  render(
    <MemoryRouter>
      <AgentPanel />
    </MemoryRouter>,
  )

describe('AgentPanel Multi-Tabs (Runden-G, Referenz-Paritaet)', () => {
  beforeEach(() => {
    localStorage.clear()
    // jsdom does not ship matchMedia/ResizeObserver — the open panel path
    // (frost pulse, dock measurement) needs them.
    if (!window.matchMedia) {
      window.matchMedia = vi.fn(() => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      })) as unknown as typeof window.matchMedia
    }
    if (!globalThis.ResizeObserver) {
      globalThis.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
      } as unknown as typeof globalThis.ResizeObserver
    }
  })

  it('alle Tabs geschlossen -> Leerzustand mit Offnen-Karten fuer jede Pane-Seite', async () => {
    setPersistedTabs([])
    renderPanel()
    openPane()
    expect(await screen.findByTestId('panel-empty-state')).toBeTruthy()
    expect(screen.getByText('agentPanel.openTabTitle')).toBeTruthy()
    expect(screen.getByText('agentPanel.openTabHint')).toBeTruthy()
    for (const key of ['preview', 'terminal', 'git', 'files', 'audit']) {
      expect(screen.getByTestId(`panel-tab-card-${key}`)).toBeTruthy()
    }
  })

  it('Karte oeffnet den Tab als aktive Pille (role=tab, aria-selected)', async () => {
    setPersistedTabs([])
    renderPanel()
    openPane()
    fireEvent.click(await screen.findByTestId('panel-tab-card-terminal'))
    const tab = (await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })) as HTMLElement
    expect(tab.getAttribute('aria-selected')).toBe('true')
  })

  it('Pille hat einen Schliesser; letzte zu -> wieder der Leerzustand', async () => {
    setPersistedTabs(['terminal'])
    renderPanel()
    openPane()
    await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })
    fireEvent.click(screen.getByTestId('panel-tab-close-terminal'))
    expect(await screen.findByTestId('panel-empty-state')).toBeTruthy()
    expect(screen.queryByRole('tab', { name: 'agentPanel.tabTerminal' })).toBeNull()
  })

  it('+-Menue zeigt "Zuletzt geschlossen" und stellt den Tab wieder her', async () => {
    setPersistedTabs(['terminal'])
    renderPanel()
    openPane()
    await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })
    fireEvent.click(screen.getByTestId('panel-tab-close-terminal'))
    await screen.findByTestId('panel-empty-state')
    fireEvent.click(screen.getByTestId('panel-add-tab'))
    expect(await screen.findByText('agentPanel.closedTabsSection')).toBeTruthy()
    fireEvent.click(screen.getByTestId('panel-recent-terminal'))
    const tab = (await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })) as HTMLElement
    expect(tab.getAttribute('aria-selected')).toBe('true')
  })

  it('zuletzt geschlossene Tabs werden unter "Zuletzt geschlossen" angeboten', async () => {
    setPersistedTabs(['terminal'])
    renderPanel()
    openPane()
    await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })
    fireEvent.click(screen.getByTestId('panel-tab-close-terminal'))
    await screen.findByTestId('panel-empty-state')
    fireEvent.click(screen.getByTestId('panel-add-tab'))
    const menu = screen.getByTestId('panel-add-menu')
    // P6 B5: the four menu keys are fixed, the search only filters — the recently
    // closed tab lives in its own "Recently closed" section.
    expect(await within(menu).findByTestId('panel-recent-terminal')).toBeTruthy()
    expect(await within(menu).findByTestId('panel-new-tab-item-terminal')).toBeTruthy()
  })

  it('Klick auf eine "Geoeffnete"-Row wechselt den Tab UND schliesst das Menue', async () => {
    setPersistedTabs(['terminal', 'git'])
    renderPanel()
    openPane()
    await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })
    fireEvent.click(screen.getByTestId('panel-add-tab'))
    fireEvent.click(await screen.findByTestId('panel-open-tab-row-git'))
    expect(
      (await screen.findByRole('tab', { name: 'agentPanel.tabGit' })).getAttribute('aria-selected'),
    ).toBe('true')
    expect(screen.queryByTestId('panel-add-menu')).toBeNull()
  })

  it('PANEL_STATE_EVENT broadcastet das geoeffnete-Tab-Inventur mit', async () => {
    setPersistedTabs([])
    const seen: { tabs?: unknown; tab?: unknown; open?: boolean }[] = []
    const listener = (e: Event) => seen.push((e as CustomEvent).detail ?? {})
    window.addEventListener(PANEL_STATE_EVENT, listener)
    try {
      renderPanel()
      openTabViaEvent('terminal')
      await screen.findByRole('tab', { name: 'agentPanel.tabTerminal' })
      openTabViaEvent('git')
      await screen.findByRole('tab', { name: 'agentPanel.tabGit' })
      // `findByRole` resolves when the pill renders; the broadcast rides a later
      // effect flush, so reading `seen[last]` on the next line races it — observed
      // red under load, green in 9 of 9 light runs. Being a load-sensitive read of
      // the *last* event is the whole defect: awaiting the event makes the same
      // three assertions strict instead of lucky. The expectation is unchanged.
      await vi.waitFor(() => {
        const last = seen[seen.length - 1]!
        expect(last.open).toBe(true)
        expect(last.tab).toBe('git')
        expect(last.tabs).toEqual(expect.arrayContaining(['terminal', 'git']))
      })
    } finally {
      window.removeEventListener(PANEL_STATE_EVENT, listener)
    }
  })

  it('Collapse-Chevron klappt das Pane zu, Tabs bleiben erhaelt en', async () => {
    setPersistedTabs(['git'])
    const { container } = renderPanel()
    openPane()
    await screen.findByRole('tab', { name: 'agentPanel.tabGit' })
    fireEvent.click(screen.getByTestId('panel-collapse-pane'))
    await vi.waitFor(() => expect(container.textContent).toBe(''))
    openPane()
    // The tabs are still open after reopening (persistence across the session)
    expect(await screen.findByRole('tab', { name: 'agentPanel.tabGit' })).toBeTruthy()
  })

  it('Erstutzung ohne Persistierung oeffnet das Pane mit dem Vorschau-Tab', async () => {
    renderPanel()
    openPane()
    const tab = (await screen.findByRole('tab', { name: 'agentPanel.tabPreview' })) as HTMLElement
    expect(tab.getAttribute('aria-selected')).toBe('true')
    // No empty state when a default tab is open
    expect(screen.queryByTestId('panel-empty-state')).toBeNull()
    // The +-button is always reachable (open more pages)
    expect(screen.getByTestId('panel-add-tab')).toBeTruthy()
  })

  it('+-Menue filtert die Suche; Angebot sind alle zehn Pane-Seiten (P4)', async () => {
    setPersistedTabs(['preview'])
    renderPanel()
    openPane()
    fireEvent.click(await screen.findByTestId('panel-add-tab'))
    const search = (await screen.findByTestId('panel-tab-search')) as HTMLInputElement
    // P6 B5: the four main accesses stay a fixed contract (side/review/
    // terminal/browser). P4 finding 1: the remaining pages are additionally there as
    // their own rows — the search filters both groups.
    fireEvent.change(search, { target: { value: 'brows' } })
    const menu = screen.getByTestId('panel-add-menu')
    expect(await within(menu).findByTestId('panel-new-tab-item-browser')).toBeTruthy()
    expect(within(menu).queryByTestId('panel-new-tab-item-terminal')).toBeNull()
    fireEvent.change(search, { target: { value: '' } })
    for (const tab of ['files', 'audit', 'trajectory', 'subagents', 'memory']) {
      expect(within(menu).getByTestId(`panel-page-item-${tab}`)).toBeTruthy()
    }
    // Hits without a match show the empty hint.
    fireEvent.change(search, { target: { value: 'zzzz' } })
    expect(await within(menu).findByText('agentPanel.noTabMatches')).toBeTruthy()
  })

  // WP5: the key 'audit' hung on the trajectory replay, while the
  // real proof list was never to be seen in the product. Both paths are their own
  // tabs — this test fails as soon as one disappears under the other again.
  it("'audit' haengt an der Nachweisliste, 'trajectory' an der Wiedergabe", async () => {
    setPersistedTabs(['audit', 'trajectory'])
    renderPanel()
    openPane()
    fireEvent.click(await screen.findByRole('tab', { name: 'agentPanel.tabAudit' }))
    expect(await screen.findByRole('group', { name: 'agentPanel.auditFilter' })).toBeTruthy()
    expect(screen.queryByTestId('trajectory-view')).toBeNull()
    fireEvent.click(await screen.findByRole('tab', { name: 'agentPanel.tabTrajectory' }))
    expect(await screen.findByTestId('trajectory-view')).toBeTruthy()
    expect(screen.queryByRole('group', { name: 'agentPanel.auditFilter' })).toBeNull()
  })

  // R2 §4.4 (point 3): the role sat on a div that had a focusable button
  // as its child; role=tabpanel/aria-controls did not occur a single time in the whole
  // agent/ folder and every pill was tabbable. These three tests hold the
  // corrected relationship: pill (button[role=tab]) -> panel id -> aria-labelledby
  // back, roving tabindex and arrow keys.
  it('tablist: die Pille traegt die Rolle und zeigt per aria-controls aufs Panel', async () => {
    setPersistedTabs(['preview', 'git'])
    renderPanel()
    openPane()
    const tab = (await screen.findByRole('tab', {
      name: 'agentPanel.tabPreview',
    })) as HTMLElement
    // The clickable element carrier IS the role — no wrapping div anymore.
    expect(tab.tagName).toBe('BUTTON')
    expect(tab.closest('[role="tablist"]')).toBeTruthy()
    expect(tab.getAttribute('aria-selected')).toBe('true')

    const panel = screen.getByRole('tabpanel')
    expect(tab.getAttribute('aria-controls')).toBe(panel.id)
    expect(panel.id).toBeTruthy()
    expect(panel.getAttribute('aria-labelledby')).toBe(tab.id)
    // The panel is the content carrier, not the tab bar itself.
    expect(await within(panel).findByTestId('preview-url-input')).toBeTruthy()
    // Only the active pill points at a panel — no dangling reference.
    const inactive = (await screen.findByRole('tab', { name: 'agentPanel.tabGit' })) as HTMLElement
    expect(inactive.hasAttribute('aria-controls')).toBe(false)
  })

  it('Roving-Tabindex: nur die aktive Pille ist tabbar', async () => {
    setPersistedTabs(['preview', 'git'])
    renderPanel()
    openPane()
    const preview = (await screen.findByRole('tab', {
      name: 'agentPanel.tabPreview',
    })) as HTMLElement
    const git = (await screen.findByRole('tab', { name: 'agentPanel.tabGit' })) as HTMLElement
    expect(preview.tabIndex).toBe(0)
    expect(git.tabIndex).toBe(-1)
  })

  it('Pfeiltasten bewegen die aktive Pille und ziehen den Fokus nach', async () => {
    setPersistedTabs(['preview', 'git'])
    renderPanel()
    openPane()
    const preview = (await screen.findByRole('tab', {
      name: 'agentPanel.tabPreview',
    })) as HTMLElement
    const git = (await screen.findByRole('tab', { name: 'agentPanel.tabGit' })) as HTMLElement

    preview.focus()
    fireEvent.keyDown(preview, { key: 'ArrowRight' })
    expect(git.getAttribute('aria-selected')).toBe('true')
    expect(preview.getAttribute('aria-selected')).toBe('false')
    expect(document.activeElement).toBe(git)
    expect(git.tabIndex).toBe(0)

    // Wrapping: right from the last pill back to the first.
    fireEvent.keyDown(git, { key: 'ArrowRight' })
    expect(preview.getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(preview)

    fireEvent.keyDown(preview, { key: 'ArrowLeft' })
    expect(git.getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(git)
  })
})
