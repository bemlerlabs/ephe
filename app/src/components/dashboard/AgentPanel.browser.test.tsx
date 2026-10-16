/**
 * P6 B5 (ref-22/24): ONE url pane in the agent panel — preview/browser dedup.
 *
 * GIVEN  the agent panel with the merged browser pane
 * WHEN   a PREVIEW_OPEN_EVENT arrives with an external http(s) URL OR an
 *        internal /api path
 * THEN   the same pane opens (tab key 'preview') with the URL in the address
 *        bar + iframe; external pages get the honest fallback hint
 *        (X-Frame-Options). Persisted 'browser' tabs from before the dedup
 *        land in the url pane.
 *
 * Note: the i18n test mock returns the key itself — so the accessible pill
 * name is 'agentPanel.tabPreview' (real UI label: Browser).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'defaultValue' in opts ? String(opts.defaultValue) : key,
  }),
}))

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
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
}))

function openPane() {
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
}
function openViaUrl(url: string, tab?: string) {
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url, tab } }))
}
function setPersistedTabs(tabs: string[]) {
  localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs))
}

describe('AgentPanel Browser-Pane (P6 B5, Preview/Browser-Dedup)', () => {
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

  it('externe http(s)-URL-Event oeffnet das URL-Pane mit der URL im iframe', async () => {
    setPersistedTabs([])
    render(<AgentPanel />)
    openPane()
    openViaUrl('https://example.com/article')
    const tab = await screen.findByRole('tab', { name: 'agentPanel.tabPreview' })
    expect(tab.getAttribute('aria-selected')).toBe('true')
    const iframe = (await screen.findByTestId('preview-frame')) as HTMLIFrameElement
    expect(iframe.getAttribute('src')).toBe('https://example.com/article')
    // Found 2026-10-02: an invalid sandbox token ('allow-popups-to-escape-
    // same-origin') was dropped silently by the browser — console error and
    // in effect no escape behaviour. Guard: only spec-conform tokens.
    const VALID_SANDBOX = new Set([
      'allow-scripts',
      'allow-same-origin',
      'allow-forms',
      'allow-popups',
      'allow-modals',
      'allow-orientation-lock',
      'allow-pointer-lock',
      'allow-presentation',
      'allow-popups-to-escape-sandbox',
      'allow-downloads',
      'allow-storage-access-by-user-activation',
    ])
    const tokens = (iframe.getAttribute('sandbox') ?? '').split(/\s+/).filter(Boolean)
    expect(tokens.filter((t) => !VALID_SANDBOX.has(t))).toEqual([])
    const input = screen.getByTestId('preview-url-input') as HTMLInputElement
    expect(input.value).toBe('https://example.com/article')
    // The honest fallback hint (X-Frame-Options) sits below the address bar
    expect(screen.getByTestId('preview-external-fallback')).toBeTruthy()
  })

  it('interne /api-URL-Event landet im selben Pane, ohne Fallback-Hinweis', async () => {
    setPersistedTabs([])
    render(<AgentPanel />)
    openPane()
    openViaUrl('/api/file?path=report.pdf')
    const tab = await screen.findByRole('tab', { name: 'agentPanel.tabPreview' })
    expect(tab.getAttribute('aria-selected')).toBe('true')
    const input = await screen.findByTestId('preview-url-input')
    expect((input as HTMLInputElement).value).toContain('report.pdf')
    expect(screen.queryByTestId('preview-external-fallback')).toBeNull()
  })

  it('Adressleiste ergaenzt scheme-freien Hosts das Protokoll (Enter laedt)', async () => {
    render(<AgentPanel />)
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'preview' } }))
    const input = (await screen.findByTestId('preview-url-input')) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'example.com' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    const frame = screen.getByTestId('preview-frame') as HTMLIFrameElement
    expect(frame.getAttribute('src')).toBe('https://example.com')
  })

  it('Menue-Key browser waehlt das URL-Pane (ein Pane, kein zweiter Tab-Typ)', async () => {
    setPersistedTabs([])
    render(<AgentPanel />)
    openPane()
    fireEvent.click(await screen.findByTestId('panel-add-tab'))
    fireEvent.click(await screen.findByTestId('panel-new-tab-item-browser'))
    expect(
      (await screen.findByRole('tab', { name: 'agentPanel.tabPreview' })).getAttribute(
        'aria-selected',
      ),
    ).toBe('true')
    // The 4 menu keys are fixed — the browser entry stays in the offer.
    fireEvent.click(screen.getByTestId('panel-add-tab'))
    const menu = screen.getByTestId('panel-add-menu')
    expect(within(menu).getByTestId('panel-new-tab-item-browser')).toBeTruthy()
  })

  it('persistiertes Inventar mit altem browser-Key landet im URL-Pane', async () => {
    setPersistedTabs(['browser'])
    render(<AgentPanel />)
    openPane()
    expect(
      (await screen.findByRole('tab', { name: 'agentPanel.tabPreview' })).getAttribute(
        'aria-selected',
      ),
    ).toBe('true')
    expect(await screen.findByTestId('preview-url-input')).toBeTruthy()
  })
})
