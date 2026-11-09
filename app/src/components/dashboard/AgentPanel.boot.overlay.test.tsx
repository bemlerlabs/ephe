/**
 * Regression: "a persisted url tab at start opens no overlay above the composer."
 *
 * The desktop app came up with a foreign page above the chat composer, with no
 * panel around it. The page itself is the native browser child WebView (closed on
 * every boot by lib/nativeBrowser.closeOrphanedBrowserPane, pinned in
 * lib/nativeBrowser.boot.test.ts); the tab inventory is the other half of the
 * guard: a stored url/browser page may come back into the bar, but it must not be
 * brought forward on its own, and the panel itself starts closed.
 *
 * GIVEN  persisted panel tabs that name the url pane — 'url', 'browser', 'preview' —
 *        and no user action
 * WHEN   the chat mounts
 * THEN   the composer is on screen, no tabpanel/iframe/overlay is painted above it,
 *        the stored page is not focused, and only a user action opens the pane.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
  runShell: vi.fn(async () => ({ output: '' })),
  runShellPty: vi.fn(async () => ({ command: 'ls', output: '', ok: true })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  listArtifacts: vi.fn(async () => ({ artifacts: [] })),
  listFs: vi.fn(async () => ({ entries: [] })),
  listChangeSets: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'p', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
  gitAdd: vi.fn(async () => ({ success: true })),
  gitCommit: vi.fn(async () => ({ success: true, hash: 'abc1234' })),
  gitApplyPatch: vi.fn(async () => ({ success: true })),
  fileUrl: vi.fn((p: string) => `/api/file?path=${p}`),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

/** What the chat column paints when it boots: the composer the pane must not cover. */
function ChatBoot() {
  return (
    <div>
      <textarea data-testid="composer" aria-label="Message" />
      <AgentPanel />
    </div>
  )
}

function seed(tabs: string[], active: string) {
  localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs))
  localStorage.setItem('ephe.panel.activeTab', JSON.stringify(active))
}

beforeEach(() => {
  localStorage.clear()
  window.matchMedia = vi.fn((q: string) => ({
    matches: false,
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver
})

describe('startup — a stored url tab opens no overlay above the composer', () => {
  for (const [tabs, active] of [
    [['url'], 'url'],
    [['browser'], 'browser'],
    [['preview'], 'preview'],
    [['url', 'git'], 'url'],
  ] as const) {
    it(`stored ${JSON.stringify(tabs)} / ${active}: composer free, nothing painted over it`, () => {
      seed([...tabs], active)
      render(<ChatBoot />)

      // The composer is the first thing the user must find — and it is reachable.
      const composer = screen.getByTestId('composer')
      expect(composer).toBeTruthy()

      // Nothing was brought forward: no panel, no frame, no fixed overlay, and the
      // stored url page did not steal the focus (no address bar is focused).
      expect(document.querySelector('[role="tabpanel"]')).toBeNull()
      expect(document.querySelector('[data-testid="panel-resize-handle"]')).toBeNull()
      expect(document.querySelector('iframe')).toBeNull()
      expect(document.querySelector('[data-testid="preview-url-input"]')).toBeNull()
      expect(document.activeElement).toBe(document.body)
    })
  }

  it('a user action still opens the pane — the guard only removes the automatic one', async () => {
    seed(['preview', 'git'], 'preview')
    render(<ChatBoot />)
    expect(document.querySelector('[role="tabpanel"]')).toBeNull()

    act(() => {
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
    })
    const panel = await screen.findByRole('tabpanel')
    expect(panel).toBeTruthy()
    // Restore guard: the bar came up on the workspace page, not the url pane.
    expect(
      document.querySelector('[data-testid="panel-tab-pill-git"]')?.getAttribute('aria-selected'),
    ).toBe('true')
  })

  it('the panel keeps a hard width bound on a desktop split (never across the composer column)', async () => {
    seed(['preview'], 'preview')
    render(<ChatBoot />)
    act(() => {
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
    })
    const panel = await screen.findByRole('tabpanel')
    // The 60 % bound is a utility class so a stored/dragged width cannot override it.
    expect(panel.className).toContain('lg:max-w-[60vw]')
  })
})
