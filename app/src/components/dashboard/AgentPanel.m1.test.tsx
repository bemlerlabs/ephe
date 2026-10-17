import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ChatMessage } from '@/types'

// M1 (reference parity 2026-09-08, screenshot 3): browser tab with a full
// navigation bar (back/forward/reload, overflow menu with default browser +
// DevTools) and a three-part empty state; the Subagents tab in the "·" format
// with a Completed word and a Running section that is always visible.

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  runShell: vi.fn(async () => ({ output: '' })),
  runShellPty: vi.fn(async () => ({ command: '', output: '', ok: true })),
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
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

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
  }),
}))

const MESSAGES: ChatMessage[] = [
  {
    id: 'm1',
    role: 'assistant',
    content: 'ok',
    timestamp: Date.now() - 31 * 60_000,
    activities: [
      {
        id: 'a2',
        label: 'Agent Judge-Gate Z16',
        status: 'done',
        detail: 'Desktop-Pruefung: Karteikopf zeigt …',
      },
    ],
  },
]

function baseStubs() {
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
}

describe('M1 — Browser-Tab 1:1 (Referenz-Screenshot 3)', () => {
  beforeEach(() => {
    localStorage.clear()
    baseStubs()
  })

  it('Nav-Leiste: zurueck, vor, neu laden, URL-Feld und Ueberlauf-Knopf', async () => {
    render(<AgentPanel messages={[]} />)
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/a.md' } }),
    )
    expect(await screen.findByTestId('preview-reload')).toBeTruthy()
    expect(screen.getByTestId('preview-back')).toBeTruthy()
    expect(screen.getByTestId('preview-forward')).toBeTruthy()
    expect(screen.getByTestId('preview-url-input')).toBeTruthy()
    expect(screen.getByTestId('preview-overflow')).toBeTruthy()
  })

  it('Ueberlauf-Menue: In Standardbrowser oeffnen (DevTools-Item als Luegen-UI entfernt, F-5)', async () => {
    render(<AgentPanel messages={[]} />)
    // P2-A: internal path URL (the panel now routes http(s) to the browser tab)
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/a.md' } }),
    )
    fireEvent.click(await screen.findByTestId('preview-overflow'))
    expect(await screen.findByTestId('preview-menu-browser')).toBeTruthy()
    expect(screen.queryByTestId('preview-menu-devtools')).toBeNull()
  })

  it('Vor/Zuruck-Navigation ueber das Session-History des Tabs', async () => {
    render(<AgentPanel messages={[]} />)
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/a.md' } }),
    )
    await screen.findByTestId('preview-reload')
    // Re-queried per check: the pane subtree remounts when the tab opens, and a node
    // captured before that keeps reporting the detached element's value.
    const address = () => (screen.getByTestId('preview-url-input') as HTMLInputElement).value
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/b.md' } }),
    )
    // Both forms of the bar identify the target, and the test must hold for either:
    // unfocused the input shows `prettifyUrl(draft)` = "b.md", focused it shows the raw
    // draft = "/api/file?path=/tmp/b.md" (previewTab.tsx:208). Opening a target and
    // navigating both move focus into the bar on a 40/60 ms timer (usePreviewNav.ts:78
    // and :114) — that is the documented follow-through, not a defect.
    //
    // This is why the case failed in CI three times while passing locally, and why the
    // earlier fix (a 4 s timeout, run 37920432654 still red at 4173 ms) could not work:
    // sampling `=== "b.md"` asks whether the focus timer or the assertion poll won, and
    // a 4-core runner under a full vitest load loses that race reproducibly. Waiting
    // longer only waits longer for a state that never converges.
    await waitFor(() => expect(address()).toContain('b.md'), { timeout: 4000 })
    fireEvent.click(screen.getByTestId('preview-back'))
    await waitFor(() => expect(address()).toContain('a.md'), { timeout: 4000 })
    fireEvent.click(screen.getByTestId('preview-forward'))
    await waitFor(() => expect(address()).toContain('b.md'), { timeout: 4000 })
  })

  it('Leerzustand dreiteilig: Globus-Titel "Browser" + Hinweis (kein URL-Wert)', async () => {
    render(<AgentPanel messages={[]} />)
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'preview' } }))
    expect(await screen.findByTestId('preview-empty-title')).toBeTruthy()
    expect(screen.getByTestId('preview-empty-hint')).toBeTruthy()
  })
})

describe('M1 — Subagents im Referenz-Format', () => {
  beforeEach(() => {
    localStorage.clear()
    baseStubs()
  })

  it('Running-Sektion erscheint immer, bei 0 mit "No running subagents"-Zeile', async () => {
    render(<AgentPanel messages={MESSAGES} />)
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'subagents' } }))
    const running = await screen.findByTestId('subagents-running-section')
    expect(within(running).getByTestId('subagents-none-row')).toBeTruthy()
  })

  it('Ended-Zeile: Name + Completed-Wort + rechts Zeit, Detail darunter (clamp)', async () => {
    render(<AgentPanel messages={MESSAGES} />)
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'subagents' } }))
    const ended = await screen.findByTestId('subagents-ended-section')
    const row = within(ended).getByTestId('subagent-row-a2')
    expect(within(row).getByTestId('subagent-state-a2').textContent).toBe(
      'agentPanel.subagentCompleted',
    )
    expect(within(row).getByTestId('subagent-time-a2')).toBeTruthy()
    // the detail is always visible now (no expand click needed)
    expect(within(row).getByTestId('subagent-detail-a2').textContent).toContain('Desktop-Pruefung')
  })
})
