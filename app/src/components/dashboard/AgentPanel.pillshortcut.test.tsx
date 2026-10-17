import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { TAB_KEYS } from '@/components/dashboard/agent/primitives'
import { resolvePanelTabByDigit } from '@/components/dashboard/agent/useTabRegistry'
import { pillShortcut } from '@/components/dashboard/agent/tabsTabPill'
import { isMacPlatform } from '@/lib/shortcuts'

const MOD = isMacPlatform() ? 'Meta' : 'Control'
const GLYPH = isMacPlatform() ? '⌘' : 'Strg'

/**
 * P4 findings 3 + 4: the digit addresses the position in the VISIBLE bar
 * (⌘2 = the second pill, not the second registry key), and the pill names
 * the shortcut and the content expectation in its title.
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
  'agentPanel.tabTipAudit.title': 'Nachweis',
  'agentPanel.tabTipAudit.body': 'Werkzeuge, Dauer, Ergebnis',
  'agentPanel.tabTipPreview.title': 'Browser',
  'agentPanel.tabTipPreview.body': 'URLs, generierte Dateien und Artefakte',
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => DE[key] ?? key }),
}))

const openPane = () =>
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

// One key press on a real element (as in the browser: target = body) so that
// the capture path of the pane listener runs first.
const pressModDigit = (digit: string) =>
  fireEvent.keyDown(document.body, { key: digit, metaKey: true, code: `Digit${digit}` })

const selectedPill = async () =>
  ((await screen.findByRole('tab', { selected: true })) as HTMLElement).getAttribute('aria-label')

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

describe('resolvePanelTabByDigit — Ziffer = Position (P4 Befund 3)', () => {
  it('greift die sichtbare Leiste zuerst, nicht die Registry', () => {
    // Real case from the measurement: pills [preview, audit] — ⌘2 was 'terminal'.
    expect(resolvePanelTabByDigit(['preview', 'audit'], 2)).toBe('audit')
    expect(resolvePanelTabByDigit(['preview', 'audit'], 1)).toBe('preview')
    expect(TAB_KEYS[1]).toBe('terminal')
  })

  it('freie Position oeffnet dieselbe Seite wie bisher', () => {
    expect(resolvePanelTabByDigit(['preview'], 3)).toBe(TAB_KEYS[2])
    expect(resolvePanelTabByDigit([], 6)).toBe(TAB_KEYS[5])
  })

  it('⌘9 ist die letzte Stelle; ausserhalb des Inventars ist Feierabend', () => {
    const full = [...TAB_KEYS]
    // Nine pages now — the tenth slot the digit row used to reach went with the
    // Steps tab, so ⌘9 is the last number and ⌘0 answers nothing.
    expect(full).toHaveLength(9)
    expect(resolvePanelTabByDigit(full, 9)).toBe(full[8])
    expect(resolvePanelTabByDigit(['preview', 'audit'], 9)).toBe(TAB_KEYS[8])
    expect(resolvePanelTabByDigit(['preview'], 10)).toBeNull()
    expect(resolvePanelTabByDigit(['preview'], 0)).toBeNull()
  })
})

describe('⌘1–⌘9 im Pane', () => {
  it('⌘2 waehlt die zweite Pille (Nachweis), nicht Terminal', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'audit']))
    render(<AgentPanel />)
    openPane()
    await screen.findByRole('tab', { name: 'Nachweis' })
    pressModDigit('2')
    expect(await selectedPill()).toBe('Nachweis')
  })

  it('⌘1 waehlt die erste Pille', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'audit']))
    render(<AgentPanel />)
    openPane()
    await screen.findByRole('tab', { name: 'Nachweis' })
    pressModDigit('2')
    await selectedPill()
    pressModDigit('1')
    expect(await selectedPill()).toBe('Browser')
  })

  it('die Zahl feuert genau einmal — der Registry-Pfad wird abgefangen', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'audit']))
    const seen: unknown[] = []
    const onOpen = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(PREVIEW_OPEN_EVENT, onOpen)
    try {
      render(<AgentPanel />)
      openPane()
      await screen.findByRole('tab', { name: 'Nachweis' })
      seen.length = 0
      pressModDigit('2')
      await selectedPill()
      expect(seen).toEqual([{ tab: 'audit', toggle: true }])
    } finally {
      window.removeEventListener(PREVIEW_OPEN_EVENT, onOpen)
    }
  })

  it('in einem modalen Dialog und in Eingabefeldern bleibt die Zahl ruhig', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'audit']))
    render(<AgentPanel />)
    openPane()
    await screen.findByRole('tab', { name: 'Nachweis' })

    const host = document.createElement('div')
    host.setAttribute('role', 'dialog')
    host.setAttribute('aria-modal', 'true')
    document.body.appendChild(host)
    try {
      pressModDigit('2')
      expect(await selectedPill()).toBe('Browser')
    } finally {
      host.remove()
    }

    const input = document.createElement('input')
    document.body.appendChild(input)
    try {
      input.focus()
      fireEvent.keyDown(input, { key: '2', metaKey: true })
      await vi.waitFor(async () => expect(await selectedPill()).toBe('Browser'))
    } finally {
      input.remove()
    }
  })
})

describe('Pillen-Titel und Kurzbefehl im Accessibility-Baum (P4 Befund 4)', () => {
  it('title sagt Label, Inhaltserwartung und die echte Ziffer', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'audit']))
    render(<AgentPanel />)
    openPane()
    const audit = (await screen.findByRole('tab', { name: 'Nachweis' })) as HTMLElement
    expect(audit.getAttribute('title')).toBe(`Nachweis — Werkzeuge, Dauer, Ergebnis (${GLYPH}2)`)
    expect(audit.getAttribute('aria-keyshortcuts')).toBe(`${MOD}+2`)
    // The name stays the bare label — the aria-label/dedup tests hang on it.
    expect(audit.getAttribute('aria-label')).toBe('Nachweis')
    const preview = (await screen.findByRole('tab', { name: 'Browser' })) as HTMLElement
    expect(preview.getAttribute('title')).toContain(`(${GLYPH}1)`)
  })

  it('die Ziffer folgt der Position, auch nach dem Schliessen einer Pille', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'audit', 'files']))
    render(<AgentPanel />)
    openPane()
    const audit = (await screen.findByRole('tab', { name: 'Nachweis' })) as HTMLElement
    expect(audit.getAttribute('aria-keyshortcuts')).toBe(`${MOD}+2`)
    fireEvent.click(screen.getByTestId('panel-tab-close-preview'))
    const moved = (await screen.findByRole('tab', { name: 'Nachweis' })) as HTMLElement
    expect(moved.getAttribute('aria-keyshortcuts')).toBe(`${MOD}+1`)
  })

  it('pillShortcut: Ziffer 0 an der zehnten Stelle, null ohne Ziffer', () => {
    expect(pillShortcut(1)?.label).toBe(`${GLYPH}1`)
    expect(pillShortcut(0)?.aria).toBe(`${MOD}+0`)
    expect(pillShortcut(null)).toBeNull()
  })

  it('der Schliesser nennt seine Wirkung an dieser Pille', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['audit']))
    render(<AgentPanel />)
    openPane()
    await screen.findByRole('tab', { name: 'Nachweis' })
    const close = screen.getByTestId('panel-tab-close-audit')
    expect(close.getAttribute('aria-label')).toBe('agentPanel.closeTab')
    expect(close.getAttribute('title')).toBe('agentPanel.closeTab: Nachweis')
  })
})
