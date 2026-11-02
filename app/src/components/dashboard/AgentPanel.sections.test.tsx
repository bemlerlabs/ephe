/**
 * C1: one icon per section, expand on click, fold the body away on the click
 * that asks for it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

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

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const renderPanel = () =>
  render(
    <MemoryRouter>
      <AgentPanel />
    </MemoryRouter>,
  )

const setPersisted = (tabs: string[], active: string) => {
  localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs))
  localStorage.setItem('ephe.panel.activeTab', JSON.stringify(active))
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

describe('AgentPanel sections (C1)', () => {
  it('draws one icon per section that holds something open', async () => {
    setPersisted(['files', 'terminal', 'memory'], 'files')
    renderPanel()
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

    const row = await screen.findByTestId('panel-sections')
    expect(within(row).getByTestId('panel-section-output')).toBeTruthy()
    expect(within(row).getByTestId('panel-section-console')).toBeTruthy()
    expect(within(row).getByTestId('panel-section-notes')).toBeTruthy()
    // nothing open in the site or review section, so neither asks for attention
    expect(within(row).queryByTestId('panel-section-site')).toBeNull()
    expect(within(row).queryByTestId('panel-section-review')).toBeNull()

    // minimal until it is the one you are looking at: the forward section names
    // itself, the others stay icons — with a name a reader can still reach
    expect(screen.getByTestId('panel-section-output').textContent).toContain(
      'agentPanel.section.output',
    )
    expect(screen.getByTestId('panel-section-console').textContent).not.toContain(
      'agentPanel.section.console',
    )
    expect(screen.getByLabelText('agentPanel.section.console')).toBeTruthy()
  })

  it('brings another section forward, then folds the body away on its own icon', async () => {
    setPersisted(['files', 'terminal'], 'files')
    renderPanel()
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

    const output = await screen.findByTestId('panel-section-output')
    const console_ = screen.getByTestId('panel-section-console')
    expect(output.getAttribute('aria-pressed')).toBe('true')

    fireEvent.click(console_)
    expect(screen.getByTestId('panel-section-console').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('panel-section-output').getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByTestId('panel-body')).toBeTruthy()

    fireEvent.click(screen.getByTestId('panel-section-console'))
    expect(screen.queryByTestId('panel-body')).toBeNull()

    fireEvent.click(screen.getByTestId('panel-section-console'))
    expect(screen.getByTestId('panel-body')).toBeTruthy()
  })

  it('a pill click unfolds the body again', async () => {
    setPersisted(['files', 'terminal'], 'files')
    renderPanel()
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

    fireEvent.click(await screen.findByTestId('panel-section-output'))
    expect(screen.queryByTestId('panel-body')).toBeNull()

    fireEvent.click(screen.getByTestId('panel-tab-pill-terminal'))
    expect(screen.getByTestId('panel-body')).toBeTruthy()
  })
})
