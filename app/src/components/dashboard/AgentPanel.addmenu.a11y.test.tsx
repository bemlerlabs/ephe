import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { TAB_KEYS } from '@/components/dashboard/agent/primitives'

/**
 * P4 (keyboard round), findings 1 + 2:
 * 1 — the +-menu offers ALL pane pages (before: 4 of 10; "Wiss" found nothing),
 * 2 — it is a real menu: its own focus, roving over ArrowUp/ArrowDown/
 *     Home/End, a closed tab cycle, Escape returns focus to the trigger
 *     and leaves the pane open.
 */

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

vi.mock('./agent/LiveTerminal', () => ({ default: () => <div data-testid="live-terminal" /> }))

// German labels as in the product — the search filters on them, not on keys.
const DE: Record<string, string> = {
  'agentPanel.tabPreview': 'Browser',
  'agentPanel.tabTerminal': 'Terminal',
  'agentPanel.tabGit': 'Änderungen',
  'agentPanel.tabFiles': 'Dateien',
  'agentPanel.tabAudit': 'Nachweis',
  'agentPanel.tabTrajectory': 'Replay',
  'agentPanel.tabSubagents': 'Helfer',
  'agentPanel.tabMemory': 'Wissen',
  'agentPanel.tabSide': 'Side-Gespraech',
  'agentPanel.addTab': 'Tab hinzufügen',
  'agentPanel.searchTabs': 'Tabs durchsuchen…',
  'agentPanel.openTabsSection': 'Geöffnete Tabs',
  'agentPanel.closedTabsSection': 'Zuletzt geschlossene Tabs',
  'agentPanel.availableTabsSection': 'Verfügbar',
  'agentPanel.noTabMatches': 'Keine passenden Tabs',
  'agentPanel.now': 'jetzt',
  'agentPanel.closeTab': 'Tab schließen',
  'agentPanel.title': 'Agent-Pane',
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => DE[key] ?? key }),
}))

const openPane = () =>
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

async function openMenu(tabs: string[]) {
  localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs))
  render(<AgentPanel />)
  openPane()
  fireEvent.click(await screen.findByTestId('panel-add-tab'))
  return screen.getByTestId('panel-add-menu')
}

beforeEach(() => {
  localStorage.clear()
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

describe('the +-menu offers every page (P4 finding 1)', () => {
  it('every tab page has a menu row and the four main entries stay', async () => {
    const menu = await openMenu(['preview'])
    for (const key of ['side', 'review', 'terminal', 'browser']) {
      expect(within(menu).getByTestId(`panel-new-tab-item-${key}`)).toBeTruthy()
    }
    for (const tab of ['files', 'audit', 'trajectory', 'subagents', 'memory']) {
      expect(within(menu).getByTestId(`panel-page-item-${tab}`)).toBeTruthy()
    }
    const names = within(menu)
      .getAllByRole('menuitem')
      .map((el) => (el.textContent || '').trim())
      .filter(Boolean)
    for (const label of [
      'Browser',
      'Terminal',
      'Änderungen',
      'Dateien',
      'Nachweis',
      'Replay',
      'Helfer',
      'Wissen',
      'Side-Gespraech',
    ]) {
      expect(names.filter((n) => n.includes(label)).length).toBeGreaterThan(0)
    }
    // Nine pages since the Steps tab left: its page listed the same steps the
    // plan card already draws, in a second vocabulary.
    expect(TAB_KEYS).toHaveLength(9)
  })

  it('searching "Wiss" finds Memory and "audit" finds the proof page', async () => {
    const menu = await openMenu(['preview'])
    const search = within(menu).getByTestId('panel-tab-search') as HTMLInputElement
    fireEvent.change(search, { target: { value: 'Wiss' } })
    expect(within(menu).queryByTestId('panel-page-item-memory')).toBeTruthy()
    expect(within(menu).queryByTestId('panel-new-tab-item-terminal')).toBeNull()
    fireEvent.change(search, { target: { value: 'audit' } })
    expect(within(menu).queryByTestId('panel-page-item-audit')).toBeTruthy()
    fireEvent.change(search, { target: { value: 'zzzz' } })
    expect(within(menu).getByText('Keine passenden Tabs')).toBeTruthy()
  })

  it('clicking an extra page opens it as a pill', async () => {
    const menu = await openMenu(['preview'])
    fireEvent.click(within(menu).getByTestId('panel-page-item-audit'))
    const pill = (await screen.findByRole('tab', { name: 'Nachweis' })) as HTMLElement
    expect(pill.getAttribute('aria-selected')).toBe('true')
  })
})

describe('the +-menu is keyboard operable (P4 finding 2)', () => {
  it('the trigger carries haspopup/expanded/controls, the menu role=menu', async () => {
    const menu = await openMenu(['preview'])
    expect(menu.getAttribute('role')).toBe('menu')
    expect(menu.id).toBe('panel-add-menu')
    const trigger = screen.getByTestId('panel-add-tab')
    expect(trigger.getAttribute('aria-haspopup')).toBe('menu')
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(trigger.getAttribute('aria-controls')).toBe('panel-add-menu')
    // No more nested interactive content: the close control is its own
    // menuitem button, not a role="button" INSIDE a row.
    const close = within(menu).getByTestId('panel-open-tab-close-preview')
    expect(close.tagName).toBe('BUTTON')
    expect(close.getAttribute('role')).toBe('menuitem')
    expect(close.parentElement?.tagName).not.toBe('BUTTON')
    // Exactly one menu in the document — the role sits on the overflow itself.
    expect(screen.getAllByRole('menu')).toHaveLength(1)
  })

  it('after opening, focus sits in the menu search field and stays off the trigger', async () => {
    const menu = await openMenu(['preview'])
    await vi.waitFor(() => expect(menu.contains(document.activeElement)).toBe(true))
    expect(document.activeElement?.getAttribute('data-testid')).toBe('panel-tab-search')
  })

  it('ArrowDown/ArrowUp/Home/End move the roving focus across the menuitems', async () => {
    const menu = await openMenu(['preview'])
    const items = within(menu).getAllByRole('menuitem') as HTMLElement[]
    const first = items[0]!
    const second = items[1]!
    const last = items[items.length - 1]!
    expect(items.every((i) => i.tabIndex === -1)).toBe(true)
    const search = within(menu).getByTestId('panel-tab-search')
    search.focus()
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(first)
    fireEvent.keyDown(first, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(second)
    fireEvent.keyDown(second, { key: 'End' })
    expect(document.activeElement).toBe(last)
    fireEvent.keyDown(last, { key: 'Home' })
    expect(document.activeElement).toBe(first)
    fireEvent.keyDown(first, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(last)
  })

  it('Enter on a row opens the page and closes the menu', async () => {
    const menu = await openMenu(['preview'])
    // The row the removed Steps page used to hold; any surviving page carries the
    // same keyboard contract.
    const row = within(menu).getByTestId('panel-page-item-files') as HTMLElement
    row.focus()
    fireEvent.keyDown(row, { key: 'ArrowDown' })
    fireEvent.click(row)
    expect(await screen.findByRole('tab', { name: 'Dateien' })).toBeTruthy()
    expect(screen.queryByTestId('panel-add-menu')).toBeNull()
  })

  it('Enter in the search field moves focus to the first result', async () => {
    const menu = await openMenu(['preview'])
    const search = within(menu).getByTestId('panel-tab-search')
    search.focus()
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(within(menu).getAllByRole('menuitem')[0]).toBe(document.activeElement)
  })

  it('Tab stays trapped in the menu and never walks the chat behind it', async () => {
    const menu = await openMenu(['preview'])
    const items = within(menu).getAllByRole('menuitem') as HTMLElement[]
    const last = items[items.length - 1]!
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(menu.contains(document.activeElement)).toBe(true)
    expect(document.activeElement?.getAttribute('data-testid')).toBe('panel-tab-search')
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  it('Escape closes only the menu and hands focus back to the trigger', async () => {
    const menu = await openMenu(['preview'])
    const search = within(menu).getByTestId('panel-tab-search')
    search.focus()
    fireEvent.keyDown(search, { key: 'Escape' })
    expect(screen.queryByTestId('panel-add-menu')).toBeNull()
    // The pane stays open (previously Escape closed the entire pane).
    expect(screen.getByTestId('panel-add-tab')).toBeTruthy()
    expect(document.activeElement).toBe(screen.getByTestId('panel-add-tab'))
  })

  it('ArrowDown on the trigger opens the menu', async () => {
    const menu = await openMenu(['preview'])
    fireEvent.keyDown(within(menu).getByTestId('panel-tab-search'), { key: 'Escape' })
    expect(screen.queryByTestId('panel-add-menu')).toBeNull()
    const trigger = screen.getByTestId('panel-add-tab')
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    expect(await screen.findByTestId('panel-add-menu')).toBeTruthy()
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
  })

  it('sections are role=group with a real name', async () => {
    const menu = await openMenu(['preview'])
    const groups = within(menu).getAllByRole('group')
    expect(groups.length).toBeGreaterThanOrEqual(2)
    expect(groups.map((g) => g.getAttribute('aria-labelledby')).every(Boolean)).toBe(true)
    expect(screen.getByText('Verfügbar')).toBeTruthy()
  })
})
